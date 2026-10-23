

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
