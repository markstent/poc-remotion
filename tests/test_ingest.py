from pathlib import Path

from poc_remotion.ingest import ingest_markdown


def _write(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


MD = "# My Title\n\nintro\n\n## One\n\ntext\n\n## Two\n\ntext\n"


def test_id_is_content_hash(tmp_path: Path) -> None:
    a = ingest_markdown(_write(tmp_path / "a.md", MD))
    b = ingest_markdown(_write(tmp_path / "b.md", MD))
    assert a.id == b.id and len(a.id) == 12


def test_title_from_h1(tmp_path: Path) -> None:
    assert ingest_markdown(_write(tmp_path / "a.md", MD)).title == "My Title"


def test_headings_h2_h3_only(tmp_path: Path) -> None:
    md = MD + "### Three\n\ntext\n#### Four\n\ntext\n"
    assert ingest_markdown(_write(tmp_path / "a.md", md)).headings == ["One", "Two", "Three"]


def test_extraction_note_records_fidelity(tmp_path: Path) -> None:
    assert ingest_markdown(_write(tmp_path / "a.md", MD)).extraction_notes == "full text captured"
