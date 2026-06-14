import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def stereo_44k_wav_bytes() -> bytes:
    """A 1-second 440Hz tone, 44.1kHz stereo WAV — deliberately NOT 16k mono,
    so normalization has something real to do. Generated with ffmpeg."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "in.wav"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=440:duration=1",
                "-ac", "2", "-ar", "44100", str(out),
            ],
            check=True,
            capture_output=True,
        )
        return out.read_bytes()


@pytest.fixture(scope="session")
def mp3_bytes() -> bytes:
    """A 1-second 440Hz tone encoded as MP3 — a compressed format, to exercise
    the bytes path with something other than WAV."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "in.mp3"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=440:duration=1",
                "-ac", "2", "-ar", "44100", "-codec:a", "libmp3lame", str(out),
            ],
            check=True,
            capture_output=True,
        )
        return out.read_bytes()
