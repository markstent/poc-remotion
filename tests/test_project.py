from pathlib import Path

import pytest

from poc_remotion.project import Project, ProjectError


def _fixture_storyboard():
    from poc_remotion.schemas import Storyboard, StoryboardScene

    return Storyboard(
        objectives=["A", "B"],
        duration_seconds=120.0,
        rationale="test",
        scenes=[
            StoryboardScene(id="intro", kind="title", purpose="start", seconds=10.0, summary="start"),
        ],
    )


def test_create_creates_layout(tmp_path: Path) -> None:
    p = Project.create(tmp_path / "projects" / "demo", "demo")
    for name in ["manifest.json", "approvals.json"]:
        assert (p.dir / name).exists()
    for sub in ["audio", "assets", "subtitles", "output"]:
        assert (p.dir / sub).is_dir()


def test_unsafe_ids_rejected(tmp_path: Path) -> None:
    for bad in ["../evil", "A B", "Upper", "a/b", "", "-x"]:
        with pytest.raises(ProjectError):
            Project.create(tmp_path / "projects" / "x", bad)


def test_gates_default_closed(tmp_path: Path) -> None:
    p = Project.create(tmp_path / "projects" / "demo", "demo")
    assert not p.all_approved()
    for stage in ["storyboard", "duration", "script"]:
        assert not p.is_approved(stage)


def test_approvals_persist_across_load(tmp_path: Path) -> None:
    p = Project.create(tmp_path / "projects" / "demo", "demo")
    p.record_approval("storyboard")
    p.record_approval("duration")
    p2 = Project.load(tmp_path / "projects" / "demo")
    assert p2.is_approved("storyboard") and p2.is_approved("duration") and not p2.is_approved("script")


def test_load_missing_document_raises(tmp_path: Path) -> None:
    p = Project.create(tmp_path / "projects" / "demo", "demo")
    with pytest.raises(ProjectError):
        p.load_storyboard()


def test_storyboard_roundtrip_through_store(tmp_path: Path) -> None:

    p = Project.create(tmp_path / "projects" / "demo", "demo")
    sb = _fixture_storyboard()
    p.save_storyboard(sb)
    assert Project.load(p.dir).load_storyboard() == sb


def test_brief_roundtrip(tmp_path: Path) -> None:
    from poc_remotion.schemas import Brief, DiscoveryAnswer

    p = Project.create(tmp_path / "projects" / "demo", "demo")
    brief = Brief(
        audience="developers",
        qa=[DiscoveryAnswer(question="What?", answer="This.")],
    )
    p.save_brief(brief)
    assert p.load_brief() == brief


def test_load_brief_missing_raises(tmp_path: Path) -> None:
    p = Project.create(tmp_path / "projects" / "demo", "demo")
    (p.dir / "brief.json").unlink()
    with pytest.raises(ProjectError, match="brief.json"):
        p.load_brief()


def test_brief_present(tmp_path: Path) -> None:
    from poc_remotion.schemas import Brief, DiscoveryAnswer

    p = Project.create(tmp_path / "projects" / "demo", "demo")
    assert not p.brief_present()
    p.save_brief(Brief(qa=[DiscoveryAnswer(question="Q?", answer="A.")]))
    assert p.brief_present()
    p.save_brief(Brief(audience="new hires"))
    assert p.brief_present()
    p.save_brief(Brief())
    assert not p.brief_present()


def test_claims_roundtrip(tmp_path: Path) -> None:
    from poc_remotion.schemas import Claim

    p = Project.create(tmp_path / "projects" / "demo", "demo")
    claims = [
        Claim(id="c1", text="First claim.", source_ids=["src-1"], locator="p. 3", status="supported"),
        Claim(id="c2", text="Second claim.", source_ids=["src-2"], locator=None, status="unresolved"),
    ]
    p.save_claims(claims)
    assert p.load_claims() == claims


def test_load_claims_empty_when_absent(tmp_path: Path) -> None:
    p = Project.create(tmp_path / "projects" / "demo", "demo")
    assert p.load_claims() == []


def test_load_claims_invalid_raises(tmp_path: Path) -> None:
    p = Project.create(tmp_path / "projects" / "demo", "demo")
    (p.dir / "claims.json").write_text('{"not": "a list"}')
    with pytest.raises(ProjectError, match="claims.json"):
        p.load_claims()
