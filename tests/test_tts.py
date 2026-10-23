"""Tests for TTS configuration loading and the content-addressed adapter."""

import hashlib
import wave
from pathlib import Path

import pytest

from poc_remotion.tts import KokoroAdapter, TTSConfigError, load_tts_config

REPO_ROOT = Path(__file__).resolve().parents[1]


class FakeEngine:
    """Test double: writes a small valid wav (44100 Hz, 16-bit mono) and records calls."""

    def __init__(self, frames: int = 22050) -> None:
        self.frames = frames
        self.calls: list[tuple[str, str, Path]] = []

    def synthesize(self, text: str, voice: str, out_path: Path) -> None:
        self.calls.append((text, voice, out_path))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(out_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(44100)
            wav.writeframes(b"\x00\x00" * self.frames)


def _cache_path(cache_dir: Path, voice: str, text: str) -> Path:
    digest = hashlib.sha256(f"{voice}\n{text}".encode()).hexdigest()[:16]
    return cache_dir / f"{digest}.wav"


def test_load_tts_config_reads_pick() -> None:
    config = load_tts_config(REPO_ROOT / "config" / "tts.json")

    assert config.engine == "kokoro-onnx"
    assert config.voice == "bf_emma"


def test_load_tts_config_missing_raises(tmp_path: Path) -> None:
    missing = tmp_path / "tts.json"

    with pytest.raises(TTSConfigError, match="tts.json"):
        load_tts_config(missing)


def test_load_tts_config_invalid_content_raises(tmp_path: Path) -> None:
    bad = tmp_path / "tts.json"
    bad.write_text('{"engine": "kokoro-onnx"}')  # voice missing

    with pytest.raises(TTSConfigError, match="tts.json"):
        load_tts_config(bad)

    bad.write_text("not json at all")
    with pytest.raises(TTSConfigError, match="tts.json"):
        load_tts_config(bad)


def test_synthesize_creates_cached_wav(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    adapter = KokoroAdapter(cache_dir=cache_dir, engine=FakeEngine())

    result = adapter.synthesize("Hello there.", "bf_emma", tmp_path / "unused.wav")

    assert result.path == str(_cache_path(cache_dir, "bf_emma", "Hello there."))
    assert Path(result.path).exists()
    assert result.duration_seconds == pytest.approx(0.5)


def test_cache_hit_skips_engine(tmp_path: Path) -> None:
    engine = FakeEngine()
    adapter = KokoroAdapter(cache_dir=tmp_path / "cache", engine=engine)

    first = adapter.synthesize("Hello there.", "bf_emma", tmp_path / "first.wav")
    second = adapter.synthesize("Hello there.", "bf_emma", tmp_path / "second.wav")

    assert len(engine.calls) == 1
    assert second.path == first.path
    assert second.duration_seconds == pytest.approx(first.duration_seconds)


def test_zero_frame_wav_reports_zero_duration(tmp_path: Path) -> None:
    adapter = KokoroAdapter(cache_dir=tmp_path / "cache", engine=FakeEngine(frames=0))

    result = adapter.synthesize("Silence.", "af_heart", tmp_path / "unused.wav")

    assert result.duration_seconds == 0.0
