"""Tests for the gated render bridge (fframes renderer)."""

import json
import subprocess
from pathlib import Path

import pytest

from poc_remotion import render as render_module
from poc_remotion.cli import main
from poc_remotion.project import Project
from poc_remotion.render import GateError, render_video
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
    """Build a plain narration.json document from project-relative file paths."""
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


def test_render_builds_expected_command(tmp_path, renderer, fake_render):
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    fake_render()
    out = render_video(p)
    assert out == p.dir / "output" / "video.mp4"
    assert (p.dir / "output" / "video.mp4").exists()


def test_render_runs_cargo_in_renderer_dir(tmp_path, renderer, monkeypatch):
    """The renderer subprocess is cargo, run inside the redirected renderer root."""
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    seen = {}

    def _run(cmd, **kw):
        seen.update(cmd=cmd, kw=kw)
        (renderer / "out.mp4").write_bytes(b"fake mp4")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(render_module, "subprocess_run", _run)
    render_video(p)
    assert seen["cmd"][0].endswith("cargo")
    assert seen["cmd"][1:] == ["run", "--release", "--quiet", "--", "render"]
    assert seen["kw"]["cwd"] == renderer
    cargo_parent = str(render_module._resolve_cargo().parent)
    assert seen["kw"]["env"]["PATH"].startswith(cargo_parent)


def test_render_stages_storyboard_and_narration(tmp_path, renderer, fake_render):
    """The staged data files mirror the saved storyboard and narration."""
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    narration = _narration_doc()
    (p.dir / "narration.json").write_text(json.dumps(narration))
    captured = fake_render()
    render_video(p)

    staged = captured["staged_data"]
    assert staged["storyboard.json"] == p.load_storyboard().model_dump()
    assert staged["narration.json"] == narration
    # Staged data is per-project: it is cleaned up after the render.
    assert list((renderer / "data").glob("*.json")) == []
    assert not (renderer / "out.mp4").exists(), "out.mp4 must be moved into the project"


def test_render_failure_raises_runtime_error_with_stderr_tail(tmp_path, renderer, monkeypatch):
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])

    def _fail(cmd, **kw):
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="cargo: boom")

    monkeypatch.setattr(render_module, "subprocess_run", _fail)
    with pytest.raises(RuntimeError) as e:
        render_video(p)
    assert "boom" in str(e.value)


def test_render_missing_output_raises(tmp_path, renderer, monkeypatch):
    """A zero-exit render that produces no out.mp4 is an error, not a success."""
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])

    def _empty(cmd, **kw):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(render_module, "subprocess_run", _empty)
    with pytest.raises(RuntimeError, match="no output"):
        render_video(p)


def test_cli_render_prints_output_path(tmp_path, renderer, fake_render, capsys):
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    fake_render()
    rc = main(["render", "--id", "demo", "--projects-root", str(tmp_path)])
    assert rc == 0
    assert str(p.dir / "output" / "video.mp4") in capsys.readouterr().out


def test_cli_render_blocked_exits_two(tmp_path, capsys):
    _approved_project(tmp_path, stages=[])
    rc = main(["render", "--id", "demo", "--projects-root", str(tmp_path)])
    assert rc == 2
    assert "storyboard" in capsys.readouterr().err


def test_render_stages_audio_and_fonts(tmp_path, renderer, monkeypatch):
    """Narration audio and brand fonts are staged into media/ before cargo runs."""
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    audio_dir = p.dir / "audio"
    _write_wav(audio_dir / "a.wav")
    _write_wav(audio_dir / "b.wav")
    (p.dir / "narration.json").write_text(
        json.dumps(_narration_doc("audio/a.wav", "audio/b.wav"))
    )
    media = renderer / "media"

    def _run(cmd, **kw):
        staged = sorted(f.name for f in media.iterdir())
        for font in render_module.FONT_FILES:
            assert font in staged, f"{font} not staged before cargo"
        assert "a.wav" in staged and "b.wav" in staged
        (renderer / "out.mp4").write_bytes(b"fake mp4")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(render_module, "subprocess_run", _run)
    render_video(p)

    staged_after = sorted(f.name for f in media.iterdir())
    # Audio is per-project and cleaned up; fonts are stable and stay staged.
    assert "a.wav" not in staged_after and "b.wav" not in staged_after
    for font in render_module.FONT_FILES:
        assert font in staged_after
    # The project's own audio files remain untouched.
    assert (audio_dir / "a.wav").exists() and (audio_dir / "b.wav").exists()


def test_render_without_narration_stages_fonts_only(tmp_path, renderer, fake_render):
    """A project without narration stages fonts and no audio."""
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    fake_render()
    render_video(p)

    staged = sorted(f.name for f in (renderer / "media").iterdir())
    assert staged == sorted(render_module.FONT_FILES)
    assert not (renderer / "data" / "narration.json").exists()


def test_render_empty_narration_lines_stages_no_audio(tmp_path, renderer, fake_render):
    """narration.json with an empty lines list stages nothing but is still passed on."""
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    (p.dir / "narration.json").write_text(json.dumps({"lines": []}))
    captured = fake_render()
    render_video(p)

    staged = [f.name for f in (renderer / "media").iterdir() if f.suffix == ".wav"]
    assert staged == []
    assert captured["staged_data"]["narration.json"] == {"lines": []}


def test_render_malformed_narration_fails_cleanly(tmp_path, renderer, monkeypatch):
    """Unparseable narration.json raises RuntimeError naming the file; cargo skipped."""
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    (p.dir / "narration.json").write_text("{not json")

    def _fail(cmd, **kw):
        raise AssertionError("cargo must not be invoked for malformed narration.json")

    monkeypatch.setattr(render_module, "subprocess_run", _fail)
    with pytest.raises(RuntimeError, match="narration.json"):
        render_video(p)


def test_render_invalid_narration_line_fails_cleanly(tmp_path, renderer, monkeypatch):
    """A narration line missing 'file' fails schema validation naming narration.json."""
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    (p.dir / "narration.json").write_text(
        json.dumps(
            {
                "lines": [
                    {
                        "scene_id": "s1",
                        "text": "line 0",
                        "start_seconds": 0.0,
                        "end_seconds": 1.0,
                    }
                ]
            }
        )
    )

    def _fail(cmd, **kw):
        raise AssertionError("cargo must not be invoked for invalid narration.json")

    monkeypatch.setattr(render_module, "subprocess_run", _fail)
    with pytest.raises(RuntimeError, match="narration.json"):
        render_video(p)


def test_render_missing_narration_audio_fails(tmp_path, renderer, monkeypatch):
    """A narration line referencing a missing file aborts before cargo runs."""
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    (p.dir / "narration.json").write_text(json.dumps(_narration_doc("audio/absent.wav")))

    def _boom(cmd, **kw):
        raise AssertionError("cargo must not be invoked when narration audio is missing")

    monkeypatch.setattr(render_module, "subprocess_run", _boom)
    with pytest.raises(RuntimeError) as e:
        render_video(p)
    assert "absent.wav" in str(e.value)


def test_render_rejects_non_audio_relative_path(tmp_path, renderer, monkeypatch):
    """Narration file paths must be audio/<name>; anything else aborts early."""
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    (p.dir / "narration.json").write_text(json.dumps(_narration_doc("somewhere/b.wav")))

    def _boom(cmd, **kw):
        raise AssertionError("cargo must not be invoked for a non-audio/ file path")

    monkeypatch.setattr(render_module, "subprocess_run", _boom)
    with pytest.raises(RuntimeError, match="audio/<name>"):
        render_video(p)


def test_render_missing_fonts_fails(tmp_path, renderer, monkeypatch):
    """A missing brand-font source aborts before cargo runs."""
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    monkeypatch.setattr(render_module, "FONTS_SOURCE_DIR", tmp_path / "absent-fonts")

    def _boom(cmd, **kw):
        raise AssertionError("cargo must not be invoked when brand fonts are missing")

    monkeypatch.setattr(render_module, "subprocess_run", _boom)
    with pytest.raises(RuntimeError, match="font"):
        render_video(p)


def test_resolve_cargo_prefers_cargo_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CARGO", str(tmp_path / "custom-cargo"))
    assert render_module._resolve_cargo() == tmp_path / "custom-cargo"


def test_resolve_cargo_falls_back_to_rustup_toolchain(tmp_path, monkeypatch):
    """Without PATH or ~/.cargo/bin, any rustup toolchain cargo is used."""
    monkeypatch.delenv("CARGO", raising=False)
    monkeypatch.setattr(render_module.shutil, "which", lambda name: None)
    monkeypatch.setenv("HOME", str(tmp_path))
    toolchain = tmp_path / ".rustup" / "toolchains" / "stable-x" / "bin"
    toolchain.mkdir(parents=True)
    cargo = toolchain / "cargo"
    cargo.write_bytes(b"#!/bin/sh\n")
    cargo.chmod(0o755)
    assert render_module._resolve_cargo() == cargo


def test_resolve_cargo_missing_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("CARGO", raising=False)
    monkeypatch.setattr(render_module.shutil, "which", lambda name: None)
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(RuntimeError, match="cargo not found"):
        render_module._resolve_cargo()
