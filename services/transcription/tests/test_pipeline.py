from app import pipeline
from app.merge import Segment, SpeakerTurn


def test_run_wires_transcribe_diarize_and_merge(monkeypatch):
    monkeypatch.setattr(
        pipeline.transcribe,
        "transcribe",
        lambda path: [Segment(start=0.0, end=1.0, text="hello world")],
    )
    monkeypatch.setattr(
        pipeline.diarize,
        "diarize",
        lambda path: [SpeakerTurn(start=0.0, end=1.0, speaker="SPEAKER_00")],
    )

    assert pipeline.run("/tmp/audio.wav") == "SPEAKER_A: hello world\n"
