from sediment_schemas import IngestionMessage


def test_round_trips_through_json():
    msg = IngestionMessage(object_key="abc123.wav", bucket="audio")
    raw = msg.model_dump_json()
    assert IngestionMessage.model_validate_json(raw) == msg


def test_requires_both_fields():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        IngestionMessage(object_key="abc123.wav")
