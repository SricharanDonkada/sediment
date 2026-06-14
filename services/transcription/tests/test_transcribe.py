from types import SimpleNamespace

from app import transcribe
from app.merge import Segment


def test_transcribe_converts_model_segments(monkeypatch):
    fake_segments = [
        SimpleNamespace(start=0.0, end=1.0, text="  hello  "),
        SimpleNamespace(start=1.0, end=2.0, text="world"),
    ]

    class FakeModel:
        def transcribe(self, path):
            # faster-whisper returns (segments_iterable, info)
            return iter(fake_segments), SimpleNamespace(language="en")

    monkeypatch.setattr(transcribe, "_load", lambda: FakeModel())

    result = transcribe.transcribe("/tmp/whatever.wav")

    assert result == [
        Segment(start=0.0, end=1.0, text="hello"),
        Segment(start=1.0, end=2.0, text="world"),
    ]
