"""Narration pass: per-line synthesis and audio-true timing rewrite."""

import json

from poc_remotion.project import Project
from poc_remotion.schemas import NarrationDoc, NarrationLine, ScriptDoc, Storyboard
from poc_remotion.subtitles import chunk_line
from poc_remotion.tts import KokoroAdapter, TtsResult, load_tts_config

NARRATION_GAP = 0.35  # seconds inserted between scenes
LINE_GAP = 0.15  # seconds inserted between lines in a scene
SCENE_TAIL = 0.3  # seconds a scene extends past its last line


class NarrateError(Exception):
    """Raised when the narration pass cannot complete."""


def _synthesize_all(
    project: Project, script: ScriptDoc, tts: KokoroAdapter, voice: str
) -> list[TtsResult]:
    """Synthesise every line before any project JSON is rewritten.

    The adapter's content-addressed cache decides the final file location;
    the ``out_path`` argument exists for signature symmetry.
    """
    results: list[TtsResult] = []
    for i, line in enumerate(script.lines):
        try:
            results.append(
                tts.synthesize(line.text, voice, project.dir / "audio" / f"line-{i}.wav")
            )
        except Exception as exc:
            raise NarrateError(
                f"script line {i + 1} (scene {line.scene_id}): synthesis failed: {exc}"
            ) from exc
    return results


def _compute_timings(
    script: ScriptDoc, sb: Storyboard, durations: list[float]
) -> tuple[list[float], list[float], dict[str, float], float]:
    """Place every line after its real audio, scene by scene in plan order.

    The measured audio drives the timeline: each scene starts NARRATION_GAP
    after the previous scene's last line ends (the storyboard's planned
    seconds are a pre-narration estimate and never stretch the video). Line
    starts stack each previous duration plus LINE_GAP. Every scene's span
    but the last reaches exactly to its successor's start, carrying the
    narration gap inside the span, so the spans sum to the total and the
    composition's packed (contiguous) timeline matches these absolute
    times. The last scene's span ends at its last line plus SCENE_TAIL,
    and the new total is the final line end plus SCENE_TAIL. Returns line
    starts, line ends, spans by scene id, and the total. Requires at least
    one scene and no empty scenes.
    """
    starts = [0.0] * len(script.lines)
    ends = [0.0] * len(script.lines)
    spans: dict[str, float] = {}
    prev_end: float | None = None
    last_line_end = 0.0

    for si, scene in enumerate(sb.scenes):
        indices = [i for i, line in enumerate(script.lines) if line.scene_id == scene.id]
        scene_start = 0.0 if prev_end is None else prev_end + NARRATION_GAP
        last_end = scene_start
        for k, i in enumerate(indices):
            start = scene_start + sum(durations[j] for j in indices[:k]) + LINE_GAP * k
            end = start + durations[i]
            starts[i] = start
            ends[i] = end
            last_end = end
        if si + 1 < len(sb.scenes):
            # Carry the gap to the next scene: the composition packs scenes
            # contiguously, so this scene's span must reach its successor's
            # start exactly or later audio falls outside the timeline.
            spans[scene.id] = last_end + NARRATION_GAP - scene_start
        else:
            spans[scene.id] = last_end - scene_start + SCENE_TAIL
        prev_end = last_end
        last_line_end = last_end

    return starts, ends, spans, last_line_end + SCENE_TAIL


def run_narrate(project: Project, tts: KokoroAdapter) -> dict[str, float | int]:
    """Synthesise every script line and rewrite timings from the real audio.

    Phase one synthesises all lines through the adapter cache; any engine
    failure raises NarrateError naming the line before any project JSON
    changes. Phase two computes the timing pass and rewrites script.json,
    storyboard.json and narration.json in a single write phase: each line
    gains start_seconds and end_seconds, each scene's seconds becomes its
    audio span, and duration_seconds becomes the last line end plus
    SCENE_TAIL. narration.json holds ``{"lines": [...]}`` with each line's
    public-relative audio path for the composition. Approvals
    are untouched: timing is not a content change. Returns a summary dict
    ``{total_seconds, lines, audio_files}``.

    Scene starts are rerun-stable: every span carries its gap to the next
    scene, so a rerun's cumulative plan reproduces the previous run's
    absolute starts exactly.
    """
    missing = [stage for stage in project.GATED_STAGES if not project.is_approved(stage)]
    if missing:
        raise NarrateError(
            "narration requires all gates approved; not approved: " + ", ".join(missing)
        )

    script = project.load_script()
    sb = project.load_storyboard()
    if not sb.scenes:
        raise NarrateError("storyboard has no scenes to narrate")
    if not script.lines:
        raise NarrateError("script has no lines to narrate")
    known = {scene.id for scene in sb.scenes}
    unknown = sorted({line.scene_id for line in script.lines} - known)
    if unknown:
        raise NarrateError(f"script references unknown scenes: {', '.join(unknown)}")
    empty = [scene.id for scene in sb.scenes if not any(
        line.scene_id == scene.id for line in script.lines
    )]
    if empty:
        raise NarrateError(
            f"storyboard scene with no script lines: {', '.join(empty)}"
        )

    # R-C1: the CLI layer owns the config; the adapter only receives the
    # voice per synthesize call and never reads the config itself.
    voice = load_tts_config().voice

    results = _synthesize_all(project, script, tts, voice)
    durations = [result.duration_seconds for result in results]
    starts, ends, spans, total = _compute_timings(script, sb, durations)

    timed = script.model_copy(deep=True)
    for i, line in enumerate(timed.lines):
        line.start_seconds = starts[i]
        line.end_seconds = ends[i]

    respanned = sb.model_copy(deep=True)
    for scene in respanned.scenes:
        scene.seconds = spans[scene.id]
    respanned.duration_seconds = total

    manifest = NarrationDoc(
        lines=[
            NarrationLine(
                scene_id=line.scene_id,
                text=line.text,
                start_seconds=starts[i],
                end_seconds=ends[i],
                file=f"audio/{tts.cache_path(line.text, voice).name}",
                cues=chunk_line(line.text, starts[i], ends[i]),
            )
            for i, line in enumerate(script.lines)
        ]
    )

    project.save_script(timed)
    project.save_storyboard(respanned)
    (project.dir / "narration.json").write_text(
        json.dumps(manifest.model_dump(), indent=2) + "\n", encoding="utf-8"
    )

    return {"total_seconds": total, "lines": len(script.lines), "audio_files": len(results)}
