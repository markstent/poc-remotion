"""Gated render bridge: render a project's video through Remotion."""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from poc_remotion.project import Project

REPO_ROOT = Path(__file__).resolve().parents[2]
REMOTION_DIR = REPO_ROOT / "remotion-starter"
PUBLIC_AUDIO_DIR = REMOTION_DIR / "public" / "audio"
NARRATION_FILENAME = "narration.json"

# Module-level alias so tests can monkeypatch subprocess execution.
subprocess_run = subprocess.run

_STDERR_TAIL_CHARS = 2000


class GateError(Exception):
    """Raised when rendering is attempted with unapproved gates."""


@dataclass
class RenderOptions:
    scale: float = 1.0


def _stderr_tail(text: str | None) -> str:
    """Return the tail of subprocess stderr for error messages."""
    if not text:
        return ""
    return text.strip()[-_STDERR_TAIL_CHARS:]


def _load_narration(project: Project) -> dict | None:
    """Return the parsed narration.json when present, else None."""
    path = project.dir / NARRATION_FILENAME
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _stage_narration_audio(narration: dict, project: Project) -> list[Path]:
    """Copy narration audio into remotion-starter/public/audio (flat by name).

    Validates every referenced file against the project audio dir before
    copying anything, so a missing file aborts before npx is invoked.

    Raises:
        RuntimeError: when a narration line references a file that does not
            exist in the project audio dir; the message names the file.
    """
    audio_dir = project.dir / "audio"
    names: list[str] = []
    for line in narration.get("lines", []):
        name = Path(line["file"]).name
        if not (audio_dir / name).exists():
            raise RuntimeError(
                f"narration audio file missing from project audio dir: {line['file']}"
            )
        if name not in names:
            names.append(name)

    PUBLIC_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    for name in names:
        destination = PUBLIC_AUDIO_DIR / name
        shutil.copy2(audio_dir / name, destination)
        staged.append(destination)
    return staged


def render_video(project: Project, opts: RenderOptions | None = None) -> Path:
    """Render the project's video via Remotion after enforcing approval gates.

    Writes ``output/props.json`` from the project's storyboard and script (plus
    ``narration`` when the project has a ``narration.json``), stages the
    referenced audio files into ``remotion-starter/public/audio`` for the
    render, then runs ``npx remotion render TrainerVideo`` in the
    remotion-starter directory. Only the staged audio copies are removed
    afterwards; the project's own audio files are untouched.

    Raises:
        GateError: when any of the storyboard, duration or script gates are
            unapproved; the message names the unrecorded stages.
        ProjectError: when storyboard.json or script.json is missing.
        RuntimeError: when a narration file is missing from the project audio
            dir (before npx is invoked), when the render subprocess fails or
            when it produces no output.
    """
    opts = opts or RenderOptions()

    unapproved = [stage for stage in Project.GATED_STAGES if not project.is_approved(stage)]
    if unapproved:
        raise GateError("render blocked, gates not approved for: " + ", ".join(unapproved))

    storyboard = project.load_storyboard()
    script = project.load_script()

    narration = _load_narration(project)
    staged_audio: list[Path] = []
    if narration is not None:
        staged_audio = _stage_narration_audio(narration, project)

    output_dir = project.dir / "output"
    output_dir.mkdir(exist_ok=True)
    props_path = output_dir / "props.json"
    props = {"storyboard": storyboard.model_dump(), "script": script.model_dump()}
    if narration is not None:
        props["narration"] = narration
    props_path.write_text(json.dumps(props, indent=2) + "\n")

    video_path = output_dir / "video.mp4"
    cmd = [
        "npx",
        "remotion",
        "render",
        "TrainerVideo",
        str(video_path),
        f"--props={props_path}",
        f"--scale={opts.scale}",
    ]

    try:
        proc = subprocess_run(cmd, cwd=REMOTION_DIR, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"remotion render failed (exit {proc.returncode}): {_stderr_tail(proc.stderr)}"
            )
        if not video_path.exists():
            raise RuntimeError(
                f"remotion render produced no output at {video_path}: {_stderr_tail(proc.stderr)}"
            )
    finally:
        for path in staged_audio:
            path.unlink(missing_ok=True)
    return video_path
