# core/utils.py

""" Here you will find:
     - URL validations;
     - Save file validations;
     - Get dependecies by path;
     - Cookies storage manipulation;
"""

import sys
import os
import re
import stat
import shutil

"""==========================
   Plataform filters
   yt-dlp has access to diferent content plataforms,
   here we normalyze just more usefull and stable ones.
   =========================="""

# This dicttionary make the plataform link normalized
_PLATFORM_DOMAINS = {
    "youtube": ("youtube.com", "youtu.be", "youtube-nocookie.com"),
    "tiktok": ("tiktok.com",),
    "instagram": ("instagram.com", "instagr.am"),
    "facebook": ("facebook.com", "fb.watch", "fb.com"),
    "twitter": ("twitter.com", "x.com"), #on tha software X is called twitter because is a better name
    "vimeo": ("vimeo.com",),
    "twitch": ("twitch.tv",),
    # if you want to add more lonk normalizations put their here
}

# Identify the plataform using current URL. Return 'generic' if unknow.
# or return a key from _PLATAFORM_DOMAINS dictionary.
def detect_platform(url: str) -> str:
    if not url:
        return "generic"
    u = url.lower()
    for platform, domains in _PLATFORM_DOMAINS.items():
        if any(d in u for d in domains):
            return platform
    return "generic"

# verify if looks like a https link by sintax
def looks_like_url(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"https?://[^\s]+", text.strip()))

# bool function - verify if the plataform is youtube
""" Identify youtube links is important because need to 
    provide trim and playlist options. 
"""
def is_youtube(url: str) -> bool:
    return detect_platform(url) == "youtube"

# bool function - verify if is a youtube playlis using url sintax
def is_youtube_playlist(url: str) -> bool:
    # True if the URL was a playlist from YouTube (with sintax "list=" or "/playlist" on the url).
    if not is_youtube(url):
        return False
    u = url.lower()
    return ("list=" in u) or ("/playlist" in u)


""" ==========================
    FILE NAME VALIDATION TO SAVE
   ========================== """

# Windows file name blocked characters
INVALID_FILENAME_CHARS = '\\/:*?"<>|'

# searche for blocked characters at the file name
def invalid_filename_chars(name: str):
    """Return a ordened list of blocked caracters at the file name."""
    if not name:
        return []
    found = []
    for c in name:
        if c in INVALID_FILENAME_CHARS and c not in found:
            found.append(c)
    return found

# verify name function - call "invalid_filename_chars()"
def is_valid_filename(name: str) -> bool:
    """True is has no blocked characters and is not null."""
    return bool(name and name.strip()) and not invalid_filename_chars(name)


""" ==========================
    CONFLICT FILE NAMES
   ========================== """

# Remove invalid caracters to file names.
def safe_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name or "").strip() or "video"

# Final extension for the format choiced.
def expected_extension(format_type: str) -> str:
    # caso format_type.upper() equals "MP3", so return mp3, else mp4
    return "mp3" if (format_type or "").upper() == "MP3" else "mp4"

# get the probably file last path (folder/title.ext).
def expected_output_path(folder: str, title: str, format_type: str) -> str:
    ext = expected_extension(format_type)
    return os.path.join(folder, f"{safe_filename(title)}.{ext}")

# verify duplicated names and type
def file_conflict(folder: str, title: str, format_type: str) -> bool:
    # True if has another file with same name and type at same folder.
    return os.path.exists(expected_output_path(folder, title, format_type))

""" Return a alternative title different of other arquives.
    Ex.: 'video' -> 'video (1)' -> 'video (2)' ...
"""
def resolve_unique_title(folder: str, title: str, format_type: str) -> str:
    base = safe_filename(title)
    if not file_conflict(folder, base, format_type):
        return base
    i = 1
    while True:
        candidate = f"{base} ({i})"
        if not file_conflict(folder, candidate, format_type):
            return candidate
        i += 1


""" ==========================
    USER DATA FOLDER (persistence)
   ========================== """

""" Return the directory where stay the user data (cookies, history, etc.)
    At development: .src/data/
    At executable: acessible on folder 'data', near the .exe
"""
# maybe that needs to be checked about data/ instance path
def get_user_data_dir():
    if getattr(sys, 'frozen', False):
        # Executable: uses .exe owne directory
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.abspath(".")
    data_dir = os.path.join(base, "data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


""" ==========================
    INTERNAL RESOURCES (packed on .exe).
    embbed dependencies at runtime, 
    need to be founded during development.
   ========================== """

""" Return the correct path to internal resources (bin, tools, assets)
    that will be packed inside executable (only read).
"""
# generic finder path function - will be used by other metods below.
def resource_path(relative_path):
    
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

""" Check bay resource_path() function if running on Windows,
    is the user is on Linux, exemple, he need to has localy installed
    or get an exeption. 
    The same logic is apply to:
        get_ytdlp_path();
        get_ffmpeg_path();
        get_node_path();
"""

#Logic explained above
def get_ytdlp_path():
    if sys.platform == "win32":
        return resource_path("bin/yt-dlp.exe")
    else:
        yt_dlp = shutil.which('yt-dlp')
        if yt_dlp:
            return yt_dlp

        # that need to be translated with location update
        raise Exception("yt-dlp não encontrado. Instale com: pip install yt-dlp")

#Logic explained above
def get_ffmpeg_path():
    if sys.platform == "win32":
        return resource_path("tools/ffmpeg/bin/")
    else:
        ffmpeg = shutil.which('ffmpeg')
        if ffmpeg:
            return ffmpeg

        # that need to be translated with location update
        raise Exception("FFmpeg não encontrado. Instale com: sudo apt install ffmpeg")

#Logic explained above
def get_node_path():
    if sys.platform == "win32":
        # Windows: look for diferent path types
        node_paths = [
            resource_path("bin/node/node.exe"),
            resource_path("node.exe"),
            "node.exe",
            "node"
        ]
    else:
        node = shutil.which('node')
        if node:
            return node

    # that need to be translated with location update
    raise Exception(
        "Node.js não encontrado!\n Linux: Instale com 'sudo apt install nodejs' ou use nvm"
    )


""" ==========================
    USER DATA (COOKIES, ETC)
  ========================== """

# cookies.txt path using get_user_data_dir() function
def get_cookies_path():
    return os.path.join(get_user_data_dir(), "cookies.txt")

# check if cookies.txt exists on user data folder
def cookies_exists():
    return os.path.exists(get_cookies_path())

# Set permissions to cookie.txt file (Unix: 600, Windows: readonly).
# that is a low level secury implementation, because you will have
# the same file on your downloads if doesn't delete.
def secure_cookies_file(path: str):
    if not os.path.exists(path):
        return
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except:
        try:
            os.chmod(path, stat.S_IREAD)
        except:
            pass

# save the cookies.txt inside user data folder
def save_cookies(content: bytes):
    path = get_cookies_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    secure_cookies_file(path)


""" ============================
    ADITIONAL FUNCTIONS
   ==========================="""

# Return the complete path to ffmpeg executable.
def get_ffmpeg_exe():
    import sys as _sys
    bin_dir = get_ffmpeg_path()
    exe = "ffmpeg.exe" if _sys.platform == "win32" else "ffmpeg"
    full = os.path.join(bin_dir, exe)
    if os.path.exists(full):
        return full
    # fallback for ffmpeg of PATH
    return exe