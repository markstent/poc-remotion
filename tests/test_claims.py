import json
from pathlib import Path

import pytest

from poc_remotion import cli
from poc_remotion.claims import run_claims
from poc_remotion.cli import main
from poc_remotion.discovery import DraftError
from poc_remotion.llm import LLMClient
from poc_remotion.project import Project
from poc_remotion.schemas import Claim, ScriptDoc, ScriptLine, SourceRef


def _source() -> SourceRef:
    return SourceRef(
        id="handbook",
        title="Staff Handbook",
        path="sources/handbook.md",
        kind="markdown",
        sha256="a" * 64,
        headings=["Leave Policy", "Expenses"],
    )


def _script() -> ScriptDoc:
    return ScriptDoc(
        lines=[
            ScriptLine(scene_id="opening", text="We give everyone 25 days of leave."),
            ScriptLine(scene_id="rule", text="Expenses are paid within 30 days."),
        ]
    )


def _claim_reply(claims: list[dict]) -> str:
    return json.dumps({"claims": claims})


def _seeded_project(tmp_path: Path, script_approved: bool = True) -> Path:
    """Create a project with sources, a saved script and the gates set."""
    project_root = tmp_path / "projects"
    assert main(["init", "--id", "demo", "--projects-root", str(project_root)]) == 0
    project = Project.load(project_root / "demo")
    project.save_sources([_source()])
    project.save_script(_script())
    project.record_approval("storyboard")
    project.record_approval("duration")
    if script_approved:
        project.record_approval("script")
    return project_root


def _patch_client(monkeypatch: pytest.MonkeyPatch, replies: list[str]) -> list[dict]:
    """Route cli's LLMClient to a fake transport; return the captured payloads."""
    calls: list[dict] = []

    def fake_post(url: str, key: str, payload: dict) -> str:
        calls.append(payload)
        return replies.pop(0)

    monkeypatch.setattr(
        cli,
        "LLMClient",
        lambda: LLMClient(base_url="http://test", api_key="k", model="test-model", _post=fake_post),
    )
    return calls


def test_claims_extracted_and_supported(tmp_path, capsys, monkeypatch):
    """Mocked replies with known headings save supported claims with ids."""
    project_root = _seeded_project(tmp_path)
    calls = _patch_client(
        monkeypatch,
        [
            _claim_reply([{"text": "Annual leave is 25 days.", "source_heading": "leave policy"}]),
            _claim_reply(
                [
                    {"text": "The leave year starts in April.", "source_heading": "Leave Policy"},
                    {"text": "Expense claims close after 30 days.", "source_heading": "Leave Policy"},
                ]
            ),
        ],
    )

    result = main(["claims", "--id", "demo", "--projects-root", str(project_root)])

    assert result == 0
    data = json.loads((project_root / "demo" / "claims.json").read_text())
    assert [claim["id"] for claim in data] == ["claim-1-1", "claim-2-1", "claim-2-2"]
    assert data[0]["status"] == "supported"
    assert data[0]["source_ids"] == ["handbook"]
    # The stored heading casing wins over the reply's casing.
    assert data[0]["locator"] == "Leave Policy"

    out = capsys.readouterr().out
    assert "claim-1-1  supported  Annual leave is 25 days." in out
    assert "unresolved" not in out

    # One call per script line; the system prompt names the job.
    assert len(calls) == 2
    system = calls[0]["messages"][0]["content"]
    user = calls[0]["messages"][1]["content"]
    assert "claim extraction" in system
    assert "25 days of leave" in user


def test_claims_unresolved_when_heading_unknown(tmp_path, capsys, monkeypatch):
    """A heading that matches no source heading leaves the claim unresolved."""
    project_root = _seeded_project(tmp_path)
    _patch_client(
        monkeypatch,
        [
            _claim_reply([{"text": "The canteen opens at seven.", "source_heading": "No Such Section"}]),
            _claim_reply([]),
        ],
    )

    result = main(["claims", "--id", "demo", "--projects-root", str(project_root)])

    assert result == 0
    data = json.loads((project_root / "demo" / "claims.json").read_text())
    assert data[0]["status"] == "unresolved"
    assert data[0]["source_ids"] == []
    assert data[0]["locator"] == "No Such Section"

    out = capsys.readouterr().out
    assert "claim-1-1  unresolved  The canteen opens at seven." in out
    assert "1 unresolved" in out


def test_claims_requires_script_gate(tmp_path, capsys, monkeypatch):
    """Script gate not approved: exit 2 naming the gate, no LLM call."""
    project_root = _seeded_project(tmp_path, script_approved=False)
    calls = _patch_client(monkeypatch, [_claim_reply([])])

    result = main(["claims", "--id", "demo", "--projects-root", str(project_root)])

    assert result == 2
    err = capsys.readouterr().err
    assert "script" in err
    assert "gate" in err
    assert calls == []
    assert not (project_root / "demo" / "claims.json").exists()


def test_claims_rerun_replaces_register(tmp_path, monkeypatch):
    """A second run overwrites claims.json with exactly the new register."""
    project_root = _seeded_project(tmp_path)
    first = _patch_client(
        monkeypatch,
        [
            _claim_reply([{"text": "First run claim one.", "source_heading": "Leave Policy"}]),
            _claim_reply([{"text": "First run claim two.", "source_heading": "Leave Policy"}]),
        ],
    )
    assert main(["claims", "--id", "demo", "--projects-root", str(project_root)]) == 0
    assert len(Project.load(project_root / "demo").load_claims()) == 2

    second = _patch_client(
        monkeypatch,
        [
            _claim_reply([{"text": "Second run claim.", "source_heading": "Expenses"}]),
            _claim_reply([]),
        ],
    )
    assert main(["claims", "--id", "demo", "--projects-root", str(project_root)]) == 0

    register: list[Claim] = Project.load(project_root / "demo").load_claims()
    assert len(register) == 1
    assert register[0].id == "claim-1-1"
    assert register[0].text == "Second run claim."
    assert register[0].status == "supported"
    assert len(first) == 2 and len(second) == 2  # one call per line, both runs


def test_run_claims_gate_message_exact(tmp_path):
    """run_claims raises DraftError with the exact gate message."""
    project_root = _seeded_project(tmp_path, script_approved=False)
    project = Project.load(project_root / "demo")

    class _FailClient:
        def chat_json(self, system: str, user: str, schema: type) -> None:
            raise AssertionError("chat_json must not be called")

    with pytest.raises(DraftError) as exc_info:
        run_claims(project, _FailClient())

    assert str(exc_info.value) == "approve the script gate first"
