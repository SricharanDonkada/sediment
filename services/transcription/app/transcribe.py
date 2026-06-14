from faster_whisper import WhisperModel

from app.config import settings
from app.merge import Segment

_model: WhisperModel | None = None


def _load() -> WhisperModel:
    """Lazily load the faster-whisper model once per process."""
    global _model
    if _model is None:
        _model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    return _model


def transcribe(path: str) -> list[Segment]:
    """Transcribe an audio file into a list of timestamped segments."""
    segments, _info = _load().transcribe(path)
    return [
        Segment(start=s.start, end=s.end, text=s.text.strip()) for s in segments
    ]
