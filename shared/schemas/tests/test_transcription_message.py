from sediment_schemas import TranscriptionMessage


def test_round_trips_through_json():
    msg = TranscriptionMessage(object_key="abc123.txt", bucket="transcripts")
    raw = msg.model_dump_json()
    assert TranscriptionMessage.model_validate_json(raw) == msg


def test_requires_both_fields():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TranscriptionMessage(object_key="abc123.txt")
