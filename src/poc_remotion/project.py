import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from poc_remotion.schemas import (
    ApprovalState,
    ProjectManifest,
    ScriptDoc,
    SourceRef,
    Storyboard,
)


class ProjectError(Exception):
    """Raised for project-related validation and I/O errors."""


_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


class Project:
    dir: Path
    id: str
    GATED_STAGES: ClassVar[list[str]] = ["storyboard", "duration", "script"]

    def __init__(self, dir: Path, id: str = "") -> None:
        self.dir = dir
        if id:
            self.id = id

    @classmethod
    def create(cls, dir: Path, id: str, model: str = "") -> "Project":
        if not _ID_PATTERN.match(id):
            raise ProjectError(f"invalid project id: {id!r}")

        dir.mkdir(parents=True, exist_ok=True)
        subdirs = ["audio", "assets", "subtitles", "output"]
        for sub in subdirs:
            (dir / sub).mkdir(exist_ok=True)

        now = datetime.now(UTC).isoformat()
        manifest = ProjectManifest(id=id, created_at=now, updated_at=now, model=model)
        (dir / "manifest.json").write_text(json.dumps(manifest.model_dump(), indent=2) + "\n")
        (dir / "approvals.json").write_text(json.dumps({"storyboard": False, "duration": False, "script": False}, indent=2) + "\n")
        (dir / "brief.json").write_text("{}\n")

        project = cls(dir)
        project.id = id
        return project

    @classmethod
    def load(cls, dir: Path) -> "Project":
        if not (dir / "manifest.json").exists():
            raise ProjectError(f"manifest.json missing in {dir}")
        manifest_json = json.loads((dir / "manifest.json").read_text())
        project = cls(dir)
        project.id = ProjectManifest(**manifest_json).id
        return project

    def save_sources(self, sources: list[SourceRef]) -> None:
        data = [s.model_dump() for s in sources]
        (self.dir / "sources.json").write_text(json.dumps(data, indent=2) + "\n")
        self._update_manifest()

    def load_sources(self) -> list[SourceRef]:
        return [SourceRef(**item) for item in json.loads((self.dir / "sources.json").read_text())]

    def save_storyboard(self, sb: Storyboard) -> None:
        (self.dir / "storyboard.json").write_text(json.dumps(sb.model_dump(), indent=2) + "\n")
        self._update_manifest()

    def load_storyboard(self) -> Storyboard:
        path = self.dir / "storyboard.json"
        if not path.exists():
            raise ProjectError(f"storyboard.json missing in {self.dir}")
        return Storyboard(**json.loads(path.read_text()))

    def save_script(self, script: ScriptDoc) -> None:
        (self.dir / "script.json").write_text(json.dumps(script.model_dump(), indent=2) + "\n")
        self._update_manifest()

    def load_script(self) -> ScriptDoc:
        path = self.dir / "script.json"
        if not path.exists():
            raise ProjectError(f"script.json missing in {self.dir}")
        return ScriptDoc(**json.loads(path.read_text()))

    def record_approval(self, stage: str) -> None:
        path = self.dir / "approvals.json"
        raw = json.loads(path.read_text())
        if stage not in raw:
            raise ProjectError(f"unknown approval stage: {stage!r}")
        raw[stage] = True
        path.write_text(json.dumps(raw, indent=2) + "\n")

    def is_approved(self, stage: str) -> bool:
        if stage not in self.GATED_STAGES:
            return False
        approvals = self._load_approvals()
        return bool(approvals.get(stage, False))

    def all_approved(self) -> bool:
        return all(self.is_approved(stage) for stage in self.GATED_STAGES)

    def manifest(self) -> ProjectManifest:
        return ProjectManifest(**json.loads((self.dir / "manifest.json").read_text()))

    def _update_manifest(self) -> None:
        path = self.dir / "manifest.json"
        data = json.loads(path.read_text())
        data["updated_at"] = datetime.now(UTC).isoformat()
        path.write_text(json.dumps(data, indent=2) + "\n")

    def _load_approvals(self) -> dict:
        raw = json.loads((self.dir / "approvals.json").read_text())
        return ApprovalState(**raw).model_dump()
