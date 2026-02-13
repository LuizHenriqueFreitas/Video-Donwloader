# core/video_info.py

import subprocess
import json
from core.utils import get_ytdlp_path

class VideoInfo:
    def extract(self, url):
        if not url:
            raise ValueError("URL vazia")

        ytdlp_path = get_ytdlp_path()

        command = [
            ytdlp_path,
            "-j",
            url
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise Exception("Erro ao extrair informações")

        info = json.loads(result.stdout)

        return {
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "formats": info.get("formats", []),
            "height": info.get("height"),
        }
    