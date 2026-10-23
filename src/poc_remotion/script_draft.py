"""Model-drafted narration script behind the storyboard gates."""

from poc_remotion.discovery import DraftError
from poc_remotion.llm import LLMClient
from poc_remotion.project import Project
from poc_remotion.schemas import Brief, ScriptDoc, ScriptLine, Storyboard
from poc_remotion.storyboard import SCENE_ON_SCREEN_SPEC

WORD_COUNT_TOLERANCE = 0.35
_WORDS_PER_MINUTE = 150

_GATES_MESSAGE = "approve the storyboard and duration gates first"


def _system_prompt() -> str:
    spec = "\n".join(f"- {kind}: {', '.join(fields)}" for kind, fields in SCENE_ON_SCREEN_SPEC.items())
    return (
        "You write the spoken narration script for a training video whose "
        "storyboard is already approved. Each storyboard kind renders a fixed "
        "on-screen contract, so write only what the presenter says:\n"
        f"{spec}\n\n"
        "Style: conversational British narration, light and witty, one to "
        "three sentences per scene. Do not invent facts beyond the scene "
        "summaries.\n\n"
        "Answer with JSON of the form "
        '{"lines": [{"scene_id": "...", "text": "..."}]}. '
        "Use exactly the storyboard's scene ids and write at least one line "
        "for every scene. Do not add start_seconds or end_seconds."
    )


def _user_prompt(sb: Storyboard, brief: Brief) -> str:
    duration = (
        "unspecified" if brief.duration_minutes is None else f"{brief.duration_minutes:g} minutes"
    )
    objectives = "\n".join(f"- {o}" for o in brief.objectives) if brief.objectives else "- none"
    scenes = "\n".join(
        f"- {scene.id} ({scene.kind}, {scene.seconds:g}s): {scene.summary}"
        for scene in sb.scenes
    )
    return (
        f"Audience: {brief.audience}\n"
        f"Objectives:\n{objectives}\n"
        f"Tone: {brief.tone}\n"
        f"Duration target: {duration}\n\n"
        f"Approved storyboard ({sb.duration_seconds:g} seconds total):\n{scenes}\n\n"
        "Write the narration lines for every scene."
    )


def _check_scene_ids(sb: Storyboard, lines: list[ScriptLine]) -> None:
    scene_ids = {scene.id for scene in sb.scenes}
    missing = [
        scene.id
        for scene in sb.scenes
        if not any(line.scene_id == scene.id for line in lines)
    ]
    if missing:
        raise DraftError(f"no narration lines for scene ids: {', '.join(missing)}")
    unknown = [line.scene_id for line in lines if line.scene_id not in scene_ids]
    if unknown:
        raise DraftError(f"unknown scene id in script: {unknown[0]}")


def _check_no_timings(lines: list[ScriptLine]) -> None:
    for line in lines:
        if line.start_seconds is not None or line.end_seconds is not None:
            raise DraftError(
                f"scene {line.scene_id}: script lines must not carry timings"
            )


def _word_count(lines: list[ScriptLine]) -> int:
    return sum(len(line.text.split()) for line in lines)


def _check_word_count(sb: Storyboard, lines: list[ScriptLine]) -> None:
    target = sb.duration_seconds / 60 * _WORDS_PER_MINUTE
    actual = _word_count(lines)
    if abs(actual - target) > WORD_COUNT_TOLERANCE * target:
        low = target * (1 - WORD_COUNT_TOLERANCE)
        high = target * (1 + WORD_COUNT_TOLERANCE)
        raise DraftError(
            f"narration is {actual} words, outside the "
            f"{WORD_COUNT_TOLERANCE:g} tolerance window around the "
            f"{target:g} word target (allowed {low:g} to {high:g} words)"
        )


def run_script(project: Project, client: LLMClient) -> ScriptDoc:
    """Draft the narration script from the approved storyboard.

    Prerequisites run before any LLM call: the storyboard and duration
    gates must both be approved. The model reply is parsed into a ScriptDoc
    and checked: every storyboard scene id has at least one line, no
    unknown scene ids appear, lines carry no timings, and the total
    narration word count sits inside the tolerance window around
    duration_seconds / 60 * 150 words. on_screen is left empty; scenes
    render the storyboard's on_screen. The script is saved only after
    every check passes.
    """
    if not project.is_approved("storyboard") or not project.is_approved("duration"):
        raise DraftError(_GATES_MESSAGE)

    sb = project.load_storyboard()
    brief = project.load_brief()

    system = _system_prompt()
    user = _user_prompt(sb, brief)

    script = client.chat_json(system, user, ScriptDoc)
    _check_scene_ids(sb, script.lines)
    _check_no_timings(script.lines)
    _check_word_count(sb, script.lines)

    saved = ScriptDoc(lines=script.lines)
    project.save_script(saved)
    return saved
