

from poc_remotion.cli import main


def test_init_then_status(tmp_path, capsys):
    assert main(["init", "--id", "demo", "--projects-root", str(tmp_path)]) == 0
    assert main(["status", "--id", "demo", "--projects-root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "storyboard: not approved" in out
    assert "script: not approved" in out


def test_approve_updates_status(tmp_path, capsys):
    main(["init", "--id", "demo", "--projects-root", str(tmp_path)])
    assert main(
        ["approve", "--id", "demo", "--stage", "storyboard", "--projects-root", str(tmp_path)]
    ) == 0
    main(["status", "--id", "demo", "--projects-root", str(tmp_path)])
    assert "storyboard: approved" in capsys.readouterr().out


def test_bad_stage_exits_two(tmp_path):
    result = main(
        ["approve", "--id", "demo", "--stage", "nope", "--projects-root", str(tmp_path)]
    )
    assert result == 2


def test_validate_ok_on_fresh_project(tmp_path):
    main(["init", "--id", "demo", "--projects-root", str(tmp_path)])
    assert main(["validate", "--id", "demo", "--projects-root", str(tmp_path)]) == 0


def test_validate_detects_corrupt_storyboard(tmp_path):
    import json

    init_result = main(["init", "--id", "bad", "--projects-root", str(tmp_path)])
    assert init_result == 0

    bad_storyboard = {"invalid_field": "not-a-list", "_type": "storyboard"}
    (tmp_path / "bad" / "storyboard.json").write_text(json.dumps(bad_storyboard) + "\n")

    assert main(["validate", "--id", "bad", "--projects-root", str(tmp_path)]) == 2


def test_status_missing_project_exits_two(tmp_path):
    assert main(["status", "--id", "ghost", "--projects-root", str(tmp_path)]) == 2


def test_projects_root_relative_path(tmp_path, monkeypatch):
    inner = tmp_path / "inner"
    inner.mkdir()
    monkeypatch.chdir(inner)
    project_root = tmp_path / "proj-root"

    assert main(["init", "--id", "myproj", "--projects-root", "../proj-root"]) == 0

    outer_proj_dir = project_root / "myproj"
    assert (outer_proj_dir / "manifest.json").exists()
