"""Command-line interface for poc-remotion."""

import argparse
import json
import sys
from pathlib import Path

from poc_remotion.brand import load_brand, validate_brand
from poc_remotion.claims import run_claims
from poc_remotion.discovery import DraftError, capture_brief, run_discovery
from poc_remotion.export import ExportError, run_export
from poc_remotion.ingest import ingest_markdown
from poc_remotion.llm import LLMClient, LLMError
from poc_remotion.narrate import NarrateError, run_narrate
from poc_remotion.project import Project, ProjectError
from poc_remotion.render import GateError, render_video
from poc_remotion.revise import ReviseError, run_revise
from poc_remotion.schemas import DiscoveryAnswer
from poc_remotion.script_draft import run_script
from poc_remotion.storyboard import DURATION_TOLERANCE, run_storyboard
from poc_remotion.subtitles import srt_from_script
from poc_remotion.tts import KokoroAdapter, TTSConfigError

REPO_ROOT = Path(__file__).resolve().parents[2]


def _print_error(msg: str) -> None:
    """Print error message to stderr."""
    print(msg, file=sys.stderr)


class CommandParseError(Exception):
    """Raised when command-line parsing fails."""


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="poc-remotion",
        description="Tool for managing Remotion video projects.",
    )

    subparsers = parser.add_subparsers(dest="command", required=False)

    init_parser = subparsers.add_parser("init", help="Initialise a new project")
    init_parser.add_argument("--id", required=True, help="Project identifier")
    init_parser.add_argument(
        "--projects-root", default="./projects", help="Root directory for projects"
    )

    status_parser = subparsers.add_parser("status", help="Show project approval status")
    status_parser.add_argument("--id", required=True, help="Project identifier")
    status_parser.add_argument(
        "--projects-root", default="./projects", help="Root directory for projects"
    )

    approve_parser = subparsers.add_parser("approve", help="Approve a project stage")
    approve_parser.add_argument("--id", required=True, help="Project identifier")
    approve_parser.add_argument(
        "--stage",
        choices=Project.GATED_STAGES,
        required=True,
        help="Stage to approve",
    )
    approve_parser.add_argument(
        "--projects-root", default="./projects", help="Root directory for projects"
    )

    validate_parser = subparsers.add_parser("validate", help="Validate project integrity")
    validate_parser.add_argument("--id", required=True, help="Project identifier")
    validate_parser.add_argument(
        "--projects-root", default="./projects", help="Root directory for projects"
    )

    render_parser = subparsers.add_parser(
        "render", help="Render the project video with the fframes renderer"
    )
    render_parser.add_argument("--id", required=True, help="Project identifier")
    render_parser.add_argument(
        "--projects-root", default="./projects", help="Root directory for projects"
    )

    ingest_parser = subparsers.add_parser(
        "ingest", help="Register source markdown files for a project"
    )
    ingest_parser.add_argument("--id", required=True, help="Project identifier")
    ingest_parser.add_argument(
        "--source",
        action="append",
        required=True,
        help="Source markdown file (repeatable; replaces any previously saved sources)",
    )
    ingest_parser.add_argument(
        "--projects-root", default="./projects", help="Root directory for projects"
    )

    discover_parser = subparsers.add_parser(
        "discover", help="Generate discovery questions from registered sources"
    )
    discover_parser.add_argument("--id", required=True, help="Project identifier")
    discover_parser.add_argument(
        "--projects-root", default="./projects", help="Root directory for projects"
    )

    brief_parser = subparsers.add_parser(
        "brief", help="Capture the brief from answered discovery questions"
    )
    brief_parser.add_argument("--id", required=True, help="Project identifier")
    brief_parser.add_argument(
        "--qa-file",
        required=True,
        help="JSON file of answered questions: [{\"question\": ..., \"answer\": ...}, ...]",
    )
    brief_parser.add_argument(
        "--projects-root", default="./projects", help="Root directory for projects"
    )

    storyboard_parser = subparsers.add_parser(
        "draft-storyboard", help="Draft a storyboard from the captured brief"
    )
    storyboard_parser.add_argument("--id", required=True, help="Project identifier")
    storyboard_parser.add_argument(
        "--projects-root", default="./projects", help="Root directory for projects"
    )

    script_parser = subparsers.add_parser(
        "draft-script", help="Draft the narration script from the approved storyboard"
    )
    script_parser.add_argument("--id", required=True, help="Project identifier")
    script_parser.add_argument(
        "--projects-root", default="./projects", help="Root directory for projects"
    )

    claims_parser = subparsers.add_parser(
        "claims", help="Extract the claim register from the approved script"
    )
    claims_parser.add_argument("--id", required=True, help="Project identifier")
    claims_parser.add_argument(
        "--projects-root", default="./projects", help="Root directory for projects"
    )

    narrate_parser = subparsers.add_parser(
        "narrate", help="Synthesise narration audio and write audio-true timings"
    )
    narrate_parser.add_argument("--id", required=True, help="Project identifier")
    narrate_parser.add_argument(
        "--projects-root", default="./projects", help="Root directory for projects"
    )

    export_srt_parser = subparsers.add_parser(
        "export-srt", help="Export the timed narration script as an SRT sidecar"
    )
    export_srt_parser.add_argument("--id", required=True, help="Project identifier")
    export_srt_parser.add_argument(
        "--projects-root", default="./projects", help="Root directory for projects"
    )

    revise_parser = subparsers.add_parser(
        "revise", help="Revise one storyboard scene and reset the approval gates"
    )
    revise_parser.add_argument("--id", required=True, help="Project identifier")
    revise_parser.add_argument("--scene", required=True, help="Scene id to revise")
    revise_parser.add_argument(
        "--instruction", required=True, help="What to change in the scene"
    )
    revise_parser.add_argument(
        "--projects-root", default="./projects", help="Root directory for projects"
    )

    export_parser = subparsers.add_parser(
        "export", help="Render the video and assemble the export bundle"
    )
    export_parser.add_argument("--id", required=True, help="Project identifier")
    export_parser.add_argument(
        "--projects-root", default="./projects", help="Root directory for projects"
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if isinstance(exc.code, int) and exc.code == 0:
            # --help: let the zero exit status pass through to the caller.
            raise
        if isinstance(exc.code, int):
            raise CommandParseError(f"parse error (exit code {exc.code})") from exc
        raise CommandParseError(str(exc)) from exc

    return args


def _projects_root(args: argparse.Namespace) -> Path:
    """Resolve the projects root path from args."""
    return Path(args.projects_root).resolve()


def cmd_init(args: argparse.Namespace) -> int:
    """Handle init subcommand."""
    projects_root = _projects_root(args)

    try:
        Project.create(projects_root / args.id, args.id)
        return 0
    except ProjectError as exc:
        _print_error(str(exc))
        return 2


def cmd_status(args: argparse.Namespace) -> int:
    """Handle status subcommand."""
    projects_root = _projects_root(args)

    project_path = projects_root / args.id

    try:
        project = Project.load(project_path)
    except ProjectError as exc:
        _print_error(str(exc))
        return 2

    for stage in Project.GATED_STAGES:
        is_approved = project.is_approved(stage)
        status = "approved" if is_approved else "not approved"
        print(f"{stage}: {status}")

    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    """Handle approve subcommand."""
    projects_root = _projects_root(args)

    project_path = projects_root / args.id

    try:
        project = Project.load(project_path)
        project.record_approval(args.stage)
        return 0
    except ProjectError as exc:
        _print_error(str(exc))
        return 2


def cmd_validate(args: argparse.Namespace) -> int:
    """Handle validate subcommand."""
    projects_root = _projects_root(args)

    project_path = projects_root / args.id

    try:
        project = Project.load(project_path)
        project.manifest()
        if (project_path / "storyboard.json").exists():
            project.load_storyboard()
        if (project_path / "script.json").exists():
            project.load_script()
        if (project_path / "sources.json").exists():
            project.load_sources()

        # Run brand validation against repo-owned brand files (cwd independent)
        brand = load_brand(REPO_ROOT / "brand/brand.json")
        problems = validate_brand(brand, REPO_ROOT / brand.fonts_dir)
        if problems:
            for problem in problems:
                _print_error(problem)
            return 2

        print("ok")
        return 0
    except ProjectError as exc:
        _print_error(str(exc))
        return 2
    except (ValueError, TypeError, OSError) as exc:
        # Covers pydantic.ValidationError (ValueError), non-mapping JSON
        # documents (TypeError) and unreadable files (OSError).
        _print_error(f"validation error: {exc}")
        return 2


def cmd_ingest(args: argparse.Namespace) -> int:
    """Handle ingest subcommand."""
    projects_root = _projects_root(args)

    project_path = projects_root / args.id

    try:
        project = Project.load(project_path)
        sources = [ingest_markdown(Path(path)) for path in args.source]
        project.save_sources(sources)
        for source in sources:
            print(f"{source.id}  {source.title}  ({len(source.headings)} headings)")
        return 0
    except ProjectError as exc:
        _print_error(str(exc))
        return 2
    except (TypeError, OSError, ValueError) as exc:
        # Covers unreadable or missing files (OSError), bad markdown
        # payloads such as UTF-8 decode failures (ValueError), and
        # corrupt non-mapping manifest JSON (TypeError), matching
        # cmd_validate's handler.
        _print_error(f"ingest error: {exc}")
        return 2


def cmd_discover(args: argparse.Namespace) -> int:
    """Handle discover subcommand."""
    projects_root = _projects_root(args)

    project_path = projects_root / args.id

    try:
        project = Project.load(project_path)
        questions = run_discovery(project, LLMClient())
        for number, question in enumerate(questions, start=1):
            print(f"{number}. {question}")
        return 0
    except (DraftError, ProjectError, LLMError) as exc:
        _print_error(str(exc))
        return 2
    except (TypeError, OSError, ValueError) as exc:
        # Covers corrupt sources.json or brief.json payloads (JSON decode,
        # pydantic validation, non-mapping documents), matching the handlers
        # in cmd_validate and cmd_ingest.
        _print_error(f"discover error: {exc}")
        return 2


def _load_qa_file(path: Path) -> list[DiscoveryAnswer]:
    """Load answered discovery questions from a JSON file.

    Raises ValueError (covering JSONDecodeError and pydantic validation) or
    TypeError for non-array documents, matching the CLI's error handlers.
    """
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise TypeError(f"qa file must contain a JSON array, got {type(raw).__name__}")
    qa: list[DiscoveryAnswer] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise TypeError(f"qa file entry {i} is not an object")
        if "question" not in item or "answer" not in item:
            raise ValueError(f"qa file entry {i} is missing 'question' or 'answer'")
        qa.append(DiscoveryAnswer(question=item["question"], answer=item["answer"]))
    return qa


def cmd_brief(args: argparse.Namespace) -> int:
    """Handle brief subcommand."""
    projects_root = _projects_root(args)

    project_path = projects_root / args.id

    try:
        qa = _load_qa_file(Path(args.qa_file))
        project = Project.load(project_path)
        brief = capture_brief(project, LLMClient(), qa)
    except (DraftError, ProjectError, LLMError) as exc:
        _print_error(str(exc))
        return 2
    except (TypeError, OSError, ValueError) as exc:
        # Covers malformed qa-file JSON (JSONDecodeError), non-object
        # entries (TypeError), unreadable files (OSError) and non-string
        # question or answer values (pydantic ValidationError, a ValueError).
        _print_error(f"brief error: {exc}")
        return 2

    duration = (
        "unspecified"
        if brief.duration_minutes is None
        else f"{brief.duration_minutes:g} minutes"
    )
    print(f"audience: {brief.audience}")
    print(f"tone: {brief.tone}")
    print(f"duration target: {duration}")
    return 0


def cmd_draft_storyboard(args: argparse.Namespace) -> int:
    """Handle draft-storyboard subcommand."""
    projects_root = _projects_root(args)

    project_path = projects_root / args.id

    try:
        project = Project.load(project_path)
        sb = run_storyboard(project, LLMClient())
    except (DraftError, ProjectError, LLMError) as exc:
        _print_error(str(exc))
        return 2
    except (TypeError, OSError, ValueError) as exc:
        # Covers corrupt sources.json or brief.json payloads (JSON decode,
        # pydantic validation, non-mapping documents), matching the handlers
        # in cmd_validate, cmd_ingest, cmd_discover and cmd_brief.
        _print_error(f"storyboard error: {exc}")
        return 2

    print("id  kind  seconds  summary")
    for scene in sb.scenes:
        print(f"{scene.id}  {scene.kind}  {scene.seconds:g}  {scene.summary}")
    return 0


def cmd_draft_script(args: argparse.Namespace) -> int:
    """Handle draft-script subcommand."""
    projects_root = _projects_root(args)

    project_path = projects_root / args.id

    try:
        project = Project.load(project_path)
        script = run_script(project, LLMClient())
        sb = project.load_storyboard()
    except (DraftError, ProjectError, LLMError) as exc:
        _print_error(str(exc))
        return 2
    except (TypeError, OSError, ValueError) as exc:
        # Covers corrupt storyboard.json, brief.json or script.json payloads
        # (JSON decode, pydantic validation, non-mapping documents), matching
        # the handlers in cmd_validate, cmd_ingest, cmd_discover, cmd_brief
        # and cmd_draft_storyboard.
        _print_error(f"script error: {exc}")
        return 2

    print("id  lines")
    for scene in sb.scenes:
        count = sum(1 for line in script.lines if line.scene_id == scene.id)
        print(f"{scene.id}  {count}")
    print(f"total  {sum(len(line.text.split()) for line in script.lines)} words")
    return 0


def cmd_claims(args: argparse.Namespace) -> int:
    """Handle claims subcommand."""
    projects_root = _projects_root(args)

    project_path = projects_root / args.id

    try:
        project = Project.load(project_path)
        claims = run_claims(project, LLMClient())
    except (DraftError, ProjectError, LLMError) as exc:
        _print_error(str(exc))
        return 2
    except (TypeError, OSError, ValueError) as exc:
        # Covers corrupt script.json, sources.json or claims.json payloads
        # (JSON decode, pydantic validation, non-mapping documents), matching
        # the handlers in cmd_validate, cmd_ingest, cmd_discover, cmd_brief,
        # cmd_draft_storyboard and cmd_draft_script.
        _print_error(f"claims error: {exc}")
        return 2

    for claim in claims:
        print(f"{claim.id}  {claim.status}  {claim.text}")
    unresolved = sum(1 for claim in claims if claim.status == "unresolved")
    if unresolved:
        print(f"{unresolved} unresolved")
    return 0


def cmd_narrate(args: argparse.Namespace) -> int:
    """Handle narrate subcommand."""
    projects_root = _projects_root(args)

    project_path = projects_root / args.id

    try:
        project = Project.load(project_path)
        brief = project.load_brief()
        tts = KokoroAdapter(cache_dir=project.dir / "audio")
        summary = run_narrate(project, tts)
        sb = project.load_storyboard()
        script = project.load_script()
    except (NarrateError, TTSConfigError, ProjectError) as exc:
        _print_error(str(exc))
        return 2
    except (TypeError, OSError, ValueError) as exc:
        # Covers corrupt brief.json, storyboard.json or script.json payloads
        # (JSON decode, pydantic validation, non-mapping documents), matching
        # the handlers in cmd_validate, cmd_ingest, cmd_discover, cmd_brief,
        # cmd_draft_storyboard, cmd_draft_script and cmd_claims.
        _print_error(f"narrate error: {exc}")
        return 2

    print("scene  audio span  seconds")
    for scene in sb.scenes:
        times = [
            (line.start_seconds, line.end_seconds)
            for line in script.lines
            if line.scene_id == scene.id and line.start_seconds is not None
        ]
        if not times:
            continue
        first = min(start for start, _ in times)
        last = max(end for _, end in times)
        print(f"{scene.id}  {first:.2f}-{last:.2f}  {scene.seconds:.2f}")
    total = summary["total_seconds"]
    print(
        f"total  {total:.2f}s  {summary['lines']} lines  "
        f"{summary['audio_files']} audio files"
    )
    print("manifest  narration.json")

    if brief.duration_minutes is not None:
        target = brief.duration_minutes * 60
        if abs(total - target) > DURATION_TOLERANCE * target:
            low = target * (1 - DURATION_TOLERANCE)
            high = target * (1 + DURATION_TOLERANCE)
            print(
                f"warning: total {total:.2f}s is outside the "
                f"{brief.duration_minutes:g} minute target window "
                f"({low:.2f}s to {high:.2f}s)"
            )
    return 0


def cmd_export_srt(args: argparse.Namespace) -> int:
    """Handle export-srt subcommand."""
    projects_root = _projects_root(args)

    project_path = projects_root / args.id

    try:
        project = Project.load(project_path)
        script = project.load_script()
        srt, skipped = srt_from_script(script)
        out_dir = project.dir / "subtitles"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{args.id}.srt"
        out_path.write_text(srt, encoding="utf-8")
    except ProjectError as exc:
        _print_error(str(exc))
        return 2
    except (TypeError, OSError, ValueError) as exc:
        # Covers corrupt script.json payloads (JSON decode, pydantic
        # validation, non-mapping documents) and unwritable output paths,
        # matching the handlers in cmd_validate, cmd_ingest, cmd_discover,
        # cmd_brief, cmd_draft_storyboard, cmd_draft_script, cmd_claims and
        # cmd_narrate.
        _print_error(f"export-srt error: {exc}")
        return 2

    print(out_path)
    if skipped:
        print(f"skipped {skipped} untimed lines")
    return 0


def _scene_summary(project: Project, scene_id: str) -> str:
    """The scene's current summary, or an empty string when it is unknown."""
    path = project.dir / "storyboard.json"
    if not path.exists():
        return ""
    for scene in project.load_storyboard().scenes:
        if scene.id == scene_id:
            return scene.summary
    return ""


def cmd_revise(args: argparse.Namespace) -> int:
    """Handle revise subcommand."""
    projects_root = _projects_root(args)

    project_path = projects_root / args.id

    try:
        project = Project.load(project_path)
        old_summary = _scene_summary(project, args.scene)
        result = run_revise(project, LLMClient(), args.scene, args.instruction)
    except (ReviseError, ProjectError, LLMError, TTSConfigError) as exc:
        _print_error(str(exc))
        return 2
    except (TypeError, OSError, ValueError) as exc:
        # Covers corrupt storyboard.json, script.json or narration.json
        # payloads (JSON decode, pydantic validation, non-mapping
        # documents), matching the handlers in the other content commands.
        _print_error(f"revise error: {exc}")
        return 2

    print(f"scene  {result['scene_id']}")
    print(f"old summary  {old_summary}")
    print(f"new summary  {result['summary']}")
    print(f"seconds  {result['seconds']:g}")
    print(
        "warning: revision invalidates approvals; gates reset: "
        + ", ".join(Project.GATED_STAGES)
    )
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    """Handle render subcommand."""
    projects_root = _projects_root(args)

    project_path = projects_root / args.id

    try:
        project = Project.load(project_path)
        out = render_video(project)
        print(out)
        return 0
    except (GateError, ProjectError, RuntimeError) as exc:
        _print_error(str(exc))
        return 2


def cmd_export(args: argparse.Namespace) -> int:
    """Handle export subcommand."""
    projects_root = _projects_root(args)

    project_path = projects_root / args.id

    try:
        project = Project.load(project_path)
        bundle = run_export(project)
    except (ExportError, ProjectError, RuntimeError, GateError, TTSConfigError) as exc:
        _print_error(str(exc))
        return 2
    except (TypeError, OSError, ValueError) as exc:
        # Covers invalid JSON documents (pydantic ValidationError is a
        # ValueError) and unreadable repo config files (OSError), matching
        # the handlers in the other content commands.
        _print_error(f"export error: {exc}")
        return 2

    print(bundle)
    for name in sorted(path.name for path in bundle.iterdir()):
        print(name)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns exit codes: 0 success, 2 on error."""
    try:
        args = _parse_args(argv)
    except CommandParseError as exc:
        _print_error(str(exc))
        return 2
    except SystemExit as exc:
        # _parse_args only lets --help (SystemExit 0) through.
        if isinstance(exc.code, int) and exc.code == 0:
            return 0
        raise

    if args.command == "init":
        return cmd_init(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "approve":
        return cmd_approve(args)
    if args.command == "validate":
        return cmd_validate(args)
    if args.command == "render":
        return cmd_render(args)
    if args.command == "ingest":
        return cmd_ingest(args)
    if args.command == "discover":
        return cmd_discover(args)
    if args.command == "brief":
        return cmd_brief(args)
    if args.command == "draft-storyboard":
        return cmd_draft_storyboard(args)
    if args.command == "draft-script":
        return cmd_draft_script(args)
    if args.command == "claims":
        return cmd_claims(args)
    if args.command == "narrate":
        return cmd_narrate(args)
    if args.command == "export-srt":
        return cmd_export_srt(args)
    if args.command == "revise":
        return cmd_revise(args)
    if args.command == "export":
        return cmd_export(args)

    _print_error(f"unknown command: {args.command}")
    return 2
