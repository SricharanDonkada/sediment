import io
import wave

from app.audio import normalize


def _wav_params(data: bytes):
    with wave.open(io.BytesIO(data), "rb") as w:
        return w.getframerate(), w.getnchannels()


def test_normalize_bytes_to_16k_mono(stereo_44k_wav_bytes):
    out = normalize(stereo_44k_wav_bytes)
    framerate, channels = _wav_params(out)
    assert framerate == 16000
    assert channels == 1


def test_normalize_accepts_path(tmp_path, stereo_44k_wav_bytes):
    src = tmp_path / "in.wav"
    src.write_bytes(stereo_44k_wav_bytes)
    out = normalize(str(src))
    framerate, channels = _wav_params(out)
    assert framerate == 16000
    assert channels == 1


def test_normalize_rejects_garbage():
    import pytest
    from app.audio import AudioProcessingError

    with pytest.raises(AudioProcessingError):
        normalize(b"this is not audio")
