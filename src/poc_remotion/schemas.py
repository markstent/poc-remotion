from pathlib import Path
from typing import Literal, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

SceneKind = Literal["title", "newsGrid", "beforeAfter", "framework", "quote", "analogy", "cheatSheet", "outro"]


class SourceRef(BaseModel):
    id: str
    title: str
    path: str
    kind: Literal["markdown", "text"]
    sha256: str
    headings: list[str] = Field(default_factory=list)
    extraction_notes: str = ""


class Claim(BaseModel):
    id: str
    text: str
    source_ids: list[str]
    locator: str | None = None
    status: Literal["supported", "unresolved", "conflict"]


class StoryboardScene(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9-]*$")
    kind: SceneKind
    purpose: str
    seconds: float = Field(..., gt=0)
    summary: str
    on_screen: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class Storyboard(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    objectives: list[str]
    duration_seconds: float = Field(..., gt=0)
    rationale: str
    scenes: list[StoryboardScene]

    @model_validator(mode="after")
    def check_unique_scene_ids(self) -> "Storyboard":
        ids = [scene.id for scene in self.scenes]
        if len(ids) != len(set(ids)):
            from pydantic_core import PydanticCustomError
            raise PydanticCustomError("custom_error", "duplicate scene ids not allowed")
        return self


class ScriptLine(BaseModel):
    scene_id: str
    text: str
    start_seconds: float | None = None
    end_seconds: float | None = None


class ScriptDoc(BaseModel):
    lines: list[ScriptLine]
    on_screen: dict[str, list[str]] = Field(default_factory=dict)


class ApprovalState(BaseModel):
    storyboard: bool = False
    duration: bool = False
    script: bool = False


class ProjectManifest(BaseModel):
    id: str
    created_at: str
    updated_at: str
    model: str = ""
    brand_version: str = ""


def generate_json_schemas(out_dir: Path) -> list[Path]:
    """Generate JSON schema files for all models.

    Args:
        out_dir: Directory to write schema files to.

    Returns:
        List of paths to generated schema files.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    models = [
        (Storyboard, "Storyboard"),
        (ScriptDoc, "ScriptDoc"),
        (SceneKind, "SceneKind"),
        (SourceRef, "SourceRef"),
        (Claim, "Claim"),
        (StoryboardScene, "StoryboardScene"),
        (ScriptLine, "ScriptLine"),
        (ApprovalState, "ApprovalState"),
        (ProjectManifest, "ProjectManifest"),
    ]

    paths: list[Path] = []
    import json

    for model, name in models:
        if name == "SceneKind":
            schema = {"type": "string", "enum": get_args(model)}
        else:
            schema = model.model_json_schema()
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(schema, indent=2))
        paths.append(path)

    return paths
