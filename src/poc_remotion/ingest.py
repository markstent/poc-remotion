import hashlib
import re
from pathlib import Path

from .schemas import SourceRef


def ingest_markdown(path: Path) -> SourceRef:
    """Ingest a markdown file and return a SourceRef.

    Args:
        path: Path to the markdown file.

    Returns:
        SourceRef with content-hash id, title, headings and metadata.
    """
    bytes_data = path.read_bytes()
    sha256_full = hashlib.sha256(bytes_data).hexdigest()
    content_id = sha256_full[:12]

    text = bytes_data.decode("utf-8-sig")
    lines = text.split("\n")

    title = ""
    headings: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not title and stripped.startswith("# "):
            title = stripped[2:].strip()
        elif stripped.startswith("## "):
            headings.append(stripped[3:].strip())
        elif stripped.startswith("### "):
            heading_text = stripped[4:].strip()
            # Strip markdown markup from heading text
            heading_text = re.sub(r"[#*_\[\]]", "", heading_text)
            heading_text = heading_text.strip()
            if heading_text:
                headings.append(heading_text)

    if not title:
        title = path.stem

    return SourceRef(
        id=content_id,
        title=title,
        path=str(path.absolute()),
        kind="markdown",
        sha256=sha256_full,
        headings=headings,
        extraction_notes="full text captured",
    )
