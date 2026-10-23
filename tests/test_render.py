"""Tests for the gated render bridge."""

import json
import subprocess
from pathlib import Path

import pytest

from poc_remotion import render as render_module
from poc_remotion.cli import main
from poc_remotion.project import Project
from poc_remotion.render import GateError, RenderOptions, render_video
from poc_remotion.schemas import ScriptDoc, ScriptLine, Storyboard, StoryboardScene


def _write_wav(path: Path, seconds: float = 0.1) -> None:
    """Write a tiny valid mono 16-bit 44.1 kHz wav (for staging tests)."""
    import struct
    import wave

    frames = b"".join(struct.pack("<h", i % 3000) for i in range(int(44100 * seconds)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(frames)


def _narration_doc(*files: str) -> dict:
    """Build a plain narration.json document from public-relative file paths."""
    lines = [
        {
            "scene_id": "s1",
            "text": f"line {i}",
            "start_seconds": float(i),
            "end_seconds": float(i) + 1.0,
            "file": file,
        }
        for i, file in enumerate(files)
    ]
    return {"lines": lines}


def _approved_project(tmp_path, stages):
    """Create a project with storyboard and script saved, approving the given stages."""
    p = Project.create(tmp_path / "demo", "demo")
    p.save_storyboard(
        Storyboard(
            objectives=["o"],
            duration_seconds=10.0,
            rationale="r",
            scenes=[
                StoryboardScene(id="s1", kind="title", purpose="p", seconds=10.0, summary="s")
            ],
        )
    )
    p.save_script(ScriptDoc(lines=[ScriptLine(scene_id="s1", text="hello")]))
    for stage in stages:
        p.record_approval(stage)
    return p


def test_render_blocked_without_gates(tmp_path):
    p = _approved_project(tmp_path, stages=[])  # storyboard+script saved, nothing approved
    with pytest.raises(GateError) as e:
        render_video(p)
    assert "storyboard" in str(e.value)


def test_render_builds_expected_command(tmp_path, monkeypatch):
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    seen = {}

    def _ok():
        (p.dir / "output" / "video.mp4").touch()
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(render_module, "subprocess_run", lambda cmd, **kw: seen.update(cmd=cmd) or _ok())
    out = render_video(p, RenderOptions(scale=0.25))
    cmd = seen["cmd"]
    assert cmd[:3] == ["npx", "remotion", "render"] and "TrainerVideo" in cmd
    assert any(a.startswith("--scale=0.25") for a in cmd)
    assert out == p.dir / "output" / "video.mp4"


def test_render_writes_props_from_project_docs(tmp_path, monkeypatch):
    """The props file passed to Remotion mirrors the saved storyboard and script."""
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    seen = {}

    def _ok():
        (p.dir / "output" / "video.mp4").touch()
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(render_module, "subprocess_run", lambda cmd, **kw: seen.update(cmd=cmd) or _ok())
    render_video(p)

    props = json.loads((p.dir / "output" / "props.json").read_text())
    assert props["storyboard"] == p.load_storyboard().model_dump()
    assert props["script"] == p.load_script().model_dump()
    assert any(a.startswith(f"--props={p.dir / 'output' / 'props.json'}") for a in seen["cmd"])


def test_render_failure_raises_runtime_error_with_stderr_tail(tmp_path, monkeypatch):
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])

    def _fail(cmd, **kw):
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="npx: boom")

    monkeypatch.setattr(render_module, "subprocess_run", _fail)
    with pytest.raises(RuntimeError) as e:
        render_video(p)
    assert "boom" in str(e.value)


def test_cli_render_prints_output_path(tmp_path, monkeypatch, capsys):
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])

    def _ok():
        (p.dir / "output" / "video.mp4").touch()
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(render_module, "subprocess_run", lambda cmd, **kw: _ok())
    rc = main(["render", "--id", "demo", "--projects-root", str(tmp_path)])
    assert rc == 0
    assert str(p.dir / "output" / "video.mp4") in capsys.readouterr().out


def test_cli_render_blocked_exits_two(tmp_path, capsys):
    _approved_project(tmp_path, stages=[])
    rc = main(["render", "--id", "demo", "--projects-root", str(tmp_path)])
    assert rc == 2
    assert "storyboard" in capsys.readouterr().err


def test_render_copies_audio_to_public(tmp_path, monkeypatch):
    """Narration audio is staged into public/audio for npx, then removed."""
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    audio_dir = p.dir / "audio"
    _write_wav(audio_dir / "a.wav")
    _write_wav(audio_dir / "b.wav")
    (p.dir / "narration.json").write_text(
        json.dumps(_narration_doc("audio/a.wav", "audio/b.wav"))
    )
    public_audio = render_module.REMOTION_DIR / "public" / "audio"
    # Clear any stale staged files so the pre-render assertions are meaningful.
    for name in ("a.wav", "b.wav"):
        (public_audio / name).unlink(missing_ok=True)

    def _ok(cmd, **kw):
        assert (public_audio / "a.wav").exists(), "a.wav not staged before npx"
        assert (public_audio / "b.wav").exists(), "b.wav not staged before npx"
        (p.dir / "output" / "video.mp4").touch()
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(render_module, "subprocess_run", _ok)
    render_video(p)

    assert not (public_audio / "a.wav").exists(), "staged a.wav not cleaned up"
    assert not (public_audio / "b.wav").exists(), "staged b.wav not cleaned up"
    # The project's own audio files remain untouched.
    assert (audio_dir / "a.wav").exists() and (audio_dir / "b.wav").exists()
    props = json.loads((p.dir / "output" / "props.json").read_text())
    assert props["narration"]["lines"][1]["file"] == "audio/b.wav"


def test_render_without_audio_touches_nothing(tmp_path, monkeypatch):
    """A project without narration leaves public/audio exactly as it was."""
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    public_audio = render_module.REMOTION_DIR / "public" / "audio"
    existed_before = public_audio.exists()
    before = sorted(f.name for f in public_audio.iterdir()) if existed_before else None

    def _ok(cmd, **kw):
        (p.dir / "output" / "video.mp4").touch()
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(render_module, "subprocess_run", _ok)
    render_video(p)

    if existed_before:
        assert sorted(f.name for f in public_audio.iterdir()) == before
    else:
        assert not public_audio.exists()


def test_render_missing_narration_audio_fails(tmp_path, monkeypatch):
    """A narration line referencing a missing file aborts before npx runs."""
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    (p.dir / "narration.json").write_text(json.dumps(_narration_doc("audio/absent.wav")))

    def _boom(cmd, **kw):
        raise AssertionError("npx must not be invoked when narration audio is missing")

    monkeypatch.setattr(render_module, "subprocess_run", _boom)
    with pytest.raises(RuntimeError) as e:
        render_video(p)
    assert "absent.wav" in str(e.value)
