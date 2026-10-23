"""Command-line interface for poc-remotion."""

import argparse
import json
import sys
from pathlib import Path

from poc_remotion.brand import load_brand, validate_brand
from poc_remotion.discovery import DraftError, capture_brief, run_discovery
from poc_remotion.ingest import ingest_markdown
from poc_remotion.llm import LLMClient, LLMError
from poc_remotion.project import Project, ProjectError
from poc_remotion.render import GateError, RenderOptions, render_video
from poc_remotion.schemas import DiscoveryAnswer
from poc_remotion.script_draft import run_script
from poc_remotion.storyboard import run_storyboard

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
        "render", help="Render the project video through Remotion"
    )
    render_parser.add_argument("--id", required=True, help="Project identifier")
    render_parser.add_argument(
        "--scale", type=float, default=1.0, help="Render scale factor"
    )
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


def cmd_render(args: argparse.Namespace) -> int:
    """Handle render subcommand."""
    projects_root = _projects_root(args)

    project_path = projects_root / args.id

    try:
        project = Project.load(project_path)
        out = render_video(project, RenderOptions(scale=args.scale))
        print(out)
        return 0
    except (GateError, ProjectError, RuntimeError) as exc:
        _print_error(str(exc))
        return 2


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

    _print_error(f"unknown command: {args.command}")
    return 2
