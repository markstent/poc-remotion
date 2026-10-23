"""Shared fixtures for the gated render bridge tests."""

import json
import subprocess
from collections.abc import Callable

import pytest

from poc_remotion import render as render_module


@pytest.fixture
def renderer(tmp_path, monkeypatch):
    """Redirect every renderer staging location into tmp_path.

    Creates a fake brand-fonts source tree so staging does not depend on the
    machine-local (gitignored) ``src/fonts`` directory.
    """
    root = tmp_path / "renderer"
    fonts_src = tmp_path / "fonts"
    font_package = fonts_src / "NEW Pangram Sans - TrueType Font"
    font_package.mkdir(parents=True)
    for name in render_module.FONT_FILES:
        (font_package / name).write_bytes(b"fake ttf")
    monkeypatch.setattr(render_module, "RENDERER_DIR", root)
    monkeypatch.setattr(render_module, "DATA_DIR", root / "data")
    monkeypatch.setattr(render_module, "MEDIA_DIR", root / "media")
    monkeypatch.setattr(render_module, "FONTS_SOURCE_DIR", fonts_src)
    return root


@pytest.fixture
def fake_render(renderer, monkeypatch) -> Callable[[], dict]:
    """Install a fake cargo run that produces a fake out.mp4.

    Returns a callable capturing the invoked command under ``cmd``, its
    keyword arguments under ``kw``, and the staged ``data/*.json`` contents
    (as parsed JSON) under ``staged_data`` while the command runs.
    """

    def _install() -> dict:
        captured: dict = {}

        def _run(cmd, **kw):
            captured.update(cmd=cmd, kw=kw)
            captured["staged_data"] = {
                path.name: json.loads(path.read_text())
                for path in sorted((renderer / "data").glob("*.json"))
            }
            (renderer / "out.mp4").write_bytes(b"fake mp4")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(render_module, "subprocess_run", _run)
        return captured

    return _install
