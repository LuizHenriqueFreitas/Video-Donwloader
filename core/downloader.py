from yt_dlp import YoutubeDL
import os


class Downloader:
    def __init__(self):
        pass

    def download(self, url, format_type, output_path, filename):
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
    
        # Opções base
        ydl_opts = {
            "outtmpl": output_template,
            "noplaylist": True,
        }

        # Formato selecionado
        if format_type == "MP4":
            ydl_opts.update({
                "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
                "merge_output_format": "mp4",
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

        # Download normal (MP4 ou MP3)
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    def _download_mp4(self, url, output_template):
        opts = {
            "outtmpl": output_template,
            "format": "bestvideo+bestaudio/best",
            "noplaylist": True,
            "postprocessors": [{"preferredcodec": "mp4"}]
        }

        with YoutubeDL(opts) as ydl:
            ydl.download([url])

    def _download_mp3(self, url, output_template):
        opts = {
            "outtmpl": output_template,
            "format": "bestaudio",
            "noplaylist": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

        with YoutubeDL(opts) as ydl:
            ydl.download([url])
