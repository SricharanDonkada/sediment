# services/extraction/tests/test_worker.py
import pytest
from app import worker
from sediment_schemas import TranscriptionMessage


def test_process_one_calls_pipeline(monkeypatch):
    calls = {}
    msg = TranscriptionMessage(object_key="abc-123.txt", bucket="transcripts")

    monkeypatch.setattr(worker.storage, "get_transcript",
                        lambda bucket, key: "SPEAKER_A: hi\n")

    def fake_run(transcript_id, text):
        calls["transcript_id"] = transcript_id
        calls["text"] = text

    monkeypatch.setattr(worker.pipeline, "run", fake_run)

    worker.process_one(msg.model_dump_json().encode())

    assert calls["transcript_id"] == "abc-123.txt"
    assert calls["text"] == "SPEAKER_A: hi\n"


def test_process_one_uses_object_key_as_transcript_id(monkeypatch):
    captured = {}
    msg = TranscriptionMessage(object_key="path/to/transcript.txt", bucket="transcripts")

    monkeypatch.setattr(worker.storage, "get_transcript", lambda b, k: "text")
    monkeypatch.setattr(worker.pipeline, "run",
                        lambda transcript_id, text: captured.update({"id": transcript_id}))

    worker.process_one(msg.model_dump_json().encode())

    assert captured["id"] == "path/to/transcript.txt"


def test_process_one_propagates_pipeline_error(monkeypatch):
    msg = TranscriptionMessage(object_key="abc.txt", bucket="transcripts")

    monkeypatch.setattr(worker.storage, "get_transcript", lambda b, k: "text")

    def boom(*a, **kw):
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr(worker.pipeline, "run", boom)

    with pytest.raises(RuntimeError, match="pipeline exploded"):
        worker.process_one(msg.model_dump_json().encode())
