"""Tests for the export bundle."""

import subprocess
from pathlib import Path

import pytest

from poc_remotion import render as render_module
from poc_remotion.cli import REPO_ROOT, main
from poc_remotion.export import ExportError, run_export
from poc_remotion.project import Project
from poc_remotion.schemas import (
    Claim,
    ScriptDoc,
    ScriptLine,
    SourceRef,
    Storyboard,
    StoryboardScene,
)
from poc_remotion.subtitles import srt_from_script

BUNDLE_FILES = [
    "brand.json",
    "claims.json",
    "demo.srt",
    "manifest.json",
    "script.json",
    "sources.json",
    "storyboard.json",
    "tts.json",
    "video.mp4",
]


def _full_project(tmp_path: Path) -> Project:
    """Create a gated project with a timed script, sources and claims."""
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
    p.save_script(
        ScriptDoc(
            lines=[
                ScriptLine(scene_id="s1", text="hello", start_seconds=0.0, end_seconds=2.0)
            ]
        )
    )
    p.save_sources(
        [
            SourceRef(
                id="src-1", title="Guide", path="guide.md", kind="markdown", sha256="0" * 64
            )
        ]
    )
    p.save_claims(
        [Claim(id="claim-1-1", text="A fact.", source_ids=["src-1"], status="supported")]
    )
    for stage in Project.GATED_STAGES:
        p.record_approval(stage)
    return p


def _fake_render(monkeypatch: pytest.MonkeyPatch, project: Project) -> list[list[str]]:
    """Replace npx with a stub that leaves a video.mp4 in place and captures commands."""
    captured: list[list[str]] = []

    def _ok(cmd, **kw):
        captured.append(cmd)
        (project.dir / "output" / "video.mp4").touch()
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(render_module, "subprocess_run", _ok)
    return captured


def _boom_render(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace npx with a stub that fails the test if it is ever invoked."""

    def _boom(cmd, **kw):
        raise AssertionError("npx must not be invoked")

    monkeypatch.setattr(render_module, "subprocess_run", _boom)


def test_export_bundle_complete(tmp_path, monkeypatch, capsys):
    """A gated, timed project exports a bundle with exactly the nine files."""
    p = _full_project(tmp_path)
    captured = _fake_render(monkeypatch, p)

    bundle = run_export(p, scale=2.0)

    assert bundle == p.dir / "output" / "bundle"
    assert sorted(f.name for f in bundle.iterdir()) == BUNDLE_FILES
    assert any(a == "--scale=2.0" for a in captured[0])
    srt, skipped = srt_from_script(p.load_script())
    assert skipped == 0
    assert (bundle / "demo.srt").read_text() == srt
    assert (bundle / "brand.json").read_bytes() == (REPO_ROOT / "brand/brand.json").read_bytes()
    assert (bundle / "tts.json").read_bytes() == (REPO_ROOT / "config/tts.json").read_bytes()
    assert (bundle / "video.mp4").exists()

    # Re-export is clean: a stale file in the bundle does not survive.
    (bundle / "stale.txt").write_text("stale")

    rc = main(["export", "--id", "demo", "--projects-root", str(tmp_path)])

    assert rc == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == str(bundle)
    assert lines[1:] == BUNDLE_FILES


def test_export_requires_timed_script(tmp_path, monkeypatch, capsys):
    """Untimed script lines block export; the message names the count and narrate."""
    p = _full_project(tmp_path)
    untimed = p.load_script()
    untimed.lines[0].start_seconds = None
    untimed.lines[0].end_seconds = None
    p.save_script(untimed)
    _boom_render(monkeypatch)

    with pytest.raises(ExportError) as e:
        run_export(p)
    assert "1 script line(s) untimed" in str(e.value)
    assert "narrate" in str(e.value)
    assert not (p.dir / "output" / "bundle").exists()

    rc = main(["export", "--id", "demo", "--projects-root", str(tmp_path)])
    assert rc == 2
    assert "narrate" in capsys.readouterr().err


def test_export_requires_gates(tmp_path, monkeypatch, capsys):
    """Unapproved gates block export first, even when lines are also untimed."""
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
    # Untimed on purpose: the gates message must still win.
    p.save_script(
        ScriptDoc(
            lines=[
                ScriptLine(scene_id="s1", text="hello", start_seconds=0.0, end_seconds=2.0)
            ]
        )
    )
    _boom_render(monkeypatch)

    with pytest.raises(ExportError) as e:
        run_export(p)
    assert "storyboard" in str(e.value)
    assert "duration" in str(e.value)
    assert "script" in str(e.value)
    assert not (p.dir / "output" / "bundle").exists()

    rc = main(["export", "--id", "demo", "--projects-root", str(tmp_path)])
    assert rc == 2
    assert "storyboard" in capsys.readouterr().err
