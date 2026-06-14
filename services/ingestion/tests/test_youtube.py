from pathlib import Path

import pytest

from app import youtube
from app.youtube import YouTubeDownloadError


class _FakeYDL:
    """Stands in for yt_dlp.YoutubeDL. Writes a fake audio file where the
    real downloader would, and reports that path via prepare_filename."""

    def __init__(self, opts):
        self._outtmpl = opts["outtmpl"]
        self._written = self._outtmpl.replace("%(ext)s", "m4a")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download):
        Path(self._written).write_bytes(b"fake-audio")
        return {"id": "vid", "ext": "m4a"}

    def prepare_filename(self, info):
        return self._written


def test_download_returns_existing_path(monkeypatch):
    monkeypatch.setattr(youtube.yt_dlp, "YoutubeDL", _FakeYDL)
    path = youtube.download("https://youtu.be/abc")
    assert Path(path).exists()
    assert Path(path).read_bytes() == b"fake-audio"


def test_download_wraps_errors(monkeypatch):
    def _boom(opts):
        raise RuntimeError("video unavailable")

    monkeypatch.setattr(youtube.yt_dlp, "YoutubeDL", _boom)
    with pytest.raises(YouTubeDownloadError):
        youtube.download("https://youtu.be/bad")
