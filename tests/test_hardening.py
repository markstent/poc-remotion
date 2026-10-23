"""Hardening carry-forward tests from the plan A whole-branch review."""

import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from poc_remotion import render
from poc_remotion.cli import main
from poc_remotion.ingest import ingest_markdown
from poc_remotion.llm import LLMClient, LLMError, _default_post
from poc_remotion.project import Project
from poc_remotion.schemas import Storyboard


def test_gated_stages_single_source(tmp_path, monkeypatch):
    """Gated stages are defined once on Project and read by every consumer."""
    assert Project.GATED_STAGES == ["storyboard", "duration", "script"]

    project = Project.create(tmp_path / "proj", "proj")
    assert project.all_approved() is False

    # Patching the single source changes all_approved behaviour.
    monkeypatch.setattr(Project, "GATED_STAGES", ["storyboard"])
    project.record_approval("storyboard")
    assert project.all_approved() is True

    # The render gate no longer keeps its own copy of the list.
    assert not hasattr(render, "_GATED_STAGES")


def test_help_exits_zero(capsys):
    """--help passes through argparse and exits 0 with usage on stdout."""
    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "usage:" in out


def test_validate_catches_type_error(tmp_path, capsys):
    """A malformed storyboard document exits 2 with a message, no traceback."""
    assert main(["init", "--id", "demo", "--projects-root", str(tmp_path)]) == 0
    (tmp_path / "demo" / "storyboard.json").write_text(json.dumps([1, 2, 3]) + "\n")

    assert main(["validate", "--id", "demo", "--projects-root", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "validation error" in err


@pytest.mark.skipif(not Path("src/fonts").is_dir(), reason="local font binaries not present")
def test_validate_works_from_other_cwd(tmp_path, monkeypatch):
    """Validate succeeds from an unrelated cwd: brand resolved from REPO_ROOT."""
    monkeypatch.chdir(tmp_path)
    projects_root = tmp_path / "projects"
    assert main(["init", "--id", "demo", "--projects-root", str(projects_root)]) == 0
    assert main(["validate", "--id", "demo", "--projects-root", str(projects_root)]) == 0


def test_ingest_handles_bom(tmp_path):
    """A UTF-8 BOM is stripped before title extraction."""
    path = tmp_path / "doc.md"
    path.write_bytes("\ufeff# BOM Title\n".encode("utf-8"))
    source = ingest_markdown(path)
    assert source.title == "BOM Title"


def test_transport_error_wrapped(monkeypatch):
    """Transport failures surface as LLMError, without exposing the API key."""

    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = LLMClient(api_key="secret-key-123", _post=_default_post)
    with pytest.raises(LLMError) as excinfo:
        client.chat_json("s", "u", Storyboard)
    message = str(excinfo.value)
    assert "connection refused" in message
    assert "secret-key-123" not in message


def test_timeout_from_env(monkeypatch):
    """LITELLM_TIMEOUT (seconds) is honoured by _default_post."""
    monkeypatch.setenv("LITELLM_TIMEOUT", "7")

    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["timeout"] = timeout
        return io.BytesIO(b"{}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    _default_post("http://127.0.0.1:4000/v1", "k", {"model": "m"})
    assert captured["timeout"] == 7
