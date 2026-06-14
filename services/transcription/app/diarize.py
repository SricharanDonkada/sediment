from pyannote.audio import Pipeline

from app.config import settings
from app.merge import SpeakerTurn

_pipeline: Pipeline | None = None


def _load() -> Pipeline:
    """Lazily load the pyannote diarization pipeline once per process.

    Requires HF_TOKEN and acceptance of the community-1 model terms on
    Hugging Face.
    """
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline.from_pretrained(
            settings.diarization_model,
            use_auth_token=settings.hf_token or None,
        )
        if settings.whisper_device == "cuda":
            import torch

            _pipeline.to(torch.device("cuda"))
    return _pipeline


def diarize(path: str) -> list[SpeakerTurn]:
    """Diarize an audio file into a list of speaker-labeled time spans."""
    annotation = _load()(path)
    return [
        SpeakerTurn(start=segment.start, end=segment.end, speaker=speaker)
        for segment, _track, speaker in annotation.itertracks(yield_label=True)
    ]
