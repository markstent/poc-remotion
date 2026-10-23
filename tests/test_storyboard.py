import json
from pathlib import Path

import pytest

from poc_remotion import cli
from poc_remotion.cli import main
from poc_remotion.discovery import DraftError
from poc_remotion.llm import LLMClient
from poc_remotion.project import Project
from poc_remotion.schemas import Brief, Storyboard
from poc_remotion.storyboard import run_storyboard

SOURCE_MD = "# Alpha Doc\n\nintro\n\n## One\n\ntext\n\n## Two\n\ntext\n"

AUDIENCE = "New hires"
OBJECTIVES = ["Explain the release process"]


def _scene(
    id: str, kind: str, seconds: float, summary: str, on_screen: list[str]
) -> dict:
    return {
        "id": id,
        "kind": kind,
        "purpose": f"Cover {summary.lower()}",
        "seconds": seconds,
        "summary": summary,
        "on_screen": on_screen,
    }


def _storyboard_reply(duration_seconds: float, scenes: list[dict]) -> str:
    return json.dumps(
        {
            "objectives": OBJECTIVES,
            "duration_seconds": duration_seconds,
            "rationale": "Scenes follow the source flow.",
            "scenes": scenes,
        }
    )


def _valid_scenes() -> list[dict]:
    return [
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
    ]


STORYBOARD_REPLY = _storyboard_reply(300, _valid_scenes())


def _seeded_project(tmp_path: Path) -> Path:
    """Create a project with a registered source and a captured brief."""
    project_root = tmp_path / "projects"
    assert main(["init", "--id", "demo", "--projects-root", str(project_root)]) == 0
    src = tmp_path / "alpha.md"
    src.write_text(SOURCE_MD)
    assert (
        main(["ingest", "--id", "demo", "--source", str(src), "--projects-root", str(project_root)])
        == 0
    )
    project = Project.load(project_root / "demo")
    project.save_brief(
        Brief(
            audience=AUDIENCE,
            objectives=OBJECTIVES,
            tone="Practical",
            duration_minutes=5,
        )
    )
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


def test_draft_storyboard_happy_path(tmp_path, capsys, monkeypatch):
    """Brief and sources seeded; a valid reply saves the storyboard and prints the table."""
    project_root = _seeded_project(tmp_path)
    calls = _patch_client(monkeypatch, [STORYBOARD_REPLY])

    result = main(["draft-storyboard", "--id", "demo", "--projects-root", str(project_root)])

    assert result == 0
    data = json.loads((project_root / "demo" / "storyboard.json").read_text())
    assert data["duration_seconds"] == 300
    assert [scene["id"] for scene in data["scenes"]] == [
        "opening",
        "rule",
        "gcse",
        "summary",
        "closing",
    ]
    out = capsys.readouterr().out
    assert "opening" in out
    assert "title" in out
    assert "60" in out
    assert "Meet the colleague" in out

    # One call: the system prompt embeds the catalogue and on-screen spec,
    # the user prompt embeds the brief and the source titles with headings.
    assert len(calls) == 1
    system = calls[0]["messages"][0]["content"]
    user = calls[0]["messages"][1]["content"]
    assert "newsGrid" in system and "framework" in system
    assert "panel label G" in system
    assert "New hires" in user
    assert "Explain the release process" in user
    assert "5 minutes" in user
    assert "Alpha Doc" in user
    assert "One" in user and "Two" in user


def test_draft_requires_brief(tmp_path, capsys, monkeypatch):
    """No captured brief: exit 2 naming discover and brief; no LLM call is made."""
    project_root = tmp_path / "projects"
    assert main(["init", "--id", "demo", "--projects-root", str(project_root)]) == 0
    calls = _patch_client(monkeypatch, [STORYBOARD_REPLY])

    result = main(["draft-storyboard", "--id", "demo", "--projects-root", str(project_root)])

    assert result == 2
    err = capsys.readouterr().err
    assert "discover" in err
    assert "brief" in err
    assert calls == []


def test_draft_duration_outside_window(tmp_path, capsys, monkeypatch):
    """Brief 5 minutes, reply says 2 minutes: exit 2, message shows both, nothing saved."""
    project_root = _seeded_project(tmp_path)
    off_reply = _storyboard_reply(
        120,
        [
            _scene("opening", "title", 40, "Meet the colleague", ["headline", "subheadline"]),
            _scene("rule", "quote", 40, "Ask clarifying questions", ["quote line"]),
            _scene("closing", "outro", 40, "Try it today", ["call to action"]),
        ],
    )
    calls = _patch_client(monkeypatch, [off_reply])

    result = main(["draft-storyboard", "--id", "demo", "--projects-root", str(project_root)])

    assert result == 2
    err = capsys.readouterr().err
    assert "5.0 minutes" in err
    assert "2.0 minutes" in err
    assert not (project_root / "demo" / "storyboard.json").exists()
    assert len(calls) == 1  # a window failure fails immediately, no repair re-ask


def test_scene_seconds_mismatch_repairs_once(tmp_path, capsys, monkeypatch):
    """First reply's scene seconds are off by 10s; the repair re-ask returns a valid board."""
    project_root = _seeded_project(tmp_path)
    off_scenes = _valid_scenes()
    off_scenes[0]["seconds"] = 70  # sum 310 against duration_seconds 300
    bad_reply = _storyboard_reply(300, off_scenes)
    calls = _patch_client(monkeypatch, [bad_reply, STORYBOARD_REPLY])

    result = main(["draft-storyboard", "--id", "demo", "--projects-root", str(project_root)])

    assert result == 0
    data = json.loads((project_root / "demo" / "storyboard.json").read_text())
    assert sum(scene["seconds"] for scene in data["scenes"]) == 300
    out = capsys.readouterr().out
    assert "closing" in out
    # Exactly one repair re-ask: same system prompt, mismatch named in the user prompt.
    assert len(calls) == 2
    assert calls[1]["messages"][0]["content"] == calls[0]["messages"][0]["content"]
    repair_user = calls[1]["messages"][1]["content"]
    assert "seconds" in repair_user
    assert "310" in repair_user
    assert "300" in repair_user


class _BadOnScreenClient:
    """Stub client returning a framework scene with too few on_screen entries."""

    def __init__(self) -> None:
        self.calls = 0

    def chat_json(self, system: str, user: str, schema: type[Storyboard]) -> Storyboard:
        self.calls += 1
        reply = _storyboard_reply(
            300,
            [
                _scene("opening", "title", 60, "Meet the colleague", ["headline", "subheadline"]),
                _scene("rule", "quote", 60, "Ask clarifying questions", ["quote line"]),
                _scene(
                    "gcse",
                    "framework",
                    60,
                    "Goal, Context, Source, Expectations",
                    ["panel label G", "panel label C"],
                ),
                _scene("closing", "outro", 60, "Try it today", ["call to action"]),
            ],
        )
        return Storyboard(**json.loads(reply))


def test_on_screen_length_enforced(tmp_path):
    """A wrong on_screen length raises DraftError naming the scene id and kind; nothing saved."""
    project_root = _seeded_project(tmp_path)
    project = Project.load(project_root / "demo")
    client = _BadOnScreenClient()

    with pytest.raises(DraftError) as exc_info:
        run_storyboard(project, client)

    message = str(exc_info.value)
    assert "gcse" in message
    assert "framework" in message
    assert client.calls == 1
    assert not (project_root / "demo" / "storyboard.json").exists()
