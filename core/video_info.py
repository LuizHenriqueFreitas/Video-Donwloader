# core/video_info.py

from yt_dlp import YoutubeDL


class VideoInfo:
    def __init__(self):
        self.ydl_opts = {
            "quiet": True,
            "skip_download": True,
        }

    def extract(self, url):
        if not url:
            raise ValueError("URL vazia")

        with YoutubeDL(self.ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        return {
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "formats": info.get("formats", []),
            "height": info.get("height"),
        }
