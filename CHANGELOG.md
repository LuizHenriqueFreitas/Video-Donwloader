# Changelog 

All notable changes to this project will be documented in this file.

---

## 2026-23-08

- Fix playlist download errors.
- Fix dialog problens.
- Fix advanced mode crash problems.

---

## 2026-28-07

- New web site avaliable, full vibe coded just to provide a more simple space to user download the .exe - made with github API.

Next steps:
- fix tmp folder gaps.
- change all folder path to relative.

---

## 2026-27-07

All files are beeing checked and documented in english.<br>
*(maybe a strange englis because i'm praticing my english while i make this)*

Now i'm reading and understanding all the code, adding usefull comments and really
document as much as i can, so i think it's good.

Also learning a little about some concepts used on this project, like threading process, 
pyside and pytest documentation and thinking about some code aproatments.

Next steps:   
- Learning more about pytest and check, documentate and translate all unit test files (right now all full generateds by free cloud code).   
- Learning more about pyside and check all ui files.
- Add a full clear history button.
- Add more Ux resources like explanations, warning boxes and life quality things.

---

## 2026-24-07

From this point on, this project will be taken seriously.

Docs folder was addes, as src folder with the source code.

Each file on Docs/ talk about a part of the development, check them for more information.

Next steps, seriously implementation of pytest, code review and refatoration when necessary.
> **utils.py** and **video_info.py** already were revised and full translated to english (the code).

> These files unity test were built using claude.ai, free plan, and will be revised and translated before next release.

I'm reading now for the  very first time, the pytest and pyside documentation, the is enought AI on this tool. Ai will be used just to accelerate the process.

---

## 2026-12-06

### Added
- Outhers social media download suport (instagram, tiktok, X, etc)
- Cut editor before download
- Download Youtube Playlists are suported now
- UI enhancements for life quality
- Semi complete Auto-Update implemented

### Improved
- Now it's possible Download Videos from:
    1. Youtube
    2. Instragram
    3. Tiktok
    4. X <br>
    5. *and probably more*<br>
    
    >**Only paste the media link**

- More Buttons and options for simple user
    - Remove vídeos from historic
    - Select between historic of 10, 20 and 50 videos
    - You can copy the original vídeo link from a button on video card

- Now is possible to download playlists
    - all videos from playlist will be with the original titles
    - automatic quality is always 1080p ou better possible
    > if you want to get a 4k or 8k video, need to do individual
    - you have a window specific for playlist manage

- You can edit the video before donwload
    - With the new tool: Advanced Mode is possibe to cut just a session of the original media to download a little file
    - This is useful whe you have a large content like a live stream, and need just a small part
    - Good too for people how don't have too much space on disk to download more content
    
    **Atention**
    > Your clip size is not visible before donwload the vídeo
    ***

## [v 2.0.0] - 2026-04-03

### Added
- Refactor archtecture
- New controler
- New service
- New historic system
- New UI
- New dynamic quality selector
- Some simple tests implementation
- Instalation_Setup
- Now you can Cancel a Download

### Improved
- Better user Interface 
    - With historic (20 last videos)
    - Open file button
    - Open file folder button
    - Video info
        - Resolution 
        - Size(MBs/GBs)
        - Original video title
        - New title

### FIxed
- Now youtube need cookies to you access videos high quality data
> Now you need to provide browser cookies.txt to download a yotube video | local storage
- Also, now we have nodeJs embedded, because youtube use this to check you're not a bot
- Fix progress bar level

## [v 1.3.0] - 2026-02-13

### Added
- Embedded yt-dlp
- yt-dlp auto update resource

### Improved 
- Better user experience with embedded resources

## [v 1.0.0] - 2026-02-11

### Added
- Embedded FFmpeg and FFprobe
- Download progress percentage indicator
- Full HD (1080p) quality option
- MP4 output with H.264 + AAC
- MP3 extraction (192kbps)
- Standalone executable (no external dependencies required)

### Fixed
- Audio codec incompatibility (Opus → AAC)
- 360p limitation when FFmpeg was missing

### Improved
- Download stability
- Format selection logic
- Packaging with PyInstaller

---

## [alpha 0.1.0] - 2026-02-09

### Initial Release
- Basic video download
- MP4 and MP3 support
- Manual FFmpeg dependency
