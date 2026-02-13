# core/downloader.py

from core.utils import get_ffmpeg_path
from core.utils import get_ffmpeg_path, get_ytdlp_path

import os
import subprocess

class Downloader:
    def __init__(self, progress_callback=None):
        """
        progress_callback(percent: float)
        """
        self.progress_callback = progress_callback

    def _progress_hook(self, d):
        if d["status"] == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate")

            if total:
                percent = downloaded / total * 100
                if self.progress_callback:
                    self.progress_callback(percent)

        elif d["status"] == "finished":
            if self.progress_callback:
                self.progress_callback(100)

    def download(
        self,
        url: str,
        format_type: str,
        quality: str,
        output_path: str,
        filename: str,
    ):
        
        ffmpeg_path = get_ffmpeg_path()
        ytdlp_path = get_ytdlp_path()

        if not url:
            raise ValueError("URL vazia")

        if not output_path:
            raise ValueError("Pasta de destino não definida")

        # Template de saída
        if filename:
            filename = os.path.splitext(filename)[0]
            output_template = os.path.join(output_path, filename + ".%(ext)s")
        else:
            output_template = os.path.join(output_path, "%(title)s.%(ext)s")

        # QUALIDADE
        if quality == "Full HD":
            video_format = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
        else:
            video_format = "bestvideo+bestaudio/best"

        command = [
            ytdlp_path,
            url,
            "-o", output_template,
            "--ffmpeg-location", ffmpeg_path,
            "--no-playlist",
        ]

        # FORMATO
        if format_type == "MP4":
            command += [
                "-f", video_format,
                "--merge-output-format", "mp4",
                "--postprocessor-args", "ffmpeg:-c:v copy -c:a aac -b:a 192k",
            ]
        elif format_type == "MP3":
            command += [
                "-f", "bestaudio",
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "192K",
            ]
            
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            universal_newlines=True,
        )

        for line in process.stdout:
            if "[download]" in line and "%" in line:
                try:
                    percent_str = line.split("%")[0].split()[-1]
                    percent = float(percent_str)
                    if self.progress_callback:
                        self.progress_callback(percent)
                except:
                    pass

        process.wait()

        if process.returncode != 0:
            raise Exception("Erro no download com yt-dlp")
                