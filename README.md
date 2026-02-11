# Video-Downloader 🎬

This project is a graphical video downloader based on **yt-dlp**.  
It uses yt-dlp as the core downloading engine and provides a clean, simple interface developed with **PySide6**, making it easier to download videos without using the command line.
Official yt-dlp repository: https://github.com/yt-dlp/yt-dlp

---


## 🪛 Resources (for use)

The application is fully self-contained and:
-  Does NOT require Python installed
-  Does NOT require FFmpeg installed
-  Works on any Windows machine
>*** This version cannot have yt-dlp updated without recompiling. ***

### for devs

  Check the [Project Structure](#project-structure) section — you will probably need it.

---

## ⚙️ Executable

The executable file is located in the release pages of this repository as "V2"

---

## 🪁 Features and Functionality

- Select output folder
- Download videos in **MP4 format (H.264 + AAC)**
- Support for **Full HD (1080p)** when available
- Extract audio in **MP3 (192 kbps)**
- Automatic audio + video merging
- File renaming before download
- Download progress indicator (%)
- Embedded FFmpeg and FFprobe
- Clean and simple user interface 

---

## 🛠 Built With

- Python
- PySide6 (Qt for Python)
- yt-dlp
- FFmpeg (embedded)
- PyInstaller

---

## 📦 How It Works

- yt-dlp handles video downloading
- FFmpeg merges video/audio streams and converts formats
- PySide6 provides the graphical interface
- PyInstaller packages everything into a single executable

---

## 📌 Project Structure

>core/ → Download logic and utilities
>ui/ → Interface files
>assets/ → Icons and UI resources
>tools/ → FFmpeg binaries (development only)
>main.py → Application entry point

---

## 📄 License

This project uses yt-dlp under its respective license.  
FFmpeg is distributed according to its official license terms.