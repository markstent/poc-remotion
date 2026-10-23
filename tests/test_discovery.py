import json
from pathlib import Path

import pytest

from poc_remotion import cli
from poc_remotion.cli import main
from poc_remotion.discovery import DraftError, run_discovery
from poc_remotion.llm import LLMClient
from poc_remotion.project import Project
from poc_remotion.schemas import Brief, DiscoveryAnswer, DiscoveryQuestions

QUESTIONS = [
    "Who is the audience?",
    "What should viewers do differently afterwards?",
    "What tone suits the subject matter?",
    "How long should the video feel?",
    "Which source sections matter most?",
]

SOURCE_MD = "# Alpha Doc\n\nintro\n\n## One\n\ntext\n\n## Two\n\ntext\n"


def _project_with_source(tmp_path: Path) -> Path:
    """Create a project and register one markdown source."""
    project_root = tmp_path / "projects"
    assert main(["init", "--id", "demo", "--projects-root", str(project_root)]) == 0
    src = tmp_path / "alpha.md"
    src.write_text(SOURCE_MD)
    assert (
        main(["ingest", "--id", "demo", "--source", str(src), "--projects-root", str(project_root)])
        == 0
    )
    return project_root


def _patch_client(monkeypatch: pytest.MonkeyPatch, reply: str) -> list[dict]:
    """Route cli's LLMClient to a fake transport; return the captured payloads."""
    calls: list[dict] = []

    def fake_post(url: str, key: str, payload: dict) -> str:
        calls.append(payload)
        return reply

    monkeypatch.setattr(
        cli,
        "LLMClient",
        lambda: LLMClient(base_url="http://test", api_key="k", model="test-model", _post=fake_post),
    )
    return calls


def test_discovery_questions_saved(tmp_path, capsys, monkeypatch):
    """Discover saves one empty-answer qa entry per question and prints them numbered."""
    project_root = _project_with_source(tmp_path)
    calls = _patch_client(monkeypatch, json.dumps({"questions": QUESTIONS}))

    result = main(["discover", "--id", "demo", "--projects-root", str(project_root)])

    assert result == 0
    data = json.loads((project_root / "demo" / "brief.json").read_text())
    assert [qa["question"] for qa in data["qa"]] == QUESTIONS
    assert all(qa["answer"] == "" for qa in data["qa"])
    out = capsys.readouterr().out
    assert "1. Who is the audience?" in out
    assert "5. Which source sections matter most?" in out

    # The prompt names the source title and headings; the system prompt is a
    # discovery prompt (task 10 routes mocked replies by these markers).
    messages = calls[0]["messages"]
    assert "Alpha Doc" in messages[1]["content"]
    assert "One" in messages[1]["content"] and "Two" in messages[1]["content"]
    assert "discovery" in messages[0]["content"].lower()


def test_discovery_is_resumable(tmp_path, capsys, monkeypatch):
    """Existing questions keep their answers; only new questions are appended."""
    project_root = _project_with_source(tmp_path)
    project = Project.load(project_root / "demo")
    project.save_brief(
        Brief(qa=[DiscoveryAnswer(question=QUESTIONS[0], answer="Platform engineers")])
    )

    _patch_client(monkeypatch, json.dumps({"questions": QUESTIONS}))

    result = main(["discover", "--id", "demo", "--projects-root", str(project_root)])

    assert result == 0
    data = json.loads((project_root / "demo" / "brief.json").read_text())
    assert len(data["qa"]) == 5
    assert data["qa"][0] == {"question": QUESTIONS[0], "answer": "Platform engineers"}
    assert [qa["question"] for qa in data["qa"][1:]] == QUESTIONS[1:]
    assert all(qa["answer"] == "" for qa in data["qa"][1:])
    out_lines = capsys.readouterr().out.splitlines()
    # The helper's ingest line precedes the discover block: last 5 lines only.
    assert out_lines[-len(QUESTIONS)] == f"1. {QUESTIONS[0]}"


def test_discovery_requires_sources(tmp_path, capsys, monkeypatch):
    """No sources registered: exit 2 naming ingest; no LLM call is made."""
    project_root = tmp_path / "projects"
    assert main(["init", "--id", "demo", "--projects-root", str(project_root)]) == 0
    calls = _patch_client(monkeypatch, json.dumps({"questions": QUESTIONS}))

    result = main(["discover", "--id", "demo", "--projects-root", str(project_root)])

    assert result == 2
    assert "no sources registered; run ingest first" in capsys.readouterr().err
    assert calls == []


def test_discovery_rejects_empty_questions(tmp_path, capsys, monkeypatch):
    """An empty question set fails loudly: exit 2 and brief.json untouched."""
    project_root = _project_with_source(tmp_path)
    _patch_client(monkeypatch, json.dumps({"questions": []}))

    result = main(["discover", "--id", "demo", "--projects-root", str(project_root)])

    assert result == 2
    assert capsys.readouterr().err != ""
    data = json.loads((project_root / "demo" / "brief.json").read_text())
    assert data.get("qa", []) == []


class _EmptyQuestionsClient:
    """Stub client returning an empty question set, bypassing schema constraints."""

    def chat_json(
        self, system: str, user: str, schema: type[DiscoveryQuestions]
    ) -> DiscoveryQuestions:
        return DiscoveryQuestions.model_construct(questions=[])


def test_run_discovery_rejects_empty_questions(tmp_path):
    """run_discovery raises DraftError (nothing saved) when no questions come back."""
    project_root = _project_with_source(tmp_path)
    project = Project.load(project_root / "demo")
    with pytest.raises(DraftError, match="no questions"):
        run_discovery(project, _EmptyQuestionsClient())
    data = json.loads((project_root / "demo" / "brief.json").read_text())
    assert data.get("qa", []) == []
