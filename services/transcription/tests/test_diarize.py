from types import SimpleNamespace

from app import diarize
from app.merge import SpeakerTurn


def test_diarize_converts_annotation_tracks(monkeypatch):
    track_a = SimpleNamespace(start=0.0, end=1.5)
    track_b = SimpleNamespace(start=1.5, end=2.0)

    class FakeAnnotation:
        def itertracks(self, yield_label=False):
            # pyannote yields (segment, track_id, speaker_label)
            yield track_a, "_", "SPEAKER_00"
            yield track_b, "_", "SPEAKER_01"

    class FakePipeline:
        def __call__(self, path):
            return FakeAnnotation()

    monkeypatch.setattr(diarize, "_load", lambda: FakePipeline())

    result = diarize.diarize("/tmp/whatever.wav")

    assert result == [
        SpeakerTurn(start=0.0, end=1.5, speaker="SPEAKER_00"),
        SpeakerTurn(start=1.5, end=2.0, speaker="SPEAKER_01"),
    ]
