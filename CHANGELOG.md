# Changelog 

All notable changes to this project will be documented in this file.

---

## [Beta 1.0.0] - 2026-02-11

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
