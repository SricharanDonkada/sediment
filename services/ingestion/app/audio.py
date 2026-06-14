import subprocess
import tempfile
from pathlib import Path


class AudioProcessingError(Exception):
    """Raised when ffmpeg fails to decode/normalize the input audio."""


def normalize(source: bytes | str, *, suffix: str = "") -> bytes:
    """Convert any audio input to 16kHz mono WAV bytes via ffmpeg.

    `source` is either raw audio bytes (upload path) or a path to an audio
    file on disk (YouTube path). `suffix` is an optional filename extension
    (e.g. ".mp3") used to hint ffmpeg's demuxer for the bytes path; it is
    ignored when `source` is a path (the path keeps its own extension).
    Returns the WAV bytes.
    """
    with tempfile.TemporaryDirectory() as d:
        if isinstance(source, bytes):
            in_path = Path(d) / f"input{suffix}"
            in_path.write_bytes(source)
        else:
            in_path = Path(source)

        out_path = Path(d) / "out.wav"
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(in_path),
                "-ar", "16000", "-ac", "1", "-f", "wav", str(out_path),
            ],
            capture_output=True,
        )
        if proc.returncode != 0 or not out_path.exists():
            raise AudioProcessingError(
                proc.stderr.decode(errors="replace")[-2000:]
            )
        return out_path.read_bytes()
