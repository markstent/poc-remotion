"""Tests for SRT sidecar generation and the export-srt CLI command."""

import itertools
from pathlib import Path

import pytest

from poc_remotion.cli import main
from poc_remotion.project import Project
from poc_remotion.schemas import ScriptDoc, ScriptLine
from poc_remotion.subtitles import chunk_line, srt_from_script


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


def test_chunk_line_short_text_single_cue() -> None:
    """A short line becomes one cue covering the whole audio window."""
    cues = chunk_line("Hello world.", 0.0, 10.0)

    assert [(c.text, c.start_seconds, c.end_seconds) for c in cues] == [
        ("Hello world.", 0.0, 10.0)
    ]


def test_chunk_line_long_text_chunks_at_word_cap() -> None:
    """A long sentence hard-splits at 12 words; timing is proportional and contiguous."""
    text = " ".join(f"word{n}" for n in range(30)) + "."
    cues = chunk_line(text, 0.0, 12.0)

    assert [len(c.text.split()) for c in cues] == [12, 12, 6]
    assert " ".join(c.text for c in cues).split() == text.split()
    assert cues[0].start_seconds == 0.0
    assert cues[-1].end_seconds == 12.0
    for earlier, later in itertools.pairwise(cues):
        assert later.start_seconds == earlier.end_seconds
    # Word-proportional durations: 12 words takes twice as long as 6.
    assert cues[0].end_seconds == pytest.approx(4.8)
    assert cues[2].start_seconds == pytest.approx(9.6)


def test_chunk_line_prefers_sentence_and_clause_breaks() -> None:
    """Chunking breaks at sentences and clauses before hard word splits."""
    text = (
        "Clarity wins. When you write a prompt, give the model a clear goal, "
        "plenty of context, and a source to draw from. Then state expectations."
    )
    cues = chunk_line(text, 0.0, 30.0)

    assert sum(len(c.text.split()) for c in cues) == len(text.split())
    assert all(len(c.text.split()) <= 12 for c in cues)
    assert " ".join(c.text for c in cues).split() == text.split()
    # Short sentences merge together, but no cue ever breaks mid-sentence or
    # mid-clause: every cue ends on sentence or clause punctuation.
    assert cues[0].text == "Clarity wins. When you write a prompt,"
    for cue in cues:
        assert cue.text.endswith((".", "!", "?", ";", ",", ":"))
    assert cues[0].start_seconds == 0.0
    assert cues[-1].end_seconds == 30.0
    for earlier, later in itertools.pairwise(cues):
        assert later.start_seconds == earlier.end_seconds


def test_srt_emits_one_block_per_cue() -> None:
    """A long timed line produces several short cues, not one giant block."""
    text = " ".join(f"word{n}" for n in range(20)) + "."
    script = ScriptDoc(
        lines=[ScriptLine(scene_id="s1", text=text, start_seconds=0.0, end_seconds=4.0)]
    )

    srt, skipped = srt_from_script(script)

    assert skipped == 0
    assert srt == (
        "1\n"
        "00:00:00,000 --> 00:00:02,400\n"
        "word0 word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11\n"
        "\n"
        "2\n"
        "00:00:02,400 --> 00:00:04,000\n"
        "word12 word13 word14 word15 word16 word17 word18 word19.\n"
    )
