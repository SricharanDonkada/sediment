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
        if not settings.hf_token:
            raise RuntimeError(
                "HF_TOKEN is required for diarization: pyannote community-1 is a "
                "gated model. Set HF_TOKEN and accept the model terms on Hugging Face."
            )
        _pipeline = Pipeline.from_pretrained(
            settings.diarization_model,
            token=settings.hf_token,
        )
        # pyannote shares the device flag with Whisper: a single-GPU box runs both
        # on CUDA, a CPU box runs both on CPU. There is no separate diarization
        # device setting by design (MVP); revisit if split-device deploys are needed.
        if settings.whisper_device == "cuda":
            import torch

            _pipeline.to(torch.device("cuda"))
    return _pipeline


def diarize(path: str) -> list[SpeakerTurn]:
    """Diarize an audio file into a list of speaker-labeled time spans.

    community-1 returns a DiarizeOutput; iterate via .speaker_diarization
    which yields (turn, speaker) pairs (not Annotation.itertracks).
    """
    output = _load()(path)
    return [
        SpeakerTurn(start=turn.start, end=turn.end, speaker=speaker)
        for turn, speaker in output.speaker_diarization
    ]
