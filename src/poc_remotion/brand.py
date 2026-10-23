"""Brand tokens, configuration and validation for TVB project."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

# Exactly 12 approved hex tokens
APPROVED_TOKENS: dict[str, str] = {
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


def _validate_tokens(tokens: dict[str, str], field_name: str = "tokens") -> dict[str, str]:
    """Validate brand tokens match the approved set exactly.

    Raises:
        pydantic.ValidationError if tokens are missing, extra, or values don't match.
    """
    token_keys = set(tokens.keys())
    approved_keys = set(APPROVED_TOKENS.keys())

    if token_keys != approved_keys:
        from pydantic_core import PydanticCustomError

        missing = sorted(approved_keys - token_keys)
        extra = sorted(token_keys - approved_keys)
        reason_parts = []
        if missing:
            reason_parts.append(f"missing tokens: {missing}")
        if extra:
            reason_parts.append(f"extra tokens: {extra}")
        raise PydanticCustomError("invalid_tokens", "; ".join(reason_parts))

    for key, expected_hex in APPROVED_TOKENS.items():
        actual_hex = tokens.get(key)
        if actual_hex != expected_hex:
            from pydantic_core import PydanticCustomError

            raise PydanticCustomError(
                "invalid_token_value",
                "{key} has {actual!r}, expected {expected!r}",
                {"key": key, "actual": actual_hex, "expected": expected_hex},
            )

    return tokens


class BrandConfig(BaseModel):
    """Brand configuration model.

    Attributes:
        version: Version identifier.
        tokens: Dictionary of hex colour tokens (12 entries).
        font_family: Name of the primary typeface.
        fonts_dir: Directory where WOFF2 files are stored.
        fonts: Mapping from weight label to filename.
        contrast_pairs: Fg, bg token names and minimum ratio.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    version: str
    tokens: dict[str, str] = Field(..., min_length=12, max_length=12)
    font_family: str = "PP Pangram Sans"
    fonts_dir: str = "src/fonts"
    fonts: dict[str, str]
    contrast_pairs: list[tuple[str, str, float]]

    @model_validator(mode="after")
    def validate_brand_tokens(self) -> BrandConfig:
        """Validate tokens keys and values match the approved set exactly."""
        _validate_tokens(self.tokens, "tokens")
        return self


def load_brand(path: Path = Path("brand/brand.json")) -> BrandConfig:
    """Load brand configuration from JSON.

    Args:
        path: Path to the JSON file (relative or absolute).

    Returns:
        A validated BrandConfig instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        pydantic.ValidationError: If the data is invalid (missing/extra tokens, wrong hex values).

    Note:
        Extra or missing token keys, or altered hex values, raise ValidationError.
    """
    from json import loads

    raw = path.read_text()
    data = loads(raw)

    # Let BrandConfig handle defaults via its model_config and model_validate; no manual rebuild.
    return BrandConfig(**data)


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """Calculate WCAG relative luminance ratio between two colours.

    Args:
        hex_a: First hex colour (e.g. #1D4757).
        hex_b: Second hex colour.

    Returns:
        Contrast ratio as a float rounded to 2 decimal places.

    Note:
        Uses WCAG 2.0 formula on sRGB channel intensities.
    """
    def relative_luminance(hex_colour: str) -> float:
        hex_colour = hex_colour.lstrip("#")
        r = int(hex_colour[0:2], 16) / 255.0
        g = int(hex_colour[2:4], 16) / 255.0
        b = int(hex_colour[4:6], 16) / 255.0

        def linearise(value: float) -> float:
            if value <= 0.03928:
                return value / 12.92
            return ((value + 0.055) / 1.055) ** 2.4

        r_lin = linearise(r)
        g_lin = linearise(g)
        b_lin = linearise(b)

        return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin

    l_a = relative_luminance(hex_a)
    l_b = relative_luminance(hex_b)

    lighter = max(l_a, l_b)
    darker = min(l_a, l_b)

    ratio = (lighter + 0.05) / (darker + 0.05)
    return round(ratio, 2)


def validate_brand(brand: BrandConfig, fonts_dir: Path) -> list[str]:
    """Validate brand configuration against file system and contrast rules.

    Args:
        brand: Loaded BrandConfig instance.
        fonts_dir: Directory where WOFF2 files should reside.

    Returns:
        List of problem strings. Empty list indicates validity.

    Problems reported:
        - missing font <weight>: <filename> for absent font files.
        - contrast <fg> on <bg>: <ratio> < required for failing pairs.
    """
    problems: list[str] = []

    fonts_path = fonts_dir.resolve()

    if not fonts_path.is_dir():
        # Fonts directory missing: return all font entries as missing
        return [f"missing font {weight}: {filename}" for weight, filename in brand.fonts.items()]

    token_to_hex: dict[str, str] = {}
    for key, value in brand.tokens.items():
        hex_pattern = re.compile(r"^#[0-9a-fA-F]{6}$")
        if not hex_pattern.match(value):
            from pydantic_core import PydanticCustomError

            raise PydanticCustomError(
                "invalid_hex", "{key!r} has invalid hex {value!r}", {"key": key, "value": value}
            )
        token_to_hex[key] = value

    def find_font_file(filename: str) -> bool:
        """Check if a WOFF2 file exists either directly or in a fonts subdirectory."""
        direct = fonts_path / filename
        if direct.exists():
            return True
        # Check common subdirectories that contain web font packs
        for subdir in fonts_path.iterdir():
            if subdir.is_dir() and (subdir / filename).exists():
                return True
        return False

    for weight, filename in brand.fonts.items():
        if not find_font_file(filename):
            problems.append(f"missing font {weight}: {filename}")

    for fg_token, bg_token, min_ratio in brand.contrast_pairs:
        hex_fg = token_to_hex.get(fg_token)
        hex_bg = token_to_hex.get(bg_token)

        if hex_fg is None or hex_bg is None:
            continue

        ratio = contrast_ratio(hex_fg, hex_bg)
        if ratio < min_ratio:
            problems.append(
                f"contrast {fg_token} on {bg_token}: {ratio} < required {min_ratio}"
            )

    return problems
