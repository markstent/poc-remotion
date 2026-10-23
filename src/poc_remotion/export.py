"""Export bundle assembly: render, subtitles and provenance in one directory."""

import json
import shutil
from pathlib import Path

from poc_remotion.brand import load_brand
from poc_remotion.project import Project
from poc_remotion.render import render_video
from poc_remotion.schemas import SourceRef
from poc_remotion.subtitles import srt_from_script
from poc_remotion.tts import load_tts_config


class ExportError(Exception):
    """Raised when a project cannot be exported."""


def _dump(data: object) -> str:
    """Serialise a JSON document with the project's file conventions."""
    return json.dumps(data, indent=2) + "\n"


def _write_project_docs(project: Project, bundle: Path, sources: list[SourceRef]) -> None:
    """Write the project's provenance documents into the bundle."""
    (bundle / "storyboard.json").write_text(
        _dump(project.load_storyboard().model_dump()), encoding="utf-8"
    )
    (bundle / "script.json").write_text(
        _dump(project.load_script().model_dump()), encoding="utf-8"
    )
    (bundle / "claims.json").write_text(
        _dump([claim.model_dump(mode="json") for claim in project.load_claims()]),
        encoding="utf-8",
    )
    (bundle / "sources.json").write_text(
        _dump([source.model_dump() for source in sources]),
        encoding="utf-8",
    )
    (bundle / "manifest.json").write_text(
        _dump(project.manifest().model_dump()), encoding="utf-8"
    )


def _copy_repo_files(bundle: Path, brand_path: Path, tts_path: Path) -> None:
    """Copy the repo brand and TTS config into the bundle (pre-validated)."""
    shutil.copy2(brand_path, bundle / "brand.json")
    shutil.copy2(tts_path, bundle / "tts.json")


def run_export(project: Project) -> Path:
    """Render the project video and assemble the export bundle.

    The bundle is ``output/bundle/`` inside the project and holds the
    rendered video, the SRT sidecar and every provenance document needed
    to audit the result. It is rebuilt from scratch on every export, so a
    re-export never leaves stale files behind.

    Returns:
        The bundle directory.

    Raises:
        ExportError: when approval gates are unrecorded (the message names
            the stages) or any script line lacks audio-true timing (the
            message names the untimed count and ``narrate``).
        ProjectError: when storyboard.json, script.json or sources.json is
            missing.
        RuntimeError: when the render subprocess fails or produces no
            output.
    """
    unapproved = [s for s in Project.GATED_STAGES if not project.is_approved(s)]
    if unapproved:
        raise ExportError(
            "export blocked, gates not approved for: " + ", ".join(unapproved)
        )

    script = project.load_script()
    untimed = sum(
        1
        for line in script.lines
        if line.start_seconds is None or line.end_seconds is None
    )
    if untimed:
        raise ExportError(
            f"export blocked: {untimed} script line(s) untimed; "
            "run narrate to write audio-true timings"
        )

    # Validate every remaining input BEFORE deleting a previous good bundle,
    # so a failed assembly cannot destroy it.
    sources = project.load_sources()
    # Imported here because cli.py imports this module: a module-level
    # import would be circular.
    from poc_remotion.cli import REPO_ROOT

    brand_path = REPO_ROOT / "brand/brand.json"
    tts_path = REPO_ROOT / "config/tts.json"
    load_brand(brand_path)
    load_tts_config(tts_path)

    video = render_video(project)

    srt, _skipped = srt_from_script(script)
    subtitles_dir = project.dir / "subtitles"
    subtitles_dir.mkdir(parents=True, exist_ok=True)
    srt_path = subtitles_dir / f"{project.id}.srt"
    srt_path.write_text(srt, encoding="utf-8")

    bundle = project.dir / "output" / "bundle"
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)

    shutil.copy2(video, bundle / "video.mp4")
    shutil.copy2(srt_path, bundle / f"{project.id}.srt")
    _write_project_docs(project, bundle, sources)
    _copy_repo_files(bundle, brand_path, tts_path)
    return bundle
