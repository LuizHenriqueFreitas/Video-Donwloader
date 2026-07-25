# Translate and revise

"""
Testes para core/video_info.py

Cobrem:
    - VideoInfo.extract() (montagem do comando yt-dlp, timeout, erros, parsing)
    - VideoInfo._format_response() (filtragem, ordenação e deduplicação de formatos)
    - VideoInfo._parse_error() (mapeamento de mensagens de erro)
    - VideoInfo.extract_playlist() (montagem do comando, parsing de entradas)
    - pick_preview_url() (seleção do melhor formato progressivo para preview)
"""

import json
import subprocess
import sys

import pytest

from core import video_info as vi
from core.video_info import VideoInfo, pick_preview_url


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

class FakeCompletedProcess:
    """Substitui subprocess.CompletedProcess para os testes."""
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def video(monkeypatch):
    """Instância de VideoInfo com todas as dependências externas mockadas
    com valores 'felizes' por padrão. Cada teste sobrescreve o que precisar."""
    monkeypatch.setattr(vi, "get_ytdlp_path", lambda: "/fake/yt-dlp")
    monkeypatch.setattr(vi, "get_node_path", lambda: "/fake/node")
    monkeypatch.setattr(vi, "get_cookies_path", lambda: "/fake/data/cookies.txt")
    monkeypatch.setattr(vi, "cookies_exists", lambda: False)
    monkeypatch.setattr(vi, "is_youtube", lambda url: "youtube.com" in url)
    monkeypatch.setattr(vi.sys, "platform", "linux")
    return VideoInfo()


# ---------------------------------------------------------------------------
# VideoInfo.extract
# ---------------------------------------------------------------------------

class TestExtract:

    def test_raises_on_empty_url(self, video):
        with pytest.raises(ValueError, match="URL vazia"):
            video.extract("")

    def test_raises_on_none_url(self, video):
        with pytest.raises(ValueError, match="URL vazia"):
            video.extract(None)

    def test_youtube_command_includes_user_agent_and_extractor_args(self, video, monkeypatch):
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            return FakeCompletedProcess(returncode=0, stdout=json.dumps({"title": "t"}))

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        video.extract("https://www.youtube.com/watch?v=abc")

        cmd = captured["command"]
        assert "--user-agent" in cmd
        assert "Mozilla/5.0" in cmd
        assert "--extractor-args" in cmd
        assert "youtube:player_client=web_safari,android_vr" in cmd

    def test_non_youtube_command_excludes_youtube_specific_args(self, video, monkeypatch):
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            return FakeCompletedProcess(returncode=0, stdout=json.dumps({"title": "t"}))

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        video.extract("https://www.tiktok.com/@user/video/1")

        cmd = captured["command"]
        assert "--user-agent" not in cmd
        assert "--extractor-args" not in cmd

    def test_command_always_includes_base_flags(self, video, monkeypatch):
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            return FakeCompletedProcess(returncode=0, stdout=json.dumps({"title": "t"}))

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        url = "https://www.tiktok.com/@user/video/1"
        video.extract(url)

        cmd = captured["command"]
        assert cmd[0] == "/fake/yt-dlp"
        assert "--js-runtime" in cmd
        assert "/fake/node" in cmd
        assert "--no-playlist" in cmd
        assert "--skip-download" in cmd
        assert "-j" in cmd
        assert cmd[-1] == url

    def test_includes_cookies_when_present(self, video, monkeypatch):
        monkeypatch.setattr(vi, "cookies_exists", lambda: True)
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            return FakeCompletedProcess(returncode=0, stdout=json.dumps({"title": "t"}))

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        video.extract("https://www.tiktok.com/@user/video/1")

        cmd = captured["command"]
        assert "--cookies" in cmd
        assert "/fake/data/cookies.txt" in cmd

    def test_excludes_cookies_when_absent(self, video, monkeypatch):
        monkeypatch.setattr(vi, "cookies_exists", lambda: False)
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            return FakeCompletedProcess(returncode=0, stdout=json.dumps({"title": "t"}))

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        video.extract("https://www.tiktok.com/@user/video/1")

        assert "--cookies" not in captured["command"]

    def test_windows_sets_creationflags(self, video, monkeypatch):
        monkeypatch.setattr(vi.sys, "platform", "win32")
        monkeypatch.setattr(vi.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
        captured = {}

        def fake_run(command, **kwargs):
            captured["kwargs"] = kwargs
            return FakeCompletedProcess(returncode=0, stdout=json.dumps({"title": "t"}))

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        video.extract("https://www.tiktok.com/@user/video/1")

        assert captured["kwargs"]["creationflags"] == 0x08000000

    def test_linux_creationflags_is_zero(self, video, monkeypatch):
        captured = {}

        def fake_run(command, **kwargs):
            captured["kwargs"] = kwargs
            return FakeCompletedProcess(returncode=0, stdout=json.dumps({"title": "t"}))

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        video.extract("https://www.tiktok.com/@user/video/1")

        assert captured["kwargs"]["creationflags"] == 0

    def test_timeout_expired_raises_generic_exception(self, video, monkeypatch):
        def fake_run(command, **kwargs):
            raise subprocess.TimeoutExpired(cmd=command, timeout=90)

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        with pytest.raises(Exception, match="Erro ao extrair"):
            video.extract("https://www.tiktok.com/@user/video/1")

    def test_nonzero_returncode_raises_parsed_error(self, video, monkeypatch):
        def fake_run(command, **kwargs):
            return FakeCompletedProcess(returncode=1, stderr="Video is private")

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        with pytest.raises(Exception, match="privado"):
            video.extract("https://www.tiktok.com/@user/video/1")

    def test_invalid_json_stdout_raises_exception(self, video, monkeypatch):
        def fake_run(command, **kwargs):
            return FakeCompletedProcess(returncode=0, stdout="not-json{{{")

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        with pytest.raises(Exception, match="Falha ao ler a resposta"):
            video.extract("https://www.tiktok.com/@user/video/1")

    def test_successful_extract_returns_formatted_response(self, video, monkeypatch):
        raw_info = {
            "title": "Meu Video",
            "thumbnail": "http://thumb.jpg",
            "duration": 120,
            "formats": [],
        }

        def fake_run(command, **kwargs):
            return FakeCompletedProcess(returncode=0, stdout=json.dumps(raw_info))

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        result = video.extract("https://www.tiktok.com/@user/video/1")

        assert result["title"] == "Meu Video"
        assert result["thumbnail"] == "http://thumb.jpg"
        assert result["duration"] == 120
        assert result["formats"] == []
        assert result["audio_formats"] == []
        assert result["raw_formats"] == []


# ---------------------------------------------------------------------------
# VideoInfo._format_response
# ---------------------------------------------------------------------------

class TestFormatResponse:

    def test_default_title_when_missing(self):
        result = VideoInfo()._format_response({})
        assert result["title"] == "Sem título"
        assert result["thumbnail"] is None
        assert result["duration"] is None
        assert result["formats"] == []
        assert result["audio_formats"] == []

    def test_separates_video_and_audio_formats(self):
        info = {
            "formats": [
                {"vcodec": "avc1", "acodec": "none", "height": 720, "ext": "mp4", "format_id": "v1"},
                {"vcodec": "none", "acodec": "mp4a", "height": None, "ext": "m4a", "abr": 128, "format_id": "a1"},
                {"vcodec": "none", "acodec": "none", "height": None, "ext": "mhtml", "format_id": "storyboard"},
            ]
        }
        result = VideoInfo()._format_response(info)
        assert len(result["formats"]) == 1
        assert result["formats"][0]["format_id"] == "v1"
        assert len(result["audio_formats"]) == 1
        assert result["audio_formats"][0]["format_id"] == "a1"

    def test_video_formats_require_height(self):
        # vcodec presente mas sem height -> não deve entrar na lista de vídeos
        info = {
            "formats": [
                {"vcodec": "avc1", "acodec": "none", "height": None, "ext": "mp4", "format_id": "v1"},
            ]
        }
        result = VideoInfo()._format_response(info)
        assert result["formats"] == []

    def test_sorts_video_formats_by_height_ascending(self):
        info = {
            "formats": [
                {"vcodec": "avc1", "acodec": "none", "height": 1080, "ext": "mp4", "format_id": "v1080"},
                {"vcodec": "avc1", "acodec": "none", "height": 360, "ext": "mp4", "format_id": "v360"},
                {"vcodec": "avc1", "acodec": "none", "height": 720, "ext": "mp4", "format_id": "v720"},
            ]
        }
        result = VideoInfo()._format_response(info)
        heights = [f["height"] for f in result["formats"]]
        assert heights == [360, 720, 1080]

    def test_sorts_audio_formats_by_abr_ascending(self):
        info = {
            "formats": [
                {"vcodec": "none", "acodec": "mp4a", "height": None, "ext": "m4a", "abr": 192, "format_id": "a192"},
                {"vcodec": "none", "acodec": "mp4a", "height": None, "ext": "m4a", "abr": 64, "format_id": "a64"},
                {"vcodec": "none", "acodec": "mp4a", "height": None, "ext": "m4a", "abr": 128, "format_id": "a128"},
            ]
        }
        result = VideoInfo()._format_response(info)
        abrs = [f["abr"] for f in result["audio_formats"]]
        assert abrs == [64, 128, 192]

    def test_deduplicates_video_formats_by_height_and_ext(self):
        # dois formatos 720p/mp4: o último (maior filesize) deve prevalecer
        # já que o algoritmo itera de trás pra frente e mantém o primeiro visto
        info = {
            "formats": [
                {"vcodec": "avc1", "acodec": "none", "height": 720, "ext": "mp4",
                 "format_id": "v720_a", "filesize": 1000},
                {"vcodec": "avc1", "acodec": "none", "height": 720, "ext": "mp4",
                 "format_id": "v720_b", "filesize": 2000},
            ]
        }
        result = VideoInfo()._format_response(info)
        assert len(result["formats"]) == 1
        # como a lista é ordenada (estável) por height antes da dedup, e ambos têm
        # a mesma altura, a ordem original é preservada; a dedup mantém o ÚLTIMO
        # elemento da lista ordenada (percorrida de trás para frente).
        assert result["formats"][0]["format_id"] == "v720_b"

    def test_deduplicates_audio_formats_by_ext_and_abr(self):
        info = {
            "formats": [
                {"vcodec": "none", "acodec": "mp4a", "height": None, "ext": "m4a",
                 "abr": 128, "format_id": "a1", "filesize": 500},
                {"vcodec": "none", "acodec": "mp4a", "height": None, "ext": "m4a",
                 "abr": 128, "format_id": "a2", "filesize": 600},
            ]
        }
        result = VideoInfo()._format_response(info)
        assert len(result["audio_formats"]) == 1

    def test_uses_filesize_approx_when_filesize_missing(self):
        info = {
            "formats": [
                {"vcodec": "avc1", "acodec": "none", "height": 480, "ext": "mp4",
                 "format_id": "v1", "filesize_approx": 12345},
            ]
        }
        result = VideoInfo()._format_response(info)
        assert result["formats"][0]["filesize"] == 12345

    def test_filesize_none_when_both_missing(self):
        info = {
            "formats": [
                {"vcodec": "avc1", "acodec": "none", "height": 480, "ext": "mp4", "format_id": "v1"},
            ]
        }
        result = VideoInfo()._format_response(info)
        assert result["formats"][0]["filesize"] is None

    def test_raw_formats_preserved_untouched(self):
        formats = [
            {"vcodec": "avc1", "acodec": "none", "height": 480, "ext": "mp4", "format_id": "v1"},
        ]
        info = {"formats": formats}
        result = VideoInfo()._format_response(info)
        assert result["raw_formats"] == formats

    def test_missing_formats_key_defaults_to_empty_list(self):
        result = VideoInfo()._format_response({"title": "x"})
        assert result["raw_formats"] == []


# ---------------------------------------------------------------------------
# VideoInfo._parse_error
# ---------------------------------------------------------------------------

class TestParseError:

    @pytest.mark.parametrize("stderr, expected_substring", [
        ("ERROR: Confirm you're not a bot", "Bloqueado pelo youtube"),
        ("some CAPTCHA required", "Bloqueado pelo youtube"),
        ("HTTP Error 429: Too Many Requests", "Muitas tentativas"),
        ("invalid cookies file provided", "Error com cookies"),
        ("Unsupported URL: foo", "Link não suportado"),
        ("This video is Private", "Video privado"),
        ("ERROR: Sign in to confirm your age", "Login necessário"),
    ])
    def test_known_error_patterns(self, stderr, expected_substring):
        result = VideoInfo()._parse_error(stderr)
        assert expected_substring in result

    def test_unknown_error_returns_original_stderr(self):
        stderr = "some completely unknown failure occurred"
        assert VideoInfo()._parse_error(stderr) == stderr

    def test_matching_is_case_insensitive(self):
        result = VideoInfo()._parse_error("VIDEO IS PRIVATE")
        assert "privado" in result

    def test_empty_stderr_returns_empty_string(self):
        assert VideoInfo()._parse_error("") == ""


# ---------------------------------------------------------------------------
# VideoInfo.extract_playlist
# ---------------------------------------------------------------------------

class TestExtractPlaylist:

    def test_raises_on_empty_url(self, video):
        with pytest.raises(ValueError, match="null URL"):
            video.extract_playlist("")

    def test_command_includes_flat_playlist_flags(self, video, monkeypatch):
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            return FakeCompletedProcess(
                returncode=0,
                stdout=json.dumps({"_type": "playlist", "title": "PL", "entries": []}),
            )

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        video.extract_playlist("https://www.youtube.com/playlist?list=PL123")

        cmd = captured["command"]
        assert "--flat-playlist" in cmd
        assert "--no-warnings" in cmd
        assert "-J" in cmd

    def test_includes_cookies_when_present(self, video, monkeypatch):
        monkeypatch.setattr(vi, "cookies_exists", lambda: True)
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            return FakeCompletedProcess(
                returncode=0,
                stdout=json.dumps({"_type": "playlist", "title": "PL", "entries": []}),
            )

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        video.extract_playlist("https://www.youtube.com/playlist?list=PL123")

        assert "--cookies" in captured["command"]

    def test_nonzero_returncode_raises_parsed_error(self, video, monkeypatch):
        def fake_run(command, **kwargs):
            return FakeCompletedProcess(returncode=1, stderr="captcha required")

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        with pytest.raises(Exception, match="Bloqueado"):
            video.extract_playlist("https://www.youtube.com/playlist?list=PL123")

    def test_invalid_json_raises_exception(self, video, monkeypatch):
        def fake_run(command, **kwargs):
            return FakeCompletedProcess(returncode=0, stdout="not json")

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        with pytest.raises(Exception, match="Falha ao ler os dados da playlist"):
            video.extract_playlist("https://www.youtube.com/playlist?list=PL123")

    def test_returns_none_when_not_a_playlist_type(self, video, monkeypatch):
        def fake_run(command, **kwargs):
            return FakeCompletedProcess(
                returncode=0,
                stdout=json.dumps({"_type": "video", "title": "single"}),
            )

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        result = video.extract_playlist("https://www.youtube.com/watch?v=abc")
        assert result is None

    def test_returns_none_when_entries_empty(self, video, monkeypatch):
        def fake_run(command, **kwargs):
            return FakeCompletedProcess(
                returncode=0,
                stdout=json.dumps({"_type": "playlist", "title": "PL", "entries": []}),
            )

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        result = video.extract_playlist("https://www.youtube.com/playlist?list=PL123")
        assert result is None

    def test_parses_entries_with_full_data(self, video, monkeypatch):
        entries = [
            {
                "url": "https://www.youtube.com/watch?v=xyz",
                "title": "Video 1",
                "id": "xyz",
                "duration": 100,
                "thumbnail": "https://img.example.com/xyz.jpg",
            }
        ]

        def fake_run(command, **kwargs):
            return FakeCompletedProcess(
                returncode=0,
                stdout=json.dumps({"_type": "playlist", "title": "My Playlist", "entries": entries}),
            )

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        result = video.extract_playlist("https://www.youtube.com/playlist?list=PL123")

        assert result["title"] == "My Playlist"
        assert len(result["entries"]) == 1
        entry = result["entries"][0]
        assert entry["url"] == "https://www.youtube.com/watch?v=xyz"
        assert entry["title"] == "Video 1"
        assert entry["id"] == "xyz"
        assert entry["duration"] == 100
        assert entry["thumbnail"] == "https://img.example.com/xyz.jpg"

    def test_skips_falsy_entries(self, video, monkeypatch):
        entries = [None, {}, {"id": "abc123", "title": "valid"}]

        def fake_run(command, **kwargs):
            return FakeCompletedProcess(
                returncode=0,
                stdout=json.dumps({"_type": "playlist", "title": "PL", "entries": entries}),
            )

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        result = video.extract_playlist("https://www.youtube.com/playlist?list=PL123")
        # None é pulado; {} ainda é um dict truthy? {} é falsy em Python!
        # então tanto None quanto {} são ignorados, sobrando só o terceiro
        assert len(result["entries"]) == 1
        assert result["entries"][0]["id"] == "abc123"

    def test_builds_youtube_url_from_id_when_not_http(self, video, monkeypatch):
        entries = [{"id": "abc123", "title": "Video"}]

        def fake_run(command, **kwargs):
            return FakeCompletedProcess(
                returncode=0,
                stdout=json.dumps({"_type": "playlist", "title": "PL", "entries": entries}),
            )

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        result = video.extract_playlist("https://www.youtube.com/playlist?list=PL123")
        assert result["entries"][0]["url"] == "https://www.youtube.com/watch?v=abc123"

    def test_non_http_id_kept_as_is_for_non_youtube(self, video, monkeypatch):
        monkeypatch.setattr(vi, "is_youtube", lambda url: False)
        entries = [{"id": "abc123", "title": "Video"}]

        def fake_run(command, **kwargs):
            return FakeCompletedProcess(
                returncode=0,
                stdout=json.dumps({"_type": "playlist", "title": "PL", "entries": entries}),
            )

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        result = video.extract_playlist("https://vimeo.com/showcase/123")
        # não é youtube, então a URL não é reconstruída, permanece o id puro
        assert result["entries"][0]["url"] == "abc123"

    def test_prefers_webpage_url_over_id(self, video, monkeypatch):
        entries = [{"id": "abc123", "webpage_url": "https://www.youtube.com/watch?v=abc123", "title": "V"}]

        def fake_run(command, **kwargs):
            return FakeCompletedProcess(
                returncode=0,
                stdout=json.dumps({"_type": "playlist", "title": "PL", "entries": entries}),
            )

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        result = video.extract_playlist("https://www.youtube.com/playlist?list=PL123")
        assert result["entries"][0]["url"] == "https://www.youtube.com/watch?v=abc123"

    def test_builds_thumbnail_when_missing_for_youtube(self, video, monkeypatch):
        entries = [{"id": "abc123", "title": "V"}]

        def fake_run(command, **kwargs):
            return FakeCompletedProcess(
                returncode=0,
                stdout=json.dumps({"_type": "playlist", "title": "PL", "entries": entries}),
            )

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        result = video.extract_playlist("https://www.youtube.com/playlist?list=PL123")
        assert result["entries"][0]["thumbnail"] == "https://img.youtube.com/vi/abc123/mqdefault.jpg"

    def test_no_thumbnail_built_for_non_youtube(self, video, monkeypatch):
        monkeypatch.setattr(vi, "is_youtube", lambda url: False)
        entries = [{"id": "abc123", "webpage_url": "https://vimeo.com/abc123", "title": "V"}]

        def fake_run(command, **kwargs):
            return FakeCompletedProcess(
                returncode=0,
                stdout=json.dumps({"_type": "playlist", "title": "PL", "entries": entries}),
            )

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        result = video.extract_playlist("https://vimeo.com/showcase/123")
        assert result["entries"][0]["thumbnail"] is None

    def test_default_title_when_missing(self, video, monkeypatch):
        entries = [{"id": "abc123", "title": "V"}]

        def fake_run(command, **kwargs):
            return FakeCompletedProcess(
                returncode=0,
                stdout=json.dumps({"_type": "playlist", "entries": entries}),
            )

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        result = video.extract_playlist("https://www.youtube.com/playlist?list=PL123")
        assert result["title"] == "Playlist"

    def test_default_entry_title_when_missing(self, video, monkeypatch):
        entries = [{"id": "abc123"}]

        def fake_run(command, **kwargs):
            return FakeCompletedProcess(
                returncode=0,
                stdout=json.dumps({"_type": "playlist", "title": "PL", "entries": entries}),
            )

        monkeypatch.setattr(vi.subprocess, "run", fake_run)
        result = video.extract_playlist("https://www.youtube.com/playlist?list=PL123")
        assert result["entries"][0]["title"] == "(sem título)"


# ---------------------------------------------------------------------------
# pick_preview_url
# ---------------------------------------------------------------------------

class TestPickPreviewUrl:

    def test_none_info_returns_none(self):
        assert pick_preview_url(None) is None

    def test_empty_dict_returns_none(self):
        assert pick_preview_url({}) is None

    def test_no_formats_returns_none(self):
        assert pick_preview_url({"raw_formats": [], "formats": []}) is None

    def test_filters_out_formats_without_video_codec(self):
        info = {"raw_formats": [
            {"vcodec": "none", "acodec": "mp4a", "url": "http://a", "ext": "mp4", "height": 360},
        ]}
        assert pick_preview_url(info) is None

    def test_filters_out_formats_without_audio_codec(self):
        info = {"raw_formats": [
            {"vcodec": "avc1", "acodec": "none", "url": "http://a", "ext": "mp4", "height": 360},
        ]}
        assert pick_preview_url(info) is None

    def test_filters_out_formats_without_url(self):
        info = {"raw_formats": [
            {"vcodec": "avc1", "acodec": "mp4a", "url": None, "ext": "mp4", "height": 360},
        ]}
        assert pick_preview_url(info) is None

    def test_ignores_non_dict_entries(self):
        info = {"raw_formats": [
            "not-a-dict",
            123,
            None,
            {"vcodec": "avc1", "acodec": "mp4a", "url": "http://good", "ext": "mp4",
             "height": 360, "protocol": "https"},
        ]}
        assert pick_preview_url(info) == "http://good"

    def test_prefers_raw_formats_over_formats(self):
        info = {
            "raw_formats": [
                {"vcodec": "avc1", "acodec": "mp4a", "url": "http://raw", "ext": "mp4",
                 "height": 360, "protocol": "https"},
            ],
            "formats": [
                {"vcodec": "avc1", "acodec": "mp4a", "url": "http://formats", "ext": "mp4",
                 "height": 360, "protocol": "https"},
            ],
        }
        assert pick_preview_url(info) == "http://raw"

    def test_falls_back_to_formats_when_raw_formats_missing(self):
        info = {
            "formats": [
                {"vcodec": "avc1", "acodec": "mp4a", "url": "http://formats", "ext": "mp4",
                 "height": 360, "protocol": "https"},
            ],
        }
        assert pick_preview_url(info) == "http://formats"

    def test_prefers_non_hls_over_hls(self):
        info = {"raw_formats": [
            {"vcodec": "avc1", "acodec": "mp4a", "url": "http://hls", "ext": "mp4",
             "height": 360, "protocol": "m3u8_native"},
            {"vcodec": "avc1", "acodec": "mp4a", "url": "http://https_stream", "ext": "mp4",
             "height": 360, "protocol": "https"},
        ]}
        assert pick_preview_url(info) == "http://https_stream"

    def test_prefers_mp4_over_other_ext_when_non_hls(self):
        info = {"raw_formats": [
            {"vcodec": "avc1", "acodec": "mp4a", "url": "http://webm", "ext": "webm",
             "height": 360, "protocol": "https"},
            {"vcodec": "avc1", "acodec": "mp4a", "url": "http://mp4", "ext": "mp4",
             "height": 360, "protocol": "https"},
        ]}
        assert pick_preview_url(info) == "http://mp4"

    def test_prefers_smaller_height_among_ties(self):
        info = {"raw_formats": [
            {"vcodec": "avc1", "acodec": "mp4a", "url": "http://big", "ext": "mp4",
             "height": 1080, "protocol": "https"},
            {"vcodec": "avc1", "acodec": "mp4a", "url": "http://small", "ext": "mp4",
             "height": 240, "protocol": "https"},
        ]}
        assert pick_preview_url(info) == "http://small"

    def test_missing_height_treated_as_large_and_deprioritized(self):
        info = {"raw_formats": [
            {"vcodec": "avc1", "acodec": "mp4a", "url": "http://no_height", "ext": "mp4",
             "protocol": "https"},  # sem height -> tratado como 9999
            {"vcodec": "avc1", "acodec": "mp4a", "url": "http://has_height", "ext": "mp4",
             "height": 480, "protocol": "https"},
        ]}
        assert pick_preview_url(info) == "http://has_height"

    def test_missing_protocol_treated_as_non_hls(self):
        info = {"raw_formats": [
            {"vcodec": "avc1", "acodec": "mp4a", "url": "http://no_protocol", "ext": "mp4",
             "height": 360},
        ]}
        assert pick_preview_url(info) == "http://no_protocol"