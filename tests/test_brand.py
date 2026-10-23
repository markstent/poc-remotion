"""Tests for brand system and validation."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from poc_remotion.brand import (
    contrast_ratio,
    load_brand,
    validate_brand,
)

EXPECTED = {
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


def _write(path: Path, tokens: dict) -> None:
    import json

    data = {
        "version": "1.0",
        "tokens": tokens,
        "font_family": "PP Pangram Sans",
        "fonts_dir": "src/fonts",
        "fonts": {
            "extrabold": "PPPangramSans-Extrabold.woff2",
            "bold": "PPPangramSans-Bold.woff2",
            "semibold": "PPPangramSans-Semibold.woff2",
            "regular": "PPPangramSans-Regular.woff2",
            "condensedBold": "PPPangramSans-CondensedBold.woff2",
        },
        "contrast_pairs": [
            ("darkTeal", "white", 4.5),
            ("darkTeal", "paleBlue", 4.5),
            ("darkTeal", "turquoise", 4.5),
            ("darkTeal", "lime", 4.5),
            ("white", "darkTeal", 4.5),
            ("turquoise", "darkTeal", 4.5),
            ("darkTeal", "turquoise25", 4.5),
        ],
    }
    (path / "brand.json").write_text(json.dumps(data, indent=2) + "\n")


def test_tokens_exact_set_and_values():
    brand = load_brand()
    assert brand.tokens == EXPECTED


def test_near_miss_token_rejected(tmp_path):
    bad = dict(EXPECTED, turquoise="#28E3CD")  # one off from approved
    _write(tmp_path, bad)
    with pytest.raises(ValidationError):
        load_brand(tmp_path / "brand.json")


def test_contrast_values():
    assert contrast_ratio("#1D4757", "#FFFFFF") >= 4.5
    assert contrast_ratio("#C4F600", "#CCFFFF") < 4.5


@pytest.mark.skipif(not Path("src/fonts").is_dir(), reason="local font binaries not present")
def test_validate_ok_on_real_files():
    assert validate_brand(load_brand(), Path("src/fonts")) == []


def test_missing_font_listed(tmp_path):
    problems = validate_brand(load_brand(), tmp_path)  # empty dir
    assert problems and all("missing font" in p for p in problems)


def test_contrast_failure_listed():
    brand = load_brand().model_copy(deep=True)
    brand.contrast_pairs.append(("lime", "paleBlue", 4.5))
    problems = validate_brand(brand, Path("src/fonts"))
    assert any("contrast" in p for p in problems)


def test_validate_brand_missing_fonts_dir(tmp_path):
    """validate_brand reports missing fonts when dir is absent."""
    problems = validate_brand(load_brand(), tmp_path / "does-not-exist")
    assert problems
    assert all(p.startswith("missing font ") for p in problems)
