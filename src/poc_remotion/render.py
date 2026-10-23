"""Gated render bridge: render a project's video through the fframes renderer."""

import json
import os
import shutil
import subprocess
from pathlib import Path

from pydantic import ValidationError

from poc_remotion.project import Project
from poc_remotion.schemas import NarrationDoc

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER_DIR = REPO_ROOT / "renderer"
DATA_DIR = RENDERER_DIR / "data"
MEDIA_DIR = RENDERER_DIR / "media"
FONTS_SOURCE_DIR = REPO_ROOT / "src" / "fonts"
FONT_FILES = (
    "PPPangramSans-Bold.ttf",
    "PPPangramSans-Regular.ttf",
    "PPPangramSans-Semibold.ttf",
    "PPPangramSans-Extrabold.ttf",
)
NARRATION_FILENAME = "narration.json"
STORYBOARD_FILENAME = "storyboard.json"

# Module-level alias so tests can monkeypatch subprocess execution.
subprocess_run = subprocess.run

_STDERR_TAIL_CHARS = 2000


class GateError(Exception):
    """Raised when rendering is attempted with unapproved gates."""


def _stderr_tail(text: str | None) -> str:
    """Return the tail of subprocess stderr for error messages."""
    if not text:
        return ""
    return text.strip()[-_STDERR_TAIL_CHARS:]


def _resolve_cargo() -> Path:
    """Locate the cargo executable.

    Resolution order: ``$CARGO``, ``PATH``, ``~/.cargo/bin``, then any rustup
    toolchain bin directory (covers rustup installs that did not create
    ``~/.cargo/bin`` shims).

    Raises:
        RuntimeError: when no cargo executable can be found.
    """
    env_cargo = os.environ.get("CARGO")
    if env_cargo:
        return Path(env_cargo)
    found = shutil.which("cargo")
    if found:
        return Path(found)
    home = Path.home()
    candidates = [home / ".cargo" / "bin" / "cargo"]
    toolchains = sorted((home / ".rustup" / "toolchains").glob("*/bin/cargo"))
    candidates.extend(toolchains)
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError(
        "cargo not found: install Rust via rustup or set $CARGO to the cargo binary"
    )


def _load_narration(project: Project) -> dict | None:
    """Return the validated narration.json contents when present, else None.

    Malformed JSON or a schema-invalid document raises RuntimeError naming
    narration.json, so the failure surfaces before the renderer runs.
    """
    path = project.dir / NARRATION_FILENAME
    if not path.exists():
        return None
    try:
        doc = NarrationDoc.model_validate(json.loads(path.read_text()))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"narration.json is not valid JSON: {path}: {exc}") from exc
    except ValidationError as exc:
        raise RuntimeError(f"narration.json is invalid: {path}: {exc}") from exc
    return doc.model_dump()


def _stage_fonts() -> list[Path]:
    """Copy the brand font TTFs into renderer/media for build-time embedding.

    The font files are not committed (licence unconfirmed), so they must come
    from the repo's gitignored ``src/fonts`` directory.

    Raises:
        RuntimeError: when the fonts directory or any font file is missing.
    """
    if not FONTS_SOURCE_DIR.is_dir():
        raise RuntimeError(
            f"brand fonts not found: {FONTS_SOURCE_DIR} is missing; "
            "the renderer cannot resolve text without them"
        )
    staged: list[Path] = []
    for name in FONT_FILES:
        source = FONTS_SOURCE_DIR / "NEW Pangram Sans - TrueType Font" / name
        if not source.exists():
            raise RuntimeError(f"brand font file missing: {source}")
        destination = MEDIA_DIR / name
        shutil.copy2(source, destination)
        staged.append(destination)
    return staged


def _stage_narration_audio(narration: dict, project: Project) -> list[Path]:
    """Copy narration audio into renderer/media (flat by name).

    Validates every referenced file against the project audio dir before
    copying anything, so a missing file aborts before the renderer runs. The
    file field must be the project-relative ``audio/<name>`` path; the
    renderer matches audio by bare file name.

    Raises:
        RuntimeError: when a narration line references a file that does not
            exist in the project audio dir, or uses a path outside
            ``audio/``; the message names the file.
    """
    audio_dir = project.dir / "audio"
    names: list[str] = []
    for line in narration.get("lines", []):
        name = Path(line["file"]).name
        if line["file"] != f"audio/{name}":
            raise RuntimeError(
                f"narration file path must be audio/<name>, got: {line['file']}"
            )
        if not (audio_dir / name).exists():
            raise RuntimeError(
                f"narration audio file missing from project audio dir: {line['file']}"
            )
        if name not in names:
            names.append(name)

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    for name in names:
        destination = MEDIA_DIR / name
        shutil.copy2(audio_dir / name, destination)
        staged.append(destination)
    return staged


def render_video(project: Project) -> Path:
    """Render the project's video via the fframes renderer after approval gates.

    Enforces the storyboard, duration and script gates, stages the project's
    storyboard, narration and referenced audio into ``renderer/`` (data/ and
    media/, both build-time includes), stages the brand fonts, then runs
    ``cargo run --release -- render`` in the renderer directory and moves the
    result to ``<project>/output/video.mp4``.

    Raises:
        GateError: when any of the storyboard, duration or script gates are
            unapproved; the message names the unrecorded stages.
        ProjectError: when storyboard.json or script.json is missing.
        RuntimeError: when a narration file is missing from the project audio
            dir (before the renderer runs), when the brand fonts are missing,
            when the render subprocess fails or when it produces no output.
    """
    unapproved = [stage for stage in Project.GATED_STAGES if not project.is_approved(stage)]
    if unapproved:
        raise GateError("render blocked, gates not approved for: " + ", ".join(unapproved))

    storyboard = project.load_storyboard()
    # Loading validates script.json exists and parses (a gate prerequisite).
    project.load_script()

    narration = _load_narration(project)

    output_dir = project.dir / "output"
    output_dir.mkdir(exist_ok=True)
    video_path = output_dir / "video.mp4"

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / STORYBOARD_FILENAME).write_text(
        json.dumps(storyboard.model_dump(), indent=1) + "\n"
    )
    if narration is not None:
        (DATA_DIR / NARRATION_FILENAME).write_text(
            json.dumps(narration, indent=1) + "\n"
        )
    else:
        (DATA_DIR / NARRATION_FILENAME).unlink(missing_ok=True)

    cargo = _resolve_cargo()
    cmd = [str(cargo), "run", "--release", "--quiet", "--", "render"]
    # cargo needs its sibling rustc on PATH (rustup installs without
    # ~/.cargo/bin shims have no other way to find the toolchain).
    env = dict(os.environ)
    env["PATH"] = f"{cargo.parent}{os.pathsep}{env.get('PATH', '')}"

    staged_audio: list[Path] = []
    try:
        _stage_fonts()
        if narration is not None:
            staged_audio = _stage_narration_audio(narration, project)
        proc = subprocess_run(cmd, cwd=RENDERER_DIR, capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            raise RuntimeError(
                f"renderer failed (exit {proc.returncode}): {_stderr_tail(proc.stderr)}"
            )
        rendered = RENDERER_DIR / "out.mp4"
        if not rendered.exists():
            raise RuntimeError(
                f"renderer produced no output at {rendered}: {_stderr_tail(proc.stderr)}"
            )
        shutil.move(rendered, video_path)
    finally:
        # Staged data and audio are per-project: remove them so the next
        # render (possibly a different project) embeds only its own files.
        # Fonts are stable and stay staged for the next build.
        for path in DATA_DIR.glob("*.json"):
            path.unlink()
        for path in staged_audio:
            path.unlink(missing_ok=True)
    return video_path
