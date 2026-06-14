import pytest

from app import worker
from sediment_schemas import IngestionMessage, TranscriptionMessage


def test_process_one_stores_transcript_and_enqueues(monkeypatch):
    calls = {}

    msg = IngestionMessage(object_key="abc-123.wav", bucket="audio")

    monkeypatch.setattr(
        worker.storage, "get_audio", lambda bucket, key: "/tmp/abc-123.wav"
    )
    monkeypatch.setattr(worker.pipeline, "run", lambda path: "SPEAKER_A: hi\n")
    monkeypatch.setattr(worker.os, "unlink", lambda path: calls.__setitem__("unlinked", path))

    def fake_put(key, text):
        calls["put"] = (key, text)

    def fake_enqueue(message):
        calls["enqueue"] = message

    monkeypatch.setattr(worker.storage, "put_transcript", fake_put)
    monkeypatch.setattr(worker.queue, "enqueue", fake_enqueue)

    worker.process_one(msg.model_dump_json().encode())

    # Transcript key mirrors the audio stem with a .txt extension.
    assert calls["put"] == ("abc-123.txt", "SPEAKER_A: hi\n")
    assert calls["enqueue"] == TranscriptionMessage(
        object_key="abc-123.txt", bucket="transcripts"
    )
    # The temp audio file is always cleaned up.
    assert calls["unlinked"] == "/tmp/abc-123.wav"


def test_process_one_cleans_up_temp_file_on_pipeline_error(monkeypatch):
    calls = {}
    msg = IngestionMessage(object_key="abc-123.wav", bucket="audio")

    monkeypatch.setattr(worker.storage, "get_audio", lambda bucket, key: "/tmp/abc-123.wav")
    monkeypatch.setattr(worker.os, "unlink", lambda path: calls.__setitem__("unlinked", path))

    def boom(path):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(worker.pipeline, "run", boom)

    with pytest.raises(RuntimeError):
        worker.process_one(msg.model_dump_json().encode())

    assert calls["unlinked"] == "/tmp/abc-123.wav"
