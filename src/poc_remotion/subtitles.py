"""SRT sidecar generation from a timed narration script."""

from poc_remotion.schemas import ScriptDoc


def _timecode(seconds: float) -> str:
    """Format seconds as an SRT timecode ``HH:MM:SS,mmm``.

    Milliseconds are truncated so sub-millisecond float tails never round a
    cue up past its real audio.
    """
    total_ms = int(seconds * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def srt_from_script(script: ScriptDoc) -> tuple[str, int]:
    """Render timed script lines as SRT; return ``(srt text, skipped count)``.

    Lines missing either timing are skipped and counted, never emitted as
    zero-length cues. Cues are numbered from 1 and separated by a blank line.
    """
    blocks: list[str] = []
    skipped = 0
    for line in script.lines:
        if line.start_seconds is None or line.end_seconds is None:
            skipped += 1
            continue
        blocks.append(
            f"{len(blocks) + 1}\n"
            f"{_timecode(line.start_seconds)} --> {_timecode(line.end_seconds)}\n"
            f"{line.text}\n"
        )
    return "\n".join(blocks), skipped
