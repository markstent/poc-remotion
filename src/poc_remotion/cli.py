"""Command-line interface for poc-remotion."""

import argparse
import sys
from pathlib import Path

from poc_remotion.project import Project, ProjectError


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
        choices=["storyboard", "duration", "script"],
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

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
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

    for stage in ["storyboard", "duration", "script"]:
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
        print("ok")
        return 0
    except ProjectError as exc:
        _print_error(str(exc))
        return 2
    except ValueError as exc:
        _print_error(f"validation error: {exc}")
        return 2


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns exit codes: 0 success, 2 on error."""
    try:
        args = _parse_args(argv)
    except CommandParseError as exc:
        _print_error(str(exc))
        return 2

    if args.command == "init":
        return cmd_init(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "approve":
        return cmd_approve(args)
    if args.command == "validate":
        return cmd_validate(args)

    _print_error(f"unknown command: {args.command}")
    return 2
