# core/downloader.py

from core.utils import get_ffmpeg_path

from yt_dlp import YoutubeDL
import os


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

        ydl_opts = {
            "outtmpl": output_template,
            "noplaylist": True,
            "progress_hooks": [self._progress_hook],
            "ffmpeg_location": ffmpeg_path,
        }

        # QUALIDADE
        if quality == "Full HD":
            video_format = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
        else:
            video_format = "bestvideo+bestaudio/best"

        # FORMATO
        if format_type == "MP4":
            ydl_opts.update({
                "format": video_format,
                "merge_output_format": "mp4",
                "postprocessors": [
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                }],
                "postprocessor_args": [
                    "-c:v", "copy",     # copia o vídeo sem re-encode
                    "-c:a", "aac",      # força áudio AAC
                    "-b:a", "192k"      # bitrate do áudio
                ],
            })

        elif format_type == "MP3":
            ydl_opts.update({
                "format": "bestaudio",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            })

        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            