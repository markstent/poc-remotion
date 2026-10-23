"""Gated render bridge: render a project's video through Remotion."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from poc_remotion.project import Project

REPO_ROOT = Path(__file__).resolve().parents[2]
REMOTION_DIR = REPO_ROOT / "remotion-starter"

# Module-level alias so tests can monkeypatch subprocess execution.
subprocess_run = subprocess.run

_GATED_STAGES = ["storyboard", "duration", "script"]
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


def render_video(project: Project, opts: RenderOptions | None = None) -> Path:
    """Render the project's video via Remotion after enforcing approval gates.

    Writes ``output/props.json`` from the project's storyboard and script, then
    runs ``npx remotion render TrainerVideo`` in the remotion-starter directory.

    Raises:
        GateError: when any of the storyboard, duration or script gates are
            unapproved; the message names the unrecorded stages.
        ProjectError: when storyboard.json or script.json is missing.
        RuntimeError: when the render subprocess fails or produces no output.
    """
    opts = opts or RenderOptions()

    unapproved = [stage for stage in _GATED_STAGES if not project.is_approved(stage)]
    if unapproved:
        raise GateError("render blocked, gates not approved for: " + ", ".join(unapproved))

    storyboard = project.load_storyboard()
    script = project.load_script()

    output_dir = project.dir / "output"
    output_dir.mkdir(exist_ok=True)
    props_path = output_dir / "props.json"
    props = {"storyboard": storyboard.model_dump(), "script": script.model_dump()}
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

    proc = subprocess_run(cmd, cwd=REMOTION_DIR, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"remotion render failed (exit {proc.returncode}): {_stderr_tail(proc.stderr)}"
        )
    if not video_path.exists():
        raise RuntimeError(
            f"remotion render produced no output at {video_path}: {_stderr_tail(proc.stderr)}"
        )
    return video_path
