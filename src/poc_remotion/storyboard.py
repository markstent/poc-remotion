"""Model-drafted storyboard generation with semantic checks."""

from poc_remotion.discovery import DraftError
from poc_remotion.llm import LLMClient
from poc_remotion.project import Project
from poc_remotion.schemas import Brief, SourceRef, Storyboard

SCENE_ON_SCREEN_SPEC: dict[str, list[str]] = {
    "title": ["headline", "subheadline"],
    "quote": ["quote line"],
    "framework": ["panel label G", "panel label C", "panel label S", "panel label E"],
    "beforeAfter": ["before text", "after text"],
    "newsGrid": ["card 1", "card 2", "card 3", "card 4"],
    "analogy": ["scene caption"],
    "cheatSheet": ["panel 1", "panel 2", "panel 3"],
    "outro": ["call to action"],
}

DURATION_TOLERANCE = 0.25

_NO_BRIEF = "brief not captured; run discover and brief first"
_NO_SOURCES = "no sources registered; run ingest first"
_SECONDS_TOLERANCE = 1.5
_MIN_SCENES = 3
_MAX_SCENES = 12

# One-line purpose per kind, from design doc section 7 (video 1 outline).
_KIND_PURPOSES: dict[str, str] = {
    "title": "opener that states the topic and introduces the presenter",
    "newsGrid": "cautionary stories hook with a checked-output lesson",
    "beforeAfter": "a vague prompt failing against a structured prompt winning",
    "framework": "the four prompt panels revealed in step",
    "quote": "the golden rule as a full-bleed quote",
    "analogy": "an everyday analogy made visual",
    "cheatSheet": "summary panels of the rules to keep",
    "outro": "try-it-today call to action",
}


def _system_prompt() -> str:
    catalogue = "\n".join(f"- {kind}: {_KIND_PURPOSES[kind]}" for kind in SCENE_ON_SCREEN_SPEC)
    spec = "\n".join(f"- {kind}: {', '.join(fields)}" for kind, fields in SCENE_ON_SCREEN_SPEC.items())
    return (
        "You draft a storyboard for a training video. "
        "Every scene uses one of these eight kinds:\n"
        f"{catalogue}\n\n"
        "Each kind has a fixed on-screen contract: an ordered list of strings "
        "the scene component renders. The on_screen array must match the "
        "kind's contract exactly in length:\n"
        f"{spec}\n\n"
        "On_screen entries are viewer-facing copy only. Never begin an entry "
        "with a structural label such as 'Card:', 'Panel N:', 'Before:' or "
        "'After:', and never wrap an entry in quotation marks: the scenes "
        "already render their own labels, badges and headers.\n\n"
        f"Use between {_MIN_SCENES} and {_MAX_SCENES} scenes, and make the "
        "scene seconds sum to duration_seconds."
    )


def _user_prompt(brief: Brief, sources_text: str) -> str:
    duration = (
        "unspecified" if brief.duration_minutes is None else f"{brief.duration_minutes:g} minutes"
    )
    objectives = "\n".join(f"- {o}" for o in brief.objectives) if brief.objectives else "- none"
    return (
        f"Audience: {brief.audience}\n"
        f"Objectives:\n{objectives}\n"
        f"Tone: {brief.tone}\n"
        f"Duration target: {duration}\n\n"
        f"Source material:\n{sources_text}\n\n"
        "Draft the storyboard for this video. "
        "Answer with JSON of the form "
        '{"objectives": ["..."], "duration_seconds": 300, "rationale": "...", '
        '"scenes": [{"id": "kebab-case-id", "kind": "title", "purpose": "...", '
        '"seconds": 60, "summary": "...", "on_screen": ["..."], "source_ids": []}]}.'
    )


def _load_sources(project: Project) -> list[SourceRef]:
    if not (project.dir / "sources.json").exists():
        raise DraftError(_NO_SOURCES)
    sources = project.load_sources()
    if not sources:
        raise DraftError(_NO_SOURCES)
    return sources


def _check_scenes(sb: Storyboard) -> None:
    if not (_MIN_SCENES <= len(sb.scenes) <= _MAX_SCENES):
        raise DraftError(f"expected {_MIN_SCENES} to {_MAX_SCENES} scenes, got {len(sb.scenes)}")
    for scene in sb.scenes:
        expected = len(SCENE_ON_SCREEN_SPEC[scene.kind])
        if len(scene.on_screen) != expected:
            raise DraftError(
                f"scene {scene.id} ({scene.kind}): expected {expected} on_screen "
                f"entries, got {len(scene.on_screen)}"
            )


def _check_duration_window(sb: Storyboard, brief: Brief) -> None:
    if brief.duration_minutes is None:
        return
    target_seconds = brief.duration_minutes * 60
    if abs(sb.duration_seconds - target_seconds) > DURATION_TOLERANCE * target_seconds:
        actual_minutes = sb.duration_seconds / 60
        raise DraftError(
            "duration_seconds is outside the tolerance window around the brief "
            f"target: target {brief.duration_minutes:.1f} minutes, "
            f"actual {actual_minutes:.1f} minutes"
        )


def _seconds_total(sb: Storyboard) -> float:
    return sum(scene.seconds for scene in sb.scenes)


def run_storyboard(project: Project, client: LLMClient) -> Storyboard:
    """Draft a storyboard from the captured brief and registered sources.

    Prerequisites run before any LLM call: the brief must be present, then
    at least one source registered. The model reply is parsed into a
    Storyboard and checked: scene count, per-kind on_screen lengths, and
    duration_seconds inside the tolerance window around the brief target
    (skipped when the brief has no duration). If the scene seconds do not
    sum to duration_seconds, exactly one repair re-ask names the mismatch;
    a second failure raises DraftError. The storyboard is saved only after
    every check passes.
    """
    if not project.brief_present():
        raise DraftError(_NO_BRIEF)
    sources = _load_sources(project)

    brief = project.load_brief()
    source_lines = []
    for source in sources:
        headings = ", ".join(source.headings) if source.headings else "none"
        source_lines.append(f"- {source.title}; headings: {headings}")

    system = _system_prompt()
    user = _user_prompt(brief, "\n".join(source_lines))

    sb = client.chat_json(system, user, Storyboard)
    _check_scenes(sb)
    _check_duration_window(sb, brief)

    if abs(_seconds_total(sb) - sb.duration_seconds) > _SECONDS_TOLERANCE:
        mismatch = (
            f"\n\nThe previous storyboard's scene seconds summed to "
            f"{_seconds_total(sb):g} but duration_seconds is "
            f"{sb.duration_seconds:g}. Adjust the scene seconds so they sum "
            "to duration_seconds."
        )
        sb = client.chat_json(system, user + mismatch, Storyboard)
        _check_scenes(sb)
        _check_duration_window(sb, brief)
        if abs(_seconds_total(sb) - sb.duration_seconds) > _SECONDS_TOLERANCE:
            raise DraftError(
                f"scene seconds still do not sum to duration_seconds: scenes "
                f"sum to {_seconds_total(sb):g}, duration_seconds is "
                f"{sb.duration_seconds:g}"
            )

    project.save_storyboard(sb)
    return sb
