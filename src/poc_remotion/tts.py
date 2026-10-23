"""TTS configuration loading and the content-addressed Kokoro adapter."""

import hashlib
import json
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from kokoro_onnx import Kokoro


class TTSConfigError(Exception):
    """Raised when the TTS config file is missing or invalid."""


class TTSConfig(BaseModel):
    """Voice pick from config/tts.json."""

    engine: Literal["kokoro-onnx"]
    voice: str


class TtsResult(BaseModel):
    """A synthesised wav file plus its measured duration."""

    path: str
    duration_seconds: float


class TtsEngine(Protocol):
    """Anything that can render text to a wav file."""

    def synthesize(self, text: str, voice: str, out_path: Path) -> None: ...


def load_tts_config(path: Path = Path("config/tts.json")) -> TTSConfig:
    """Load and validate the TTS voice pick from ``path``."""
    if not path.is_file():
        raise TTSConfigError(f"TTS config file not found: {path}")
    try:
        return TTSConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise TTSConfigError(f"Invalid TTS config file: {path}: {exc}") from exc


def _wav_duration_seconds(path: Path) -> float:
    """Measure wav duration as frames / framerate; a 0-frame wav reports 0.0."""
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        framerate = wav.getframerate()
    if frames == 0:
        return 0.0
    return frames / framerate


# kokoro-onnx's create() takes misaki language tags ("en-us"/"en-gb"),
# not the bare voice-prefix letters derived above.
_LANG_TAGS = {"a": "en-us", "b": "en-gb"}


def _build_engine(voice: str) -> TtsEngine:
    """Build the real kokoro-onnx engine, importing kokoro lazily.

    ``voice`` only selects the language variant here; the voice itself is a
    synthesize() argument (ruling R-C1: the adapter never reads the config).
    """
    lang_code = voice.split("_", 1)[0][:1]
    if lang_code not in ("a", "b"):
        lang_code = "a"
    from kokoro_onnx import Kokoro  # lazy import: keeps kokoro off the import path

    return _KokoroOnnxEngine(Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin"), lang_code)


class _KokoroOnnxEngine:
    """TtsEngine backed by a kokoro-onnx pipeline."""

    def __init__(self, kokoro: "Kokoro", lang_code: str) -> None:
        self._kokoro = kokoro
        self._lang_code = lang_code

    def synthesize(self, text: str, voice: str, out_path: Path) -> None:
        samples, sample_rate = self._kokoro.create(
            text, voice=voice, lang=_LANG_TAGS.get(self._lang_code, "en-us")
        )
        with wave.open(str(out_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(int(sample_rate))
            wav.writeframes((samples * 32767).astype("int16").tobytes())


class KokoroAdapter:
    """Text-to-speech adapter with content-addressed caching.

    Output always lands at ``cache_dir / sha256(voice + "\\n" + text)[:16].wav``;
    an existing cache file short-circuits the engine. ``engine`` is built
    lazily on first use when not supplied. The ``out_path`` argument exists
    for protocol symmetry with TtsEngine; the cache key decides the location.
    """

    def __init__(self, cache_dir: Path, engine: TtsEngine | None = None) -> None:
        self._cache_dir = cache_dir
        self._engine = engine

    def synthesize(self, text: str, voice: str, out_path: Path) -> TtsResult:
        """Synthesize ``text`` with ``voice``, returning the cached wav."""
        digest = hashlib.sha256(f"{voice}\n{text}".encode()).hexdigest()[:16]
        cache_path = self._cache_dir / f"{digest}.wav"
        if not cache_path.exists():
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._engine_for(voice).synthesize(text, voice, cache_path)
        return TtsResult(
            path=str(cache_path), duration_seconds=_wav_duration_seconds(cache_path)
        )

    def _engine_for(self, voice: str) -> TtsEngine:
        if self._engine is None:
            self._engine = _build_engine(voice)
        return self._engine
