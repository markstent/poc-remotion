"""Tests for the gated render bridge."""

import json
import subprocess

import pytest

from poc_remotion import render as render_module
from poc_remotion.cli import main
from poc_remotion.project import Project
from poc_remotion.render import GateError, RenderOptions, render_video
from poc_remotion.schemas import ScriptDoc, ScriptLine, Storyboard, StoryboardScene


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
