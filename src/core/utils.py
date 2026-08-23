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
import subprocess

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

""" "youtube:player_client=" is the getter what ytdlp access youtube data;
    We are using "web_safari" and fallback "android_vr" because are the best quality ones
    for ower cookies browseless pipeline.
"""
# this constant will be used to extract UI info and to get the download process
YOUTUBE_CLIENT_SETTINGS = ["--extractor-args", "youtube:player_client=web_safari,android_vr"]


""" ============================
        URL VERIFICATION
  =========================== """

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
    At development: src/data/
    At executable: acessible on folder 'data', near the .exe
"""
def get_user_data_dir():
    if getattr(sys, 'frozen', False):
        # Executable: uses .exe owne directory
        base = os.path.dirname(sys.executable)
    else:
        # Dev mode: anchor to the "src" folder itself (same base used by
        # resource_path() and get_ytdlp_path()) instead of the process' cwd -
        # otherwise cookies.txt/settings.json/history.json silently end up in
        # a different "data" folder depending on where the app was launched from.
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base, "data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


""" ==========================
    TEMP FILES (thumbnails, etc.)
   ========================== """

""" Return the directory for short-lived temp files (ex.: preview thumbnails).
    Uses the same base as get_user_data_dir() so it's always an absolute path
    next to the .exe / project root, instead of relative to whatever the
    process' current working directory happens to be.
"""
def get_temp_dir():
    temp_dir = os.path.join(get_user_data_dir(), "temp")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir

""" Return the directory for thumbnails that must survive across app restarts
    (ex.: history cards). Separate from get_temp_dir() on purpose: that one is
    wiped on every startup by clear_temp_dir(), which would otherwise delete
    history thumbnails still referenced by history.json.
"""
def get_thumbnails_dir():
    thumbs_dir = os.path.join(get_user_data_dir(), "thumbnails")
    os.makedirs(thumbs_dir, exist_ok=True)
    return thumbs_dir

""" Wipe every file inside the temp dir. Safe to call on app startup as a
    safety net for thumbnails that were never cleaned up (crash, force-quit,
    dialog closed in an unexpected way).
"""
def clear_temp_dir():
    temp_dir = get_temp_dir()
    for name in os.listdir(temp_dir):
        path = os.path.join(temp_dir, name)
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass

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
    # Dev mode: anchor to the "src" folder itself instead of the process' cwd,
    # matching where bundled resources (bin/, tools/, assets/) actually live
    # regardless of where the app was launched from.
    src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(src_dir, relative_path)

""" Check bay resource_path() function if running on Windows,
    is the user is on Linux, exemple, he need to has localy installed
    or get an exeption. 
    The same logic is apply to:
        get_ytdlp_path();
        get_ffmpeg_path();
        get_node_path();
"""

# runs "<path> --version" to confirm the bundled binary actually executes on
# this OS/arch before trusting it. Without this, a bin/yt-dlp(.exe) that is
# the wrong platform's binary (ex.: a Windows .exe copied into bin/yt-dlp on
# Linux) gets returned as-is, and every caller crashes with an uncaught
# OSError("Exec format error") instead of falling back to the system yt-dlp.
def _ytdlp_binary_runs(path):
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(
            [path, "--version"],
            capture_output=True, text=True, timeout=5,
            creationflags=creationflags,
        )
        return result.returncode == 0
    except Exception:
        return False

#Logic explained above
def get_ytdlp_path():
    if sys.platform == "win32":

        current_dir = os.path.dirname(os.path.abspath(__file__))
        bin_path = os.path.join(current_dir, "..", "bin", "yt-dlp.exe")
        bin_path = os.path.normpath(bin_path)

        if os.path.exists(bin_path) and _ytdlp_binary_runs(bin_path):
            return bin_path

        yt_dlp = shutil.which('yt-dlp.exe')
        if yt_dlp:
            return yt_dlp
        raise Exception(
            f"yt-dlp não encontrado em: {bin_path}\n"
            f"Verifique se o arquivo está em: src/bin/yt-dlp.exe"
        )
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        bin_path = os.path.join(current_dir, "..", "bin", "yt-dlp")
        bin_path = os.path.normpath(bin_path)

        if os.path.exists(bin_path) and os.access(bin_path, os.X_OK) and _ytdlp_binary_runs(bin_path):
            return bin_path

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

# yt-dlp's JS challenge solver (used to resolve youtube signature/n-challenge)
# refuses to run below this version, older node just silently fails to solve
# the challenge and youtube ends up returning HTTP 403 on the video formats.
NODE_MIN_MAJOR_VERSION = 22

# runs "node --version" and checks against NODE_MIN_MAJOR_VERSION
# returns True if the version could not be determined, so we don't block
# on a candidate just because parsing failed
def _node_version_supported(node_path):
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(
            [node_path, "--version"],
            capture_output=True, text=True, timeout=5,
            creationflags=creationflags,
        )
        major = int(result.stdout.strip().lstrip("v").split(".")[0])
        return major >= NODE_MIN_MAJOR_VERSION
    except Exception:
        return True

#Logic explained above
def get_node_path():
    outdated_path = None

    if sys.platform == "win32":
        # Windows: look for the embedded binary first (bundled with the .exe),
        # then fall back to whatever "node" is available on the system PATH.
        node_paths = [
            resource_path("bin/node/node.exe"),
            resource_path("node.exe"),
        ]
        for path in node_paths:
            if os.path.exists(path):
                if _node_version_supported(path):
                    return path
                outdated_path = path

        node = shutil.which("node") or shutil.which("node.exe")
        if node:
            if _node_version_supported(node):
                return node
            outdated_path = node
    else:
        # linux search for local node installed on the system
        node = shutil.which('node')
        if node:
            if _node_version_supported(node):
                return node
            outdated_path = node

    if outdated_path:
        # that need to be translated with location update
        raise Exception(
            f"Node.js encontrado em '{outdated_path}' está desatualizado "
            f"(precisa ser versão {NODE_MIN_MAJOR_VERSION} ou superior).\n"
            "Linux: use nvm (https://github.com/nvm-sh/nvm) para instalar uma versão recente\n"
            "Windows: baixe em https://nodejs.org/"
        )

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