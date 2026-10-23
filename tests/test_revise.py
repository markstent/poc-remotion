"""Tests for targeted scene revision with gate reset."""

import json
import wave
from pathlib import Path

import pytest
from pydantic import BaseModel

from poc_remotion import cli
from poc_remotion.cli import main
from poc_remotion.narrate import run_narrate
from poc_remotion.project import Project
from poc_remotion.revise import ReviseError, run_revise
from poc_remotion.schemas import (
    Brief,
    NarrationDoc,
    ScriptDoc,
    ScriptLine,
    Storyboard,
    StoryboardScene,
)
from poc_remotion.tts import KokoroAdapter

_PROJECT_ID = "demo"
_VOICE = "bf_emma"


class FakeClient:
    """Test double returning one canned RevisedScene payload."""

    def __init__(self, reply: dict) -> None:
        self._reply = reply
        self.calls: list[tuple[str, str]] = []

    def chat_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        self.calls.append((system, user))
        return schema.model_validate(self._reply)


class FakeEngine:
    """Test double writing a valid half-second wav for every line."""

    def synthesize(self, text: str, voice: str, out_path: Path) -> None:
        with wave.open(str(out_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(44100)
            wav.writeframes(b"\x00\x00" * 22050)


def _seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Project, KokoroAdapter]:
    """Seed a narrated project: two scenes, three lines, approvals, audio."""
    root = tmp_path / "projects"
    assert main(["init", "--id", _PROJECT_ID, "--projects-root", str(root)]) == 0
    project = Project.load(root / _PROJECT_ID)
    project.save_brief(Brief(audience="New hires", objectives=["Teach"], tone="Light"))
    project.save_storyboard(
        Storyboard(
            objectives=["Teach"],
            duration_seconds=3.8,
            rationale="Planned pacing.",
            scenes=[
                StoryboardScene(
                    id="opening",
                    kind="title",
                    purpose="Opener",
                    seconds=3.0,
                    summary="Meet the tool",
                    on_screen=["headline", "subheadline"],
                ),
                StoryboardScene(
                    id="closing",
                    kind="outro",
                    purpose="Closer",
                    seconds=2.0,
                    summary="Try it today",
                    on_screen=["call to action"],
                ),
            ],
        )
    )
    project.save_script(
        ScriptDoc(
            lines=[
                ScriptLine(scene_id="opening", text="first line"),
                ScriptLine(scene_id="opening", text="second line"),
                ScriptLine(scene_id="closing", text="third line"),
            ]
        )
    )
    for stage in project.GATED_STAGES:
        project.record_approval(stage)

    # run_narrate and run_revise read the voice from config/tts.json.
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "tts.json").write_text(
        '{"engine": "kokoro-onnx", "voice": "bf_emma"}\n'
    )
    monkeypatch.chdir(tmp_path)

    tts = KokoroAdapter(cache_dir=project.dir / "audio", engine=FakeEngine())
    run_narrate(project, tts)
    return project, tts


_GOOD_REPLY = {
    "summary": "A sharper opener",
    "seconds": 4,
    "on_screen": ["headline", "subheadline"],
    "text": "revised opener line",
}


def test_revise_updates_scene_and_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The mocked reply replaces the scene and its lines; everything else stands."""
    project, _tts = _seed(tmp_path, monkeypatch)
    sb_before = json.loads((project.dir / "storyboard.json").read_text())
    client = FakeClient(_GOOD_REPLY)

    result = run_revise(project, client, "opening", "make the opener punchier")

    assert result == {
        "scene_id": "opening",
        "summary": "A sharper opener",
        "seconds": 4.0,
        "new_text": "revised opener line",
    }
    sb_after = json.loads((project.dir / "storyboard.json").read_text())
    opening = next(s for s in sb_after["scenes"] if s["id"] == "opening")
    assert opening["summary"] == "A sharper opener"
    assert opening["seconds"] == 4.0
    assert opening["on_screen"] == ["headline", "subheadline"]
    assert opening["kind"] == "title"  # the kind never changes
    closing_before = next(s for s in sb_before["scenes"] if s["id"] == "closing")
    closing_after = next(s for s in sb_after["scenes"] if s["id"] == "closing")
    assert json.dumps(closing_after, sort_keys=True) == json.dumps(closing_before, sort_keys=True)

    script = project.load_script()
    assert [(line.scene_id, line.text) for line in script.lines] == [
        ("opening", "revised opener line"),
        ("closing", "third line"),
    ]
    assert script.lines[0].start_seconds is None
    assert script.lines[0].end_seconds is None
    assert script.lines[1].start_seconds == pytest.approx(3.0)
    assert script.lines[1].end_seconds == pytest.approx(3.5)

    # The prompt embeds the full storyboard, the scene's current lines and
    # the instruction; the system prompt carries the kind's on-screen spec.
    system, user = client.calls[0]
    assert "title" in system
    assert "headline" in system and "subheadline" in system
    assert "closing" in user
    assert "first line" in user and "second line" in user
    assert "make the opener punchier" in user


def test_revise_resets_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """All three approvals are false afterwards, and the output claims it."""
    _project, _tts = _seed(tmp_path, monkeypatch)
    root = tmp_path / "projects"
    monkeypatch.setattr(cli, "LLMClient", lambda: FakeClient(_GOOD_REPLY))

    result = main(
        [
            "revise",
            "--id",
            _PROJECT_ID,
            "--scene",
            "opening",
            "--instruction",
            "tighten the opener",
            "--projects-root",
            str(root),
        ]
    )

    assert result == 0
    project = Project.load(root / _PROJECT_ID)
    for stage in project.GATED_STAGES:
        assert project.is_approved(stage) is False
    out = capsys.readouterr().out
    assert "reset" in out
    assert "storyboard" in out and "duration" in out and "script" in out
    assert "Meet the tool" in out  # old summary
    assert "A sharper opener" in out  # new summary


def test_revise_keeps_other_audio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Untouched lines keep their wavs; the revised scene's stale wavs go."""
    project, tts = _seed(tmp_path, monkeypatch)
    keep_note = project.dir / "audio" / "notes.txt"
    keep_note.write_text("not audio")
    stale_names = [
        tts.cache_path(text, _VOICE).name for text in ("first line", "second line")
    ]
    keep_name = tts.cache_path("third line", _VOICE).name
    client = FakeClient(_GOOD_REPLY)

    run_revise(project, client, "opening", "tighten the opener")

    audio = project.dir / "audio"
    assert (audio / keep_name).exists()
    assert keep_note.exists()  # only *.wav files are ever deleted
    for name in stale_names:
        assert not (audio / name).exists()
    manifest = NarrationDoc.model_validate(
        json.loads((project.dir / "narration.json").read_text())
    )
    assert [line.scene_id for line in manifest.lines] == ["closing"]
    assert manifest.lines[0].file == f"audio/{keep_name}"


def test_revise_unknown_scene_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unknown scene id exits 2 naming the valid ids, with no LLM call."""
    _project, _tts = _seed(tmp_path, monkeypatch)
    root = tmp_path / "projects"
    client = FakeClient(_GOOD_REPLY)
    monkeypatch.setattr(cli, "LLMClient", lambda: client)

    result = main(
        [
            "revise",
            "--id",
            _PROJECT_ID,
            "--scene",
            "ghost",
            "--instruction",
            "tighten",
            "--projects-root",
            str(root),
        ]
    )

    assert result == 2
    err = capsys.readouterr().err
    assert "ghost" in err
    assert "opening" in err and "closing" in err
    assert client.calls == []
    sb = json.loads((root / _PROJECT_ID / "storyboard.json").read_text())
    assert [scene["id"] for scene in sb["scenes"]] == ["opening", "closing"]
    project = Project.load(root / _PROJECT_ID)
    for stage in project.GATED_STAGES:
        assert project.is_approved(stage) is True


def test_revise_on_screen_length_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A wrong on_screen length raises ReviseError; the storyboard is untouched."""
    project, _tts = _seed(tmp_path, monkeypatch)
    sb_bytes = (project.dir / "storyboard.json").read_bytes()
    client = FakeClient({**_GOOD_REPLY, "on_screen": ["only one"]})

    with pytest.raises(ReviseError, match="opening") as exc_info:
        run_revise(project, client, "opening", "tighten")

    message = str(exc_info.value)
    assert "2" in message  # the expected entry count is named
    assert (project.dir / "storyboard.json").read_bytes() == sb_bytes
    for stage in project.GATED_STAGES:
        assert project.is_approved(stage) is True


def test_revise_scene_without_lines_gets_new_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Revising a scene with no script lines still lands the replacement."""
    project, _tts = _seed(tmp_path, monkeypatch)
    project.save_script(ScriptDoc(lines=[ScriptLine(scene_id="closing", text="third line")]))
    client = FakeClient(_GOOD_REPLY)

    run_revise(project, client, "opening", "tighten")

    script = project.load_script()
    assert [(line.scene_id, line.text) for line in script.lines] == [
        ("closing", "third line"),
        ("opening", "revised opener line"),
    ]
