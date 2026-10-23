"""Tests for SRT sidecar generation and the export-srt CLI command."""

from pathlib import Path

import pytest

from poc_remotion.cli import main
from poc_remotion.project import Project
from poc_remotion.schemas import ScriptDoc, ScriptLine
from poc_remotion.subtitles import srt_from_script


def test_srt_two_timed_lines() -> None:
    """Two timed lines produce two numbered cues with millisecond timecodes."""
    script = ScriptDoc(
        lines=[
            ScriptLine(
                scene_id="s1", text="Hello world.", start_seconds=0.0, end_seconds=1.5
            ),
            ScriptLine(
                scene_id="s2", text="Second cue.", start_seconds=2.0, end_seconds=3.25
            ),
        ]
    )

    srt, skipped = srt_from_script(script)

    assert skipped == 0
    assert srt == (
        "1\n"
        "00:00:00,000 --> 00:00:01,500\n"
        "Hello world.\n"
        "\n"
        "2\n"
        "00:00:02,000 --> 00:00:03,250\n"
        "Second cue.\n"
    )


def test_srt_skips_untimed_and_counts() -> None:
    """A line missing either timing is dropped from the cues and counted."""
    script = ScriptDoc(
        lines=[
            ScriptLine(
                scene_id="s1", text="Hello world.", start_seconds=0.0, end_seconds=1.5
            ),
            ScriptLine(scene_id="s2", text="Untimed."),
        ]
    )

    srt, skipped = srt_from_script(script)

    assert skipped == 1
    assert srt == "1\n00:00:00,000 --> 00:00:01,500\nHello world.\n"


def test_srt_rounds_down_to_ms() -> None:
    """Sub-millisecond tails are truncated: 1.234567 -> 00:00:01,234."""
    script = ScriptDoc(
        lines=[
            ScriptLine(
                scene_id="s1",
                text="Precise.",
                start_seconds=1.234567,
                end_seconds=2.5,
            ),
        ]
    )

    srt, _skipped = srt_from_script(script)

    assert "00:00:01,234 --> 00:00:02,500" in srt


def _seed_script(tmp_path: Path, lines: list[ScriptLine]) -> tuple[Path, Path]:
    """Create a project holding a script; return (projects root, project dir)."""
    root = tmp_path / "projects"
    assert main(["init", "--id", "demo", "--projects-root", str(root)]) == 0
    project = Project.load(root / "demo")
    project.save_script(ScriptDoc(lines=lines))
    return root, project.dir


def test_export_srt_writes_sidecar_and_reports_skips(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """export-srt writes subtitles/<id>.srt, prints the path and the skip count."""
    root, project_dir = _seed_script(
        tmp_path,
        [
            ScriptLine(
                scene_id="s1", text="Hello world.", start_seconds=0.0, end_seconds=1.5
            ),
            ScriptLine(scene_id="s2", text="Untimed."),
        ],
    )

    result = main(["export-srt", "--id", "demo", "--projects-root", str(root)])

    assert result == 0
    out_path = project_dir / "subtitles" / "demo.srt"
    assert out_path.read_text() == "1\n00:00:00,000 --> 00:00:01,500\nHello world.\n"
    out = capsys.readouterr().out
    assert str(out_path) in out
    assert "skipped 1 untimed lines" in out


def test_export_srt_missing_project_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing project exits 2 with the house error message."""
    result = main(
        ["export-srt", "--id", "ghost", "--projects-root", str(tmp_path / "projects")]
    )

    assert result == 2
    assert "manifest.json missing" in capsys.readouterr().err
