import json
from pathlib import Path

import pytest

from poc_remotion import cli
from poc_remotion.cli import main
from poc_remotion.discovery import DraftError
from poc_remotion.llm import LLMClient
from poc_remotion.project import Project
from poc_remotion.schemas import Brief, ScriptDoc, Storyboard
from poc_remotion.script_draft import run_script

AUDIENCE = "New hires"
OBJECTIVES = ["Explain the release process"]

# 21 words; repeated five times per line gives 105 words per line, so five
# scenes land at 525 words, inside the 487.5 to 1012.5 window for 300 seconds.
_LINE_TEXT = (
    "Here is a line of narration with plenty of words to keep the pacing "
    "natural and the count inside the window. " * 5
)


def _scene(id: str, kind: str, seconds: float, summary: str, on_screen: list[str]) -> dict:
    return {
        "id": id,
        "kind": kind,
        "purpose": f"Cover {summary.lower()}",
        "seconds": seconds,
        "summary": summary,
        "on_screen": on_screen,
    }


def _storyboard() -> Storyboard:
    return Storyboard(
        objectives=OBJECTIVES,
        duration_seconds=300,
        rationale="Scenes follow the source flow.",
        scenes=[
            _scene("opening", "title", 60, "Meet the colleague", ["headline", "subheadline"]),
            _scene("rule", "quote", 60, "Ask clarifying questions", ["quote line"]),
            _scene(
                "gcse",
                "framework",
                60,
                "Goal, Context, Source, Expectations",
                ["panel label G", "panel label C", "panel label S", "panel label E"],
            ),
            _scene("summary", "cheatSheet", 60, "Recap the rules", ["panel 1", "panel 2", "panel 3"]),
            _scene("closing", "outro", 60, "Try it today", ["call to action"]),
        ],
    )


SCENE_IDS = ["opening", "rule", "gcse", "summary", "closing"]


def _script_reply(lines: list[dict]) -> str:
    return json.dumps({"lines": lines})


def _full_lines(text: str = _LINE_TEXT) -> list[dict]:
    return [{"scene_id": scene_id, "text": text} for scene_id in SCENE_IDS]


def _seeded_project(tmp_path: Path, approved: bool = True) -> Path:
    """Create a project with a brief and an approved 5 minute storyboard."""
    project_root = tmp_path / "projects"
    assert main(["init", "--id", "demo", "--projects-root", str(project_root)]) == 0
    project = Project.load(project_root / "demo")
    project.save_brief(
        Brief(audience=AUDIENCE, objectives=OBJECTIVES, tone="Light", duration_minutes=5)
    )
    project.save_storyboard(_storyboard())
    if approved:
        project.record_approval("storyboard")
        project.record_approval("duration")
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


def test_draft_script_happy_path(tmp_path, capsys, monkeypatch):
    """Approved gates; one line per scene saves the script and exits 0."""
    project_root = _seeded_project(tmp_path)
    calls = _patch_client(monkeypatch, [_script_reply(_full_lines())])

    result = main(["draft-script", "--id", "demo", "--projects-root", str(project_root)])

    assert result == 0
    data = json.loads((project_root / "demo" / "script.json").read_text())
    assert [line["scene_id"] for line in data["lines"]] == SCENE_IDS
    assert data["on_screen"] == {}  # scenes render the storyboard's on_screen
    assert all(line["start_seconds"] is None for line in data["lines"])
    assert all(line["end_seconds"] is None for line in data["lines"])

    out = capsys.readouterr().out
    assert "opening" in out and "closing" in out
    assert "525" in out  # per-scene counts and the word total

    # One call: the system prompt embeds the on-screen spec and names the
    # narration job; the user prompt embeds the storyboard and the brief.
    assert len(calls) == 1
    system = calls[0]["messages"][0]["content"]
    user = calls[0]["messages"][1]["content"]
    assert "narration" in system
    assert "panel label G" in system
    assert "opening" in user and "gcse" in user
    assert "quote" in user and "60" in user
    assert "Meet the colleague" in user
    assert "New hires" in user


def test_draft_script_requires_gates(tmp_path, capsys, monkeypatch):
    """Gates not approved: exit 2, message names the gates, no LLM call."""
    project_root = _seeded_project(tmp_path, approved=False)
    calls = _patch_client(monkeypatch, [_script_reply(_full_lines())])

    result = main(["draft-script", "--id", "demo", "--projects-root", str(project_root)])

    assert result == 2
    err = capsys.readouterr().err
    assert "storyboard" in err
    assert "duration" in err
    assert calls == []
    assert not (project_root / "demo" / "script.json").exists()


class _StubClient:
    """Stub client returning a canned script reply."""

    def __init__(self, lines: list[dict]) -> None:
        self._lines = lines
        self.calls = 0

    def chat_json(self, system: str, user: str, schema: type[ScriptDoc]) -> ScriptDoc:
        self.calls += 1
        return ScriptDoc(**json.loads(_script_reply(self._lines)))


def test_draft_script_unknown_scene_rejected(tmp_path):
    """A reply naming an unknown scene id fails; script.json stays absent."""
    project_root = _seeded_project(tmp_path)
    lines = _full_lines()
    lines.append({"scene_id": "sX", "text": _LINE_TEXT})
    project = Project.load(project_root / "demo")
    client = _StubClient(lines)

    with pytest.raises(DraftError) as exc_info:
        run_script(project, client)

    assert "sX" in str(exc_info.value)
    assert client.calls == 1
    assert not (project_root / "demo" / "script.json").exists()


def test_draft_script_word_count_window(tmp_path):
    """40 narration words against a 750 word target fails, naming both."""
    project_root = _seeded_project(tmp_path)
    lines = _full_lines("Just a few short bridging words right here.")
    project = Project.load(project_root / "demo")
    client = _StubClient(lines)

    with pytest.raises(DraftError) as exc_info:
        run_script(project, client)

    message = str(exc_info.value)
    assert "40" in message
    assert "750" in message
    assert "487.5" in message
    assert not (project_root / "demo" / "script.json").exists()


def test_draft_script_rejects_timings(tmp_path):
    """A reply that carries start_seconds on a line fails the checks."""
    project_root = _seeded_project(tmp_path)
    lines = _full_lines()
    lines[0] = {"scene_id": "opening", "text": _LINE_TEXT, "start_seconds": 0.0}
    project = Project.load(project_root / "demo")
    client = _StubClient(lines)

    with pytest.raises(DraftError) as exc_info:
        run_script(project, client)

    assert "timings" in str(exc_info.value)
    assert not (project_root / "demo" / "script.json").exists()
