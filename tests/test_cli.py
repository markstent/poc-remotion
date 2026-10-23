

import json

from poc_remotion.cli import main


def test_validate_ok_on_fresh_project(tmp_path, capsys, monkeypatch):
    """Brand validation passes when fonts_dir matches the brand's configured dir."""
    monkeypatch.chdir(tmp_path)

    # Create a minimal valid brand setup
    brand_dir = tmp_path / "brand"
    brand_dir.mkdir()
    brand_json = {
        "version": "1.0",
        "tokens": {
            "turquoise": "#27E2CC",
            "darkTeal": "#1D4757",
            "lime": "#C4F600",
            "paleBlue": "#CCFFFF",
            "white": "#FFFFFF",
            "black": "#000000",
            "turquoise75": "#5DE9D9",
            "turquoise50": "#93F0E5",
            "turquoise25": "#C9F8F2",
            "darkTeal75": "#496E7A",
            "darkTeal50": "#829BA3",
            "darkTeal25": "#C3CFD1",
        },
        "font_family": "PP Pangram Sans",
        "fonts_dir": str(tmp_path / "fake-fonts"),
        "fonts": {},
        "contrast_pairs": [],
    }

    brand_dir.joinpath("brand.json").write_text(json.dumps(brand_json) + "\n")

    # Init a project
    assert main(["init", "--id", "demo", "--projects-root", "projects"]) == 0

    # validate should succeed because fonts map is empty
    result = main(["validate", "--id", "demo", "--projects-root", "projects"])
    assert result == 0


def test_validate_corrupt_brand_tokens(tmp_path, capsys, monkeypatch):
    """Brand validation fails with exit 2 when tokens key missing."""
    monkeypatch.chdir(tmp_path)

    # Create brand dir with corrupt brand.json (removed tokens)
    brand_dir = tmp_path / "brand"
    brand_dir.mkdir()
    brand_json = {
        "version": "1.0",
        "font_family": "PP Pangram Sans",
        "fonts_dir": str(tmp_path / "fake-fonts"),
        "fonts": {},
        "contrast_pairs": [],
    }

    brand_dir.joinpath("brand.json").write_text(json.dumps(brand_json) + "\n")

    assert main(["init", "--id", "demo", "--projects-root", "projects"]) == 0
    result = main(["validate", "--id", "demo", "--projects-root", "projects"])
    assert result == 2


def test_validate_missing_fonts_dir(tmp_path, capsys, monkeypatch):
    """Brand validation reports missing font problems when fonts dir is absent."""
    monkeypatch.chdir(tmp_path)

    # Create a valid brand setup but with non-existent fonts_dir
    brand_dir = tmp_path / "brand"
    brand_dir.mkdir()

    valid_tokens = {
        "turquoise": "#27E2CC",
        "darkTeal": "#1D4757",
        "lime": "#C4F600",
        "paleBlue": "#CCFFFF",
        "white": "#FFFFFF",
        "black": "#000000",
        "turquoise75": "#5DE9D9",
        "turquoise50": "#93F0E5",
        "turquoise25": "#C9F8F2",
        "darkTeal75": "#496E7A",
        "darkTeal50": "#829BA3",
        "darkTeal25": "#C3CFD1",
    }

    brand_json = {
        "version": "1.0",
        "tokens": valid_tokens,
        "font_family": "PP Pangram Sans",
        "fonts_dir": str(tmp_path / "does-not-exist"),
        "fonts": {
            "extrabold": "PPPangramSans-Extrabold.woff2",
            "regular": "PPPangramSans-Regular.woff2",
        },
        "contrast_pairs": [],
    }

    brand_dir.joinpath("brand.json").write_text(json.dumps(brand_json) + "\n")

    assert main(["init", "--id", "demo", "--projects-root", "projects"]) == 0
    result = main(["validate", "--id", "demo", "--projects-root", "projects"])
    assert result == 2
    out = capsys.readouterr().err
    assert "missing font extrabold" in out
    assert "missing font regular" in out


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
