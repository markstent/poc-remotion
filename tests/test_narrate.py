"""Tests for the narration pass with audio-true timings."""

import json
import wave
from pathlib import Path

import pytest

from poc_remotion import cli
from poc_remotion.cli import main
from poc_remotion.narrate import (
    LINE_GAP,
    NARRATION_GAP,
    SCENE_TAIL,
    NarrateError,
    run_narrate,
)
from poc_remotion.project import Project
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


class FakeEngine:
    """Test double: writes a valid wav with a per-text duration, and can fail."""

    def __init__(self, durations: dict[str, float], fail_on: str | None = None) -> None:
        self._durations = durations
        self._fail_on = fail_on
        self.calls: list[str] = []

    def synthesize(self, text: str, voice: str, out_path: Path) -> None:
        self.calls.append(text)
        if text == self._fail_on:
            raise RuntimeError("engine exploded")
        frames = round(self._durations[text] * 44100)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(out_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(44100)
            wav.writeframes(b"\x00\x00" * frames)


def _seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    approved: bool = True,
    lines: list[tuple[str, str]] | None = None,
    durations: dict[str, float] | None = None,
    duration_minutes: float | None = None,
    fail_on: str | None = None,
    seconds: tuple[float, float] = (3.0, 2.0),
) -> tuple[Project, KokoroAdapter, FakeEngine, Path]:
    """Seed a gated project and a fake-engine adapter scoped to its audio dir."""
    root = tmp_path / "projects"
    assert main(["init", "--id", _PROJECT_ID, "--projects-root", str(root)]) == 0
    project = Project.load(root / _PROJECT_ID)
    project.save_brief(
        Brief(
            audience="New hires",
            objectives=["Teach the workflow"],
            tone="Light",
            duration_minutes=duration_minutes,
        )
    )
    scenes = [
        StoryboardScene(
            id="opening",
            kind="title",
            purpose="Opener",
            seconds=seconds[0],
            summary="Meet the tool",
            on_screen=["headline", "subheadline"],
        ),
        StoryboardScene(
            id="closing",
            kind="outro",
            purpose="Closer",
            seconds=seconds[1],
            summary="Try it today",
            on_screen=["call to action"],
        ),
    ]
    project.save_storyboard(
        Storyboard(
            objectives=["Teach the workflow"],
            duration_seconds=5.0,
            rationale="Planned pacing.",
            scenes=scenes,
        )
    )
    if lines is None:
        lines = [("opening", "first line"), ("opening", "second line"), ("closing", "third line")]
    project.save_script(
        ScriptDoc(lines=[ScriptLine(scene_id=scene_id, text=text) for scene_id, text in lines])
    )
    if approved:
        for stage in project.GATED_STAGES:
            project.record_approval(stage)

    # run_narrate reads the voice from config/tts.json relative to the cwd.
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "tts.json").write_text(
        '{"engine": "kokoro-onnx", "voice": "bf_emma"}\n'
    )
    monkeypatch.chdir(tmp_path)

    texts = [text for _, text in lines]
    if durations is None:
        durations = {text: 0.5 for text in texts}
    engine = FakeEngine(durations, fail_on=fail_on)
    tts = KokoroAdapter(cache_dir=project.dir / "audio", engine=engine)
    return project, tts, engine, root


def test_narrate_produces_timings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Line starts and ends follow the gap rules; scene seconds equal the span."""
    project, tts, engine, _root = _seed(tmp_path, monkeypatch)

    summary = run_narrate(project, tts)

    assert (LINE_GAP, NARRATION_GAP, SCENE_TAIL) == (0.15, 0.35, 0.3)
    script = project.load_script()
    starts = [line.start_seconds for line in script.lines]
    ends = [line.end_seconds for line in script.lines]
    # Scene opening starts at its planned 0.0; line 1 sits after 0.5s of
    # audio plus the line gap; closing starts at its planned 3.0 because
    # the plan (3.0) beats the previous end plus the narration gap (1.5).
    assert starts == pytest.approx([0.0, 0.65, 3.0])
    assert ends == pytest.approx([0.5, 1.15, 3.5])
    sb = project.load_storyboard()
    # Span = last line end - scene start + tail: 1.15 + 0.3 and 0.5 + 0.3.
    assert [scene.seconds for scene in sb.scenes] == pytest.approx([1.45, 0.8])
    assert sb.duration_seconds == pytest.approx(3.8)
    assert summary["total_seconds"] == pytest.approx(3.8)
    assert summary["lines"] == 3
    assert summary["audio_files"] == 3
    assert len(list((project.dir / "audio").glob("*.wav"))) == 3
    assert len(engine.calls) == 3


def test_narrate_preserves_approvals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Timing is not a content change: approvals survive the rewrite byte for byte."""
    project, tts, _engine, _root = _seed(tmp_path, monkeypatch)
    before = (project.dir / "approvals.json").read_bytes()

    run_narrate(project, tts)

    assert (project.dir / "approvals.json").read_bytes() == before
    assert project.all_approved()
    # Only timings changed; the narration text is untouched.
    script = project.load_script()
    assert [line.text for line in script.lines] == ["first line", "second line", "third line"]


def test_narrate_requires_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Gates not approved: exit 2 with every unapproved gate named, no synthesis."""
    _project, _tts, engine, root = _seed(tmp_path, monkeypatch, approved=False)
    monkeypatch.setattr(
        cli,
        "KokoroAdapter",
        lambda cache_dir: KokoroAdapter(cache_dir=cache_dir, engine=engine),
    )

    result = main(["narrate", "--id", _PROJECT_ID, "--projects-root", str(root)])

    assert result == 2
    err = capsys.readouterr().err
    assert "storyboard" in err
    assert "duration" in err
    assert "script" in err
    assert engine.calls == []


def test_narrate_long_audio_grows_scene(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """40s of audio in a 3s scene grows the scene; the CLI reports the new total."""
    project, _tts, engine, root = _seed(
        tmp_path,
        monkeypatch,
        durations={"first line": 40.0, "second line": 0.5, "third line": 0.5},
        duration_minutes=5,
    )
    monkeypatch.setattr(
        cli,
        "KokoroAdapter",
        lambda cache_dir: KokoroAdapter(cache_dir=cache_dir, engine=engine),
    )

    result = main(["narrate", "--id", _PROJECT_ID, "--projects-root", str(root)])

    assert result == 0
    sb = project.load_storyboard()
    # The 3s scene grew to fit both lines (40.0s + gap + 0.5s, ending at
    # 40.65) plus the tail.
    assert sb.scenes[0].seconds == pytest.approx(40.95)
    script = project.load_script()
    # The next scene is pushed past the overrun (40.65 + gap), never clipped.
    assert script.lines[2].start_seconds == pytest.approx(41.0)
    assert sb.duration_seconds == pytest.approx(41.8)
    out = capsys.readouterr().out
    assert "40.95" in out
    assert "41.80" in out
    # 41.8s sits far outside the 5 minute target window: warned, not failed.
    assert "warning" in out


def test_narrate_skips_warning_without_duration_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No brief duration target: no window warning is printed."""
    _project, _tts, engine, root = _seed(
        tmp_path,
        monkeypatch,
        durations={"first line": 40.0, "second line": 0.5, "third line": 0.5},
        duration_minutes=None,
    )
    monkeypatch.setattr(
        cli,
        "KokoroAdapter",
        lambda cache_dir: KokoroAdapter(cache_dir=cache_dir, engine=engine),
    )

    result = main(["narrate", "--id", _PROJECT_ID, "--projects-root", str(root)])

    assert result == 0
    assert "warning" not in capsys.readouterr().out


def test_narrate_unknown_scene_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A script line naming an unknown scene id fails before any synthesis."""
    project, tts, engine, _root = _seed(
        tmp_path,
        monkeypatch,
        lines=[("opening", "first line"), ("ghost", "orphan line")],
    )

    with pytest.raises(NarrateError, match="ghost"):
        run_narrate(project, tts)

    assert engine.calls == []


def test_narrate_engine_failure_leaves_project_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An engine failure on line 2 names the line and rewrites no JSON."""
    project, tts, engine, _root = _seed(tmp_path, monkeypatch, fail_on="second line")
    script_bytes = (project.dir / "script.json").read_bytes()
    sb_bytes = (project.dir / "storyboard.json").read_bytes()
    script_mtime = (project.dir / "script.json").stat().st_mtime_ns
    sb_mtime = (project.dir / "storyboard.json").stat().st_mtime_ns

    with pytest.raises(NarrateError, match=r"script line 2 .*synthesis failed"):
        run_narrate(project, tts)

    assert (project.dir / "script.json").read_bytes() == script_bytes
    assert (project.dir / "storyboard.json").read_bytes() == sb_bytes
    assert (project.dir / "script.json").stat().st_mtime_ns == script_mtime
    assert (project.dir / "storyboard.json").stat().st_mtime_ns == sb_mtime
    assert engine.calls == ["first line", "second line"]


def test_narrate_writes_narration_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """narration.json mirrors the timed script with public audio-relative files."""
    project, tts, _engine, _root = _seed(tmp_path, monkeypatch)

    run_narrate(project, tts)

    manifest_path = project.dir / "narration.json"
    assert manifest_path.exists()
    doc = NarrationDoc.model_validate(json.loads(manifest_path.read_text()))
    script = project.load_script()
    assert len(doc.lines) == len(script.lines) == 3
    for line, nline in zip(script.lines, doc.lines):
        assert nline.scene_id == line.scene_id
        assert nline.text == line.text
        assert nline.start_seconds == line.start_seconds
        assert nline.end_seconds == line.end_seconds
        assert nline.file == f"audio/{tts.cache_path(line.text, 'bf_emma').name}"


def test_narrate_second_run_is_noop_for_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The content-addressed cache means a rerun synthesises nothing new.

    The scenario is audio-dominated (scene plan 0.5s against 0.5s of audio),
    matching a project narrated straight after draft-script: audio spans
    drive every scene start, so the recomputed plan reproduces run 1 exactly.
    """
    project, tts, engine, _root = _seed(
        tmp_path,
        monkeypatch,
        lines=[("opening", "first line")],
        seconds=(0.5, 0.5),
    )

    first = run_narrate(project, tts)
    script_after_first = (project.dir / "script.json").read_bytes()
    second = run_narrate(project, tts)

    assert len(engine.calls) == 1
    assert (project.dir / "script.json").read_bytes() == script_after_first
    assert second == first
