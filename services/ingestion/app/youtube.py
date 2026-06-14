import tempfile
from pathlib import Path

import yt_dlp


class YouTubeDownloadError(Exception):
    """Raised when yt-dlp cannot download audio for the given URL."""


def download(url: str) -> str:
    """Download best available audio for `url` to a temp file. Returns the
    path. Caller is responsible for normalizing and cleaning up the file.
    """
    tmp_dir = tempfile.mkdtemp(prefix="ytdl-")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(Path(tmp_dir) / "%(id)s.%(ext)s"),
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
    except Exception as exc:  # noqa: BLE001 — surface any yt-dlp failure uniformly
        raise YouTubeDownloadError(str(exc)) from exc
