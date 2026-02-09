# Video-Downloader

This project is a graphical video downloader based on **yt-dlp**.  
It uses yt-dlp as the core downloading engine and provides a clean, simple interface developed with **PySide6**, making it easier to download videos without using the command line.

## Requirements

This version requires **FFmpeg** to be installed locally in order to run properly.

## Executable

The executable file is located in the following directory: app/dist

## Features and Functionality

- Choose the output folder  
- Download videos as **MP4** or extract **audio only (MP3)**  
- Rename the file before downloading  

### Limitations

- Download progress feedback (%) is not available yet  
- Videos are always downloaded in the **highest available quality**  
- Quality selection is not supported at the moment
