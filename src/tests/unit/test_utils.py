# Translate and revise

"""
Testes para core/utils.py

Cobrem:
    - Detecção e normalização de plataformas / URLs
    - Validação de nomes de arquivo
    - Resolução de conflitos de nome de arquivo
    - Diretório de dados do usuário
    - Resolução de caminhos de recursos internos (yt-dlp, ffmpeg, node)
    - Armazenamento e permissões do cookies.txt
    - Função auxiliar get_ffmpeg_exe
"""

import os
import stat
import sys
import shutil
import pytest

from core import utils


# ---------------------------------------------------------------------------
# detect_platform
# ---------------------------------------------------------------------------

class TestDetectPlatform:

    @pytest.mark.parametrize("url, expected", [
        ("https://www.youtube.com/watch?v=abc123", "youtube"),
        ("https://youtu.be/abc123", "youtube"),
        ("https://www.youtube-nocookie.com/embed/abc123", "youtube"),
        ("https://www.tiktok.com/@user/video/123", "tiktok"),
        ("https://www.instagram.com/p/abc123/", "instagram"),
        ("https://instagr.am/p/abc123/", "instagram"),
        ("https://www.facebook.com/watch/?v=123", "facebook"),
        ("https://fb.watch/abc123/", "facebook"),
        ("https://fb.com/abc123", "facebook"),
        ("https://twitter.com/user/status/123", "twitter"),
        ("https://x.com/user/status/123", "twitter"),
        ("https://vimeo.com/123456", "vimeo"),
        ("https://www.twitch.tv/somechannel", "twitch"),
    ])
    def test_known_platforms(self, url, expected):
        assert utils.detect_platform(url) == expected

    def test_unknown_platform_returns_generic(self):
        assert utils.detect_platform("https://example.com/video/1") == "generic"

    def test_empty_string_returns_generic(self):
        assert utils.detect_platform("") == "generic"

    def test_none_returns_generic(self):
        assert utils.detect_platform(None) == "generic"

    def test_is_case_insensitive(self):
        assert utils.detect_platform("HTTPS://WWW.YOUTUBE.COM/watch?v=X") == "youtube"

    def test_substring_domain_match_is_naive(self):
        # documenta o comportamento atual: o matching é feito por substring,
        # então um domínio "fake-youtube.com.evil.com" também seria detectado
        # como youtube. Isso é uma limitação conhecida da implementação.
        assert utils.detect_platform("https://fake-youtube.com.evil.com/x") == "youtube"


# ---------------------------------------------------------------------------
# looks_like_url
# ---------------------------------------------------------------------------

class TestLooksLikeUrl:

    @pytest.mark.parametrize("text", [
        "https://youtube.com/watch?v=abc",
        "http://example.com",
        "  https://example.com  ",
        "check this out https://example.com/video",
    ])
    def test_valid_url_like_strings(self, text):
        assert utils.looks_like_url(text) is True

    @pytest.mark.parametrize("text", [
        "",
        None,
        "not a url",
        "www.example.com",  # sem esquema http(s)
        "ftp://example.com",
    ])
    def test_invalid_url_like_strings(self, text):
        assert utils.looks_like_url(text) is False


# ---------------------------------------------------------------------------
# is_youtube / is_youtube_playlist
# ---------------------------------------------------------------------------

class TestIsYoutube:

    def test_youtube_url(self):
        assert utils.is_youtube("https://www.youtube.com/watch?v=abc") is True

    def test_non_youtube_url(self):
        assert utils.is_youtube("https://www.tiktok.com/@user/video/1") is False

    def test_empty_url(self):
        assert utils.is_youtube("") is False


class TestIsYoutubePlaylist:

    def test_playlist_query_param(self):
        url = "https://www.youtube.com/watch?v=abc&list=PLxyz"
        assert utils.is_youtube_playlist(url) is True

    def test_playlist_path(self):
        url = "https://www.youtube.com/playlist?list=PLxyz"
        assert utils.is_youtube_playlist(url) is True

    def test_regular_youtube_video_is_not_playlist(self):
        url = "https://www.youtube.com/watch?v=abc"
        assert utils.is_youtube_playlist(url) is False

    def test_non_youtube_url_is_never_playlist(self):
        # mesmo contendo "list=" não é playlist se não for youtube
        url = "https://www.tiktok.com/list=123"
        assert utils.is_youtube_playlist(url) is False

    def test_case_insensitive_playlist_marker(self):
        url = "https://www.youtube.com/PLAYLIST?LIST=abc"
        assert utils.is_youtube_playlist(url) is True


# ---------------------------------------------------------------------------
# invalid_filename_chars / is_valid_filename
# ---------------------------------------------------------------------------

class TestInvalidFilenameChars:

    def test_no_invalid_chars(self):
        assert utils.invalid_filename_chars("meu video") == []

    def test_detects_each_invalid_char(self):
        for c in utils.INVALID_FILENAME_CHARS:
            assert c in utils.invalid_filename_chars(f"video{c}nome")

    def test_returns_ordered_unique_list(self):
        name = 'a*b*c?d?e'
        result = utils.invalid_filename_chars(name)
        assert result == ['*', '?']  # ordem de aparição, sem duplicatas

    def test_empty_string_returns_empty_list(self):
        assert utils.invalid_filename_chars("") == []

    def test_none_returns_empty_list(self):
        assert utils.invalid_filename_chars(None) == []


class TestIsValidFilename:

    def test_valid_name(self):
        assert utils.is_valid_filename("meu video legal") is True

    def test_invalid_due_to_char(self):
        assert utils.is_valid_filename('video:nome') is False

    def test_empty_string_invalid(self):
        assert utils.is_valid_filename("") is False

    def test_whitespace_only_invalid(self):
        assert utils.is_valid_filename("   ") is False

    def test_none_invalid(self):
        assert utils.is_valid_filename(None) is False


# ---------------------------------------------------------------------------
# safe_filename
# ---------------------------------------------------------------------------

class TestSafeFilename:

    def test_removes_invalid_chars(self):
        assert utils.safe_filename('a*b:c?d"e<f>g|h\\i/j') == "abcdefghij"

    def test_strips_whitespace(self):
        assert utils.safe_filename("   meu video   ") == "meu video"

    def test_empty_string_falls_back_to_video(self):
        assert utils.safe_filename("") == "video"

    def test_none_falls_back_to_video(self):
        assert utils.safe_filename(None) == "video"

    def test_only_invalid_chars_falls_back_to_video(self):
        assert utils.safe_filename('***???') == "video"

    def test_keeps_valid_unicode_characters(self):
        assert utils.safe_filename("vídeo em português") == "vídeo em português"


# ---------------------------------------------------------------------------
# expected_extension / expected_output_path
# ---------------------------------------------------------------------------

class TestExpectedExtension:

    @pytest.mark.parametrize("format_type, expected", [
        ("mp3", "mp3"),
        ("MP3", "mp3"),
        ("Mp3", "mp3"),
        ("mp4", "mp4"),
        ("MP4", "mp4"),
        ("", "mp4"),
        (None, "mp4"),
        ("wav", "mp4"),  # qualquer coisa diferente de mp3 cai em mp4
    ])
    def test_extension_mapping(self, format_type, expected):
        assert utils.expected_extension(format_type) == expected


class TestExpectedOutputPath:

    def test_builds_correct_path_mp4(self):
        result = utils.expected_output_path("/downloads", "Meu Video", "mp4")
        assert result == os.path.join("/downloads", "Meu Video.mp4")

    def test_builds_correct_path_mp3(self):
        result = utils.expected_output_path("/downloads", "Minha Musica", "mp3")
        assert result == os.path.join("/downloads", "Minha Musica.mp3")

    def test_sanitizes_title(self):
        result = utils.expected_output_path("/downloads", "vid:eo?", "mp4")
        assert result == os.path.join("/downloads", "video.mp4")


# ---------------------------------------------------------------------------
# file_conflict / resolve_unique_title
# ---------------------------------------------------------------------------

class TestFileConflict:

    def test_no_conflict_when_file_does_not_exist(self, tmp_path):
        assert utils.file_conflict(str(tmp_path), "video", "mp4") is False

    def test_conflict_when_file_exists(self, tmp_path):
        (tmp_path / "video.mp4").write_text("data")
        assert utils.file_conflict(str(tmp_path), "video", "mp4") is True

    def test_conflict_is_specific_to_extension(self, tmp_path):
        (tmp_path / "video.mp3").write_text("data")
        # mp4 não deve conflitar já que só existe o mp3
        assert utils.file_conflict(str(tmp_path), "video", "mp4") is False


class TestResolveUniqueTitle:

    def test_returns_base_name_when_no_conflict(self, tmp_path):
        result = utils.resolve_unique_title(str(tmp_path), "video", "mp4")
        assert result == "video"

    def test_returns_incremented_name_on_single_conflict(self, tmp_path):
        (tmp_path / "video.mp4").write_text("data")
        result = utils.resolve_unique_title(str(tmp_path), "video", "mp4")
        assert result == "video (1)"

    def test_skips_multiple_existing_conflicts(self, tmp_path):
        (tmp_path / "video.mp4").write_text("data")
        (tmp_path / "video (1).mp4").write_text("data")
        (tmp_path / "video (2).mp4").write_text("data")
        result = utils.resolve_unique_title(str(tmp_path), "video", "mp4")
        assert result == "video (3)"

    def test_sanitizes_title_before_resolving(self, tmp_path):
        result = utils.resolve_unique_title(str(tmp_path), "vid:eo?", "mp4")
        assert result == "video"


# ---------------------------------------------------------------------------
# get_user_data_dir
# ---------------------------------------------------------------------------

class TestGetUserDataDir:

    # src/ folder, same base resource_path()/get_ytdlp_path() use - the "src"
    # dir is two levels above utils.py (src/core/utils.py)
    _SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(utils.__file__)))

    def test_dev_mode_ignores_cwd(self, tmp_path, monkeypatch):
        # cwd must NOT affect the result - it used to (bug), now it's anchored
        # to the "src" folder regardless of where the process was launched from
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        monkeypatch.chdir(tmp_path)
        result = utils.get_user_data_dir()
        assert result == os.path.join(self._SRC_DIR, "data")
        assert os.path.isdir(result)

    def test_frozen_mode_uses_executable_dir(self, tmp_path, monkeypatch):
        fake_exe_dir = tmp_path / "app"
        fake_exe_dir.mkdir()
        fake_exe = fake_exe_dir / "app.exe"
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)
        result = utils.get_user_data_dir()
        assert result == os.path.join(str(fake_exe_dir), "data")
        assert os.path.isdir(result)

    def test_creates_directory_if_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        monkeypatch.chdir(tmp_path)
        utils.get_user_data_dir()
        assert os.path.isdir(os.path.join(self._SRC_DIR, "data"))

    def test_idempotent_when_directory_already_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        monkeypatch.chdir(tmp_path)
        first = utils.get_user_data_dir()
        second = utils.get_user_data_dir()
        assert first == second


# ---------------------------------------------------------------------------
# resource_path
# ---------------------------------------------------------------------------

class TestResourcePath:

    _SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(utils.__file__)))

    def test_uses_meipass_when_present(self, monkeypatch):
        monkeypatch.setattr(sys, "_MEIPASS", "/fake/meipass", raising=False)
        result = utils.resource_path("bin/tool.exe")
        assert result == os.path.join("/fake/meipass", "bin/tool.exe")

    def test_ignores_cwd_when_no_meipass(self, monkeypatch):
        # cwd must NOT affect the result - anchored to the "src" folder instead
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        result = utils.resource_path("bin/tool.exe")
        assert result == os.path.join(self._SRC_DIR, "bin/tool.exe")


# ---------------------------------------------------------------------------
# get_ytdlp_path
# ---------------------------------------------------------------------------

class TestGetYtdlpPath:

    def test_windows_returns_bundled_path(self, monkeypatch):
        monkeypatch.setattr(utils.sys, "platform", "win32")
        monkeypatch.setattr(sys, "_MEIPASS", "/fake/meipass", raising=False)
        result = utils.get_ytdlp_path()
        assert result == os.path.join("/fake/meipass", "bin/yt-dlp.exe")

    def test_linux_uses_bundled_binary_when_present_and_executable(self, monkeypatch):
        monkeypatch.setattr(utils.sys, "platform", "linux")
        monkeypatch.setattr(utils.os.path, "exists", lambda path: True)
        monkeypatch.setattr(utils.os, "access", lambda path, mode: True)
        monkeypatch.setattr(utils, "_ytdlp_binary_runs", lambda path: True)
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/yt-dlp")
        result = utils.get_ytdlp_path()
        assert result == os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(utils.__file__)), "..", "bin", "yt-dlp")
        )

    def test_linux_falls_back_to_which_when_bundled_binary_does_not_run(self, monkeypatch):
        # regression: bin/yt-dlp existing and marked executable is not enough -
        # it can be the wrong platform's binary (ex.: a Windows .exe copied in
        # by mistake), which raises OSError("Exec format error") on exec. In
        # that case get_ytdlp_path() must fall back to the system yt-dlp
        # instead of returning a binary that crashes every caller.
        monkeypatch.setattr(utils.sys, "platform", "linux")
        monkeypatch.setattr(utils.os.path, "exists", lambda path: True)
        monkeypatch.setattr(utils.os, "access", lambda path, mode: True)
        monkeypatch.setattr(utils, "_ytdlp_binary_runs", lambda path: False)
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/yt-dlp")
        assert utils.get_ytdlp_path() == "/usr/bin/yt-dlp"

    def test_linux_falls_back_to_which_when_bundled_missing(self, monkeypatch):
        monkeypatch.setattr(utils.sys, "platform", "linux")
        monkeypatch.setattr(utils.os.path, "exists", lambda path: False)
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/yt-dlp")
        assert utils.get_ytdlp_path() == "/usr/bin/yt-dlp"

    def test_linux_falls_back_to_which_when_bundled_not_executable(self, monkeypatch):
        monkeypatch.setattr(utils.sys, "platform", "linux")
        monkeypatch.setattr(utils.os.path, "exists", lambda path: True)
        monkeypatch.setattr(utils.os, "access", lambda path, mode: False)
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/yt-dlp")
        assert utils.get_ytdlp_path() == "/usr/bin/yt-dlp"

    def test_linux_raises_when_not_found(self, monkeypatch):
        monkeypatch.setattr(utils.sys, "platform", "linux")
        monkeypatch.setattr(utils.os.path, "exists", lambda path: False)
        monkeypatch.setattr(shutil, "which", lambda name: None)
        with pytest.raises(Exception, match="yt-dlp"):
            utils.get_ytdlp_path()


# ---------------------------------------------------------------------------
# get_ffmpeg_path
# ---------------------------------------------------------------------------

class TestGetFfmpegPath:

    def test_windows_returns_bundled_path(self, monkeypatch):
        monkeypatch.setattr(utils.sys, "platform", "win32")
        monkeypatch.setattr(sys, "_MEIPASS", "/fake/meipass", raising=False)
        result = utils.get_ffmpeg_path()
        assert result == os.path.join("/fake/meipass", "tools/ffmpeg/bin/")

    def test_linux_uses_which_when_found(self, monkeypatch):
        monkeypatch.setattr(utils.sys, "platform", "linux")
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ffmpeg")
        assert utils.get_ffmpeg_path() == "/usr/bin/ffmpeg"

    def test_linux_raises_when_not_found(self, monkeypatch):
        monkeypatch.setattr(utils.sys, "platform", "linux")
        monkeypatch.setattr(shutil, "which", lambda name: None)
        with pytest.raises(Exception, match="FFmpeg"):
            utils.get_ffmpeg_path()


# ---------------------------------------------------------------------------
# get_node_path
# ---------------------------------------------------------------------------

class TestGetNodePath:

    def test_linux_uses_which_when_found(self, monkeypatch):
        monkeypatch.setattr(utils.sys, "platform", "linux")
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/node")
        monkeypatch.setattr(utils, "_node_version_supported", lambda path: True)
        assert utils.get_node_path() == "/usr/bin/node"

    def test_linux_raises_when_not_found(self, monkeypatch):
        monkeypatch.setattr(utils.sys, "platform", "linux")
        monkeypatch.setattr(shutil, "which", lambda name: None)
        with pytest.raises(Exception, match="Node.js"):
            utils.get_node_path()

    def test_linux_raises_when_version_outdated(self, monkeypatch):
        monkeypatch.setattr(utils.sys, "platform", "linux")
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/node")
        monkeypatch.setattr(utils, "_node_version_supported", lambda path: False)
        with pytest.raises(Exception, match="desatualizado"):
            utils.get_node_path()

    def test_windows_currently_always_raises(self, monkeypatch):
        # NOTA: no branch win32 a função monta a lista `node_paths` mas nunca
        # a utiliza (não faz `return` nem checagem de existência), então o
        # fluxo cai direto no `raise Exception` final. Este teste documenta
        # o comportamento atual da implementação (provável bug).
        monkeypatch.setattr(utils.sys, "platform", "win32")
        with pytest.raises(Exception, match="Node.js"):
            utils.get_node_path()


# ---------------------------------------------------------------------------
# _node_version_supported
# ---------------------------------------------------------------------------

class TestNodeVersionSupported:

    def _make_fake_node(self, tmp_path, version_output):
        script = tmp_path / "fake_node"
        script.write_text(f"#!/bin/sh\necho '{version_output}'\n")
        script.chmod(0o755)
        return str(script)

    def test_supported_version(self, tmp_path):
        fake_node = self._make_fake_node(tmp_path, "v22.23.2")
        assert utils._node_version_supported(fake_node) is True

    def test_outdated_version(self, tmp_path):
        fake_node = self._make_fake_node(tmp_path, "v18.19.1")
        assert utils._node_version_supported(fake_node) is False

    def test_unparseable_output_defaults_to_true(self, tmp_path):
        # não bloqueia o usuário quando não conseguimos determinar a versão
        fake_node = self._make_fake_node(tmp_path, "not-a-version")
        assert utils._node_version_supported(fake_node) is True

    def test_nonexistent_path_defaults_to_true(self):
        assert utils._node_version_supported("/nonexistent/node") is True


# ---------------------------------------------------------------------------
# Cookies: get_cookies_path / cookies_exists / secure_cookies_file / save_cookies
# ---------------------------------------------------------------------------

class TestCookiesPath:
    # get_user_data_dir() is now anchored to the real "src" folder (not cwd),
    # so tests must monkeypatch it directly - otherwise they'd read/write the
    # developer's real data/cookies.txt.

    def test_get_cookies_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(utils, "get_user_data_dir", lambda: str(tmp_path / "data"))
        result = utils.get_cookies_path()
        assert result == os.path.join(str(tmp_path), "data", "cookies.txt")

    def test_cookies_exists_false_when_absent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(utils, "get_user_data_dir", lambda: str(tmp_path / "data"))
        assert utils.cookies_exists() is False

    def test_cookies_exists_true_when_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr(utils, "get_user_data_dir", lambda: str(tmp_path / "data"))
        path = utils.get_cookies_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"data")
        assert utils.cookies_exists() is True


class TestSecureCookiesFile:

    def test_noop_when_file_missing(self, tmp_path):
        # não deve lançar exceção mesmo que o arquivo não exista
        utils.secure_cookies_file(str(tmp_path / "nao_existe.txt"))

    def test_sets_owner_read_write_permissions(self, tmp_path):
        f = tmp_path / "cookies.txt"
        f.write_text("data")
        utils.secure_cookies_file(str(f))
        mode = stat.S_IMODE(os.stat(str(f)).st_mode)
        assert mode == (stat.S_IRUSR | stat.S_IWUSR)

    def test_falls_back_gracefully_when_chmod_fails(self, tmp_path, monkeypatch):
        f = tmp_path / "cookies.txt"
        f.write_text("data")

        def raise_error(*args, **kwargs):
            raise OSError("chmod not supported")

        monkeypatch.setattr(os, "chmod", raise_error)
        # não deve lançar exceção, mesmo com os.chmod sempre falhando
        utils.secure_cookies_file(str(f))


class TestSaveCookies:
    # same reasoning as TestCookiesPath - monkeypatch get_user_data_dir()
    # directly so these tests never touch the developer's real data/cookies.txt

    def test_creates_file_with_content(self, tmp_path, monkeypatch):
        monkeypatch.setattr(utils, "get_user_data_dir", lambda: str(tmp_path / "data"))
        utils.save_cookies(b"cookie-content")
        path = utils.get_cookies_path()
        assert os.path.exists(path)
        with open(path, "rb") as f:
            assert f.read() == b"cookie-content"

    def test_creates_parent_directory_if_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(utils, "get_user_data_dir", lambda: str(tmp_path / "data"))
        assert not (tmp_path / "data").exists()
        utils.save_cookies(b"abc")
        assert (tmp_path / "data").is_dir()

    def test_applies_secure_permissions(self, tmp_path, monkeypatch):
        monkeypatch.setattr(utils, "get_user_data_dir", lambda: str(tmp_path / "data"))
        utils.save_cookies(b"abc")
        path = utils.get_cookies_path()
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == (stat.S_IRUSR | stat.S_IWUSR)

    def test_overwrites_existing_cookies_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(utils, "get_user_data_dir", lambda: str(tmp_path / "data"))
        utils.save_cookies(b"old-content")
        utils.save_cookies(b"new-content")
        with open(utils.get_cookies_path(), "rb") as f:
            assert f.read() == b"new-content"


# ---------------------------------------------------------------------------
# get_ffmpeg_exe
# ---------------------------------------------------------------------------

class TestGetFfmpegExe:

    def test_returns_full_path_when_exe_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(utils.sys, "platform", "linux")
        fake_bin = tmp_path
        ffmpeg_file = fake_bin / "ffmpeg"
        ffmpeg_file.write_text("")
        monkeypatch.setattr(utils, "get_ffmpeg_path", lambda: str(fake_bin))
        result = utils.get_ffmpeg_exe()
        assert result == str(ffmpeg_file)

    def test_falls_back_to_bare_exe_name_when_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(utils.sys, "platform", "linux")
        monkeypatch.setattr(utils, "get_ffmpeg_path", lambda: str(tmp_path))
        result = utils.get_ffmpeg_exe()
        assert result == "ffmpeg"

    def test_windows_exe_suffix(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(utils, "get_ffmpeg_path", lambda: str(tmp_path))
        result = utils.get_ffmpeg_exe()
        assert result == "ffmpeg.exe"

    def test_propagates_exception_when_ffmpeg_path_fails(self, monkeypatch):
        def raise_error():
            raise Exception("FFmpeg não encontrado.")
        monkeypatch.setattr(utils, "get_ffmpeg_path", raise_error)
        with pytest.raises(Exception, match="FFmpeg"):
            utils.get_ffmpeg_exe()