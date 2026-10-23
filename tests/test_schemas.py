from typing import get_args

import pytest
from pydantic import ValidationError

from poc_remotion.schemas import (
    SceneKind,
    Storyboard,
    StoryboardScene,
    generate_json_schemas,
)

SCENE_KINDS = ["title", "newsGrid", "beforeAfter", "framework", "quote", "analogy", "cheatSheet", "outro"]


def _scene(id: str, kind: SceneKind, seconds: float) -> StoryboardScene:
    return StoryboardScene(
        id=id,
        kind=kind,
        purpose="placeholder",
        seconds=seconds,
        summary="placeholder",
        on_screen=["placeholder"],
    )


def test_scene_kinds_match_design():
    assert get_args(SceneKind) == tuple(SCENE_KINDS)  # order too: scenes index by position


def test_storyboard_roundtrip():
    sb = Storyboard(
        objectives=["x"], duration_seconds=5.0, rationale="r", scenes=[_scene("s1", "title", 3.0), _scene("s2", "quote", 2.0)]
    )
    assert Storyboard.model_validate_json(sb.model_dump_json()) == sb


def test_nonpositive_duration_rejected():
    with pytest.raises(ValidationError):
        Storyboard(objectives=[], duration_seconds=0, rationale="r", scenes=[_scene("s1", "title", 1.0)])


def test_duplicate_scene_ids_rejected():
    with pytest.raises(ValidationError):
        Storyboard(objectives=[], duration_seconds=2.0, rationale="r", scenes=[_scene("s1", "title", 1.0), _scene("s1", "quote", 1.0)])


def test_schema_files_generated(tmp_path):
    paths = generate_json_schemas(tmp_path)
    assert {p.name for p in paths} >= {"Storyboard.json", "ScriptDoc.json"}
