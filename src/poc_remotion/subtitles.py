"""SRT sidecar generation and caption cue chunking from a timed script."""

import re

from poc_remotion.schemas import Cue, ScriptDoc

MAX_CUE_WORDS = 12

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_CLAUSE_SPLIT = re.compile(r"(?<=[;:,])\s+")


def _atomic_segments(text: str) -> list[str]:
    """Split text into pieces of at most MAX_CUE_WORDS words each.

    Breaks at sentence ends first, then clause punctuation, then hard word
    boundaries, so captions never exceed one comfortable pill.
    """
    pieces: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(text.strip()):
        clauses = _CLAUSE_SPLIT.split(sentence) if sentence else []
        for clause in clauses or [sentence]:
            words = clause.split()
            for start in range(0, len(words), MAX_CUE_WORDS):
                pieces.append(" ".join(words[start : start + MAX_CUE_WORDS]))
    return [piece for piece in pieces if piece]


def chunk_line(text: str, start_seconds: float, end_seconds: float) -> list[Cue]:
    """Carve a timed narration line into short cues for captions and SRT.

    Segments merge greedily back up to the word cap (so short sentences do
    not become one-word captions), then each cue's duration is its share of
    the line's word count across the audio window. Cues are contiguous and
    cover the window exactly.
    """
    merged: list[str] = []
    for piece in _atomic_segments(text):
        if merged and len((merged[-1] + " " + piece).split()) <= MAX_CUE_WORDS:
            merged[-1] = f"{merged[-1]} {piece}"
        else:
            merged.append(piece)

    counts = [len(segment.split()) for segment in merged]
    total_words = sum(counts)
    span = end_seconds - start_seconds
    cursor = start_seconds
    cues: list[Cue] = []
    for index, (segment, count) in enumerate(zip(merged, counts, strict=True)):
        # The final cue ends exactly on the window end so float accumulation
        # never pushes a caption past its audio.
        end = end_seconds if index == len(merged) - 1 else cursor + span * count / total_words
        cues.append(Cue(text=segment, start_seconds=cursor, end_seconds=end))
        cursor = end
    return cues


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
    zero-length cues. Long lines are chunked into short caption cues, one
    SRT block per cue. Cues are numbered from 1 and separated by a blank
    line.
    """
    blocks: list[str] = []
    skipped = 0
    for line in script.lines:
        if line.start_seconds is None or line.end_seconds is None:
            skipped += 1
            continue
        for cue in chunk_line(line.text, line.start_seconds, line.end_seconds):
            blocks.append(
                f"{len(blocks) + 1}\n"
                f"{_timecode(cue.start_seconds)} --> {_timecode(cue.end_seconds)}\n"
                f"{cue.text}\n"
            )
    return "\n".join(blocks), skipped
