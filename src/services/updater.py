# services/updater.py

""" Maybe could be a good thing implement unit tests to this file.
    Also can be a good idea implementa an APP truly auto-updater.
"""

""" Here in this file you will find just some auto-update resoucers, like:
    - YT-DLP official repository url;
    - Get-Media-Free official repository url;
    - Function to check if there's a new version of Get-Media-Free;
    - App version validators;
    - YT-DLP auto updater, downloader and replacer;
    - YT-DLP version getter to be used on UI;
"""

import os
import re
import requests
import shutil
from core.utils import get_ytdlp_path
import subprocess

""" This file is resposable to mantain the app version, and the path to check
    and get new versions of the entair Get-Media-Free binary or just yt-dlp.exe
"""


""" ==================================================
    GET-MEDIA-FREE VERSION / YT=DLP / GITHUB RELEASE
  ================================================== """

# url to get yt-dlp last version from official github
YTDLP_DOWNLOAD_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"

# Get Media Free actual version
APP_VERSION = "2.5.0"
# app oficial repo 
GITHUB_REPO = "LuizHenriqueFreitas/Get-Media-Free"
# github app releases api url
GITHUB_RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


""" ============================
      APP VERSION VALIDATION
  =========================== """

# normalize release name just to numbers
# that will just work to x.x.x named releases, other names will not be catch by auto-updater
def _parse_version(text):
    #'v2.1.0' -> (2, 1, 0). Ignores non-numeric suffixes.
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:3]) if nums else ()

# check is the newest github release is bigger (numericaly) than current version
def _is_newer(candidate, current):
    cv, curv = _parse_version(candidate), _parse_version(current)
    if not cv:
        return False
    # normalize sizes (ex.: (2,1) vs (2,0,0))
    length = max(len(cv), len(curv))
    cv += (0,) * (length - len(cv))
    curv += (0,) * (length - len(curv))
    return cv > curv


""" ========================
        CHECK APP UPDATE
  ======================== """

""" Checks the project's latest release on GitHub.
    Returns (update_available: bool, latest_version: str|None).
    In case of network or API failure, silently returns (False, None).

    That code just notifies that a new version avaliable, but doesn't auto update 
    the entire software yet.
"""
def check_app_update():
    try:
        r = requests.get(
            GITHUB_RELEASES_API,
            timeout=15,
            headers={"Accept": "application/vnd.github+json"},
        )
        if r.status_code != 200:
            return (False, None)
        tag = (r.json().get("tag_name") or "").strip()
        latest = tag.lstrip("vV").strip() or tag
        if _is_newer(tag, APP_VERSION):
            return (True, latest)
        return (False, latest)
    except Exception:
        return (False, None)


""" =============================
        YT-DLP FUNCTIONS
  ========================= """

# as the name says, tha function download the lastest official ytdlp .exe
def download_latest_ytdlp():
    ytdlp_path = get_ytdlp_path()
    temp_path = ytdlp_path + ".new"

    response = requests.get(YTDLP_DOWNLOAD_URL, stream=True, timeout=30)

    if response.status_code != 200:
        # that will need to be transtalet on location update
        raise Exception("Falha ao baixar yt-dlp")

    with open(temp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return temp_path

# this function replaces the old version for the new one
def replace_binary_ytdlp(temp_path):
    ytdlp_path = get_ytdlp_path()
    backup_path = ytdlp_path + ".backup"

    if os.path.exists(ytdlp_path):
        shutil.move(ytdlp_path, backup_path)

    shutil.move(temp_path, ytdlp_path)

    if os.path.exists(backup_path):
        os.remove(backup_path)

""" This function implements the 2 other functinos above
    "download_lastest_ytdlp()" and "replace_binary_ytdlp()".
    Is that function how check and update the yt-dlp binary
"""
def check_and_update_ytdlp():
    try:
        temp_file = download_latest_ytdlp()
        replace_binary_ytdlp(temp_file)
        # that will need to be transtalet on location update
        return True, "yt-dlp atualizado com sucesso!"
    except Exception as e:
        # that will need to be transtalet on location update
        return False, f"Error na atualização: {str(e)}"

# that is just a getter, this function get the actual version of ytdlp - probably used on UI
def get_installed_version_ytdlp():
    try:
        ytdlp_path = get_ytdlp_path()

        import os
        if os.path.isabs(ytdlp_path) and not os.path.exists(ytdlp_path):
                return "Not Found"
        
        result = subprocess.run(
            [ytdlp_path, "--version"],
            capture_output=True,
            text=True,
            timeout = 10
        )

        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return f"Erro: {result.stderr.strip()}"

    except FileNotFoundError as e:
        return f"yt-dlp não encontrado: {e}"
    except subprocess.TimeoutExpired:
        return "Timeout"
    except Exception as e:
        return f"Erro inesperado: {str(e)}"
