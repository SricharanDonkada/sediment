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
