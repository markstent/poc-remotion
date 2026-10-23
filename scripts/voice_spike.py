"""Synthesise candidate TTS voice samples with Kokoro ONNX for the user to pick by ear.

Downloads the Kokoro v1.0 ONNX model and voice bank on first use (a few hundred
megabytes, cached under data/voice_samples/.models which is gitignored), renders
the sample sentence with three female voices and writes one WAV per voice into
data/voice_samples/<voice>.wav.

Usage: uv run python scripts/voice_spike.py
"""

from __future__ import annotations

import sys
import urllib.request
import wave
from pathlib import Path

import numpy as np
from kokoro_onnx import Kokoro
from numpy.typing import NDArray

MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/kokoro-v1.0.onnx"
)
VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/voices-v1.0.bin"
)

SAMPLE_TEXT = (
    "Before you answer, ask me any clarifying questions. Better prompts, better results."
)
VOICES = ["af_heart", "af_bella", "bf_emma"]

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_CACHE = REPO_ROOT / "data" / "voice_samples" / ".models"
OUTPUT_DIR = REPO_ROOT / "data" / "voice_samples"


def download(url: str, destination: Path) -> None:
    """Download url to destination with a simple progress readout."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}")
    with urllib.request.urlopen(url) as response, destination.open("wb") as out:
        total = int(response.headers.get("Content-Length", 0))
        downloaded = 0
        while chunk := response.read(1 << 20):
            out.write(chunk)
            downloaded += len(chunk)
            if total:
                percent = downloaded * 100 // total
                print(
                    f"\r  {downloaded / 1e6:8.1f} MB ({percent}%)",
                    end="",
                    flush=True,
                )
    print()


def ensure_model_files() -> tuple[Path, Path]:
    """Return paths to the Kokoro model and voice bank, downloading if missing."""
    model_path = MODEL_CACHE / "kokoro-v1.0.onnx"
    voices_path = MODEL_CACHE / "voices-v1.0.bin"
    for url, path in ((MODEL_URL, model_path), (VOICES_URL, voices_path)):
        if not path.exists():
            download(url, path)
    return model_path, voices_path


def write_wav(path: Path, samples: NDArray[np.float32], sample_rate: int) -> None:
    """Write mono 16-bit PCM samples to a WAV file."""
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def main() -> int:
    """Synthesise the sample sentence with each candidate voice and save WAVs."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model_path, voices_path = ensure_model_files()
    print("Loading Kokoro model...")
    kokoro = Kokoro(str(model_path), str(voices_path))
    for voice in VOICES:
        print(f"Synthesising {voice}...")
        samples, sample_rate = kokoro.create(SAMPLE_TEXT, voice=voice, speed=1.0)
        out_path = OUTPUT_DIR / f"{voice}.wav"
        write_wav(out_path, samples, sample_rate)
        print(f"  wrote {out_path} ({out_path.stat().st_size} bytes)")
    print("Done. Listen to the samples and pick a voice.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
