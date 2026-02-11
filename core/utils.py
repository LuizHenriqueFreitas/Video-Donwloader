# core/utils.py
import sys
import os


def resource_path(relative_path):
    """
    Retorna caminho correto tanto em dev quanto em exe (PyInstaller)
    """
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def get_ffmpeg_path():
    """
    Retorna o diretório onde está o ffmpeg
    Funciona tanto em desenvolvimento quanto no executável
    """
    if getattr(sys, "frozen", False):
        # Dentro do EXE
        return resource_path("tools/ffmpeg/bin/")
    else:
        # Em desenvolvimento
        return resource_path("tools/ffmpeg/bin/")
