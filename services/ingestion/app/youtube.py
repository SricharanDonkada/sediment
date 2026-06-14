import shutil
import tempfile
from pathlib import Path

import yt_dlp


class YouTubeDownloadError(Exception):
    """Raised when yt-dlp cannot download audio for the given URL."""


def download(url: str) -> str:
    """Download best available audio for `url` to a fresh temp directory.

    Returns the path to the downloaded file. On success the caller owns the
    returned file AND its parent temp directory (remove the directory when
    done). On failure the temp directory is cleaned up here before raising.
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
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise YouTubeDownloadError(str(exc)) from exc
