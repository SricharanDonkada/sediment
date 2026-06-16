from types import SimpleNamespace

from app import diarize
from app.merge import SpeakerTurn


def test_diarize_converts_annotation_tracks(monkeypatch):
    class FakeDiarizeOutput:
        speaker_diarization = [
            (SimpleNamespace(start=0.0, end=1.5), "SPEAKER_00"),
            (SimpleNamespace(start=1.5, end=2.0), "SPEAKER_01"),
        ]

    class FakePipeline:
        def __call__(self, path):
            return FakeDiarizeOutput()

    monkeypatch.setattr(diarize, "_load", lambda: FakePipeline())

    result = diarize.diarize("/tmp/whatever.wav")

    assert result == [
        SpeakerTurn(start=0.0, end=1.5, speaker="SPEAKER_00"),
        SpeakerTurn(start=1.5, end=2.0, speaker="SPEAKER_01"),
    ]


def test_load_requires_hf_token(monkeypatch):
    import pytest

    monkeypatch.setattr(diarize, "_pipeline", None)
    monkeypatch.setattr(diarize.settings, "hf_token", "")

    with pytest.raises(RuntimeError, match="HF_TOKEN"):
        diarize._load()
