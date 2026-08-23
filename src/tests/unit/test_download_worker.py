# Translate and revise

"""
Testes para ui/workers/download_worker.py (DownloadWorker)

Cobrem:
    - _build_download_command() (MP3/MP4, clip, cookies, node, youtube args, overwrite)
    - _run_ytdlp_process() (parsing de progresso, merge, cancelamento, sucesso/erro)
    - _run_ffmpeg() (sucesso, cancelamento, exceção na criação do processo)
    - _run_clip_strategy() (fluxo completo de download+corte, fallback, conflitos de nome)
    - run_download() (orquestração: limpeza inicial, clip vs. normal, sinais emitidos)
    - cancel() / _kill_process_tree() (Windows vs Linux, fallback de kill)
    - _find_downloaded_file() (seleção do arquivo mais recente, exclusões, exceções)

Todas as dependências externas (subprocess.Popen/run, core.utils.*) são
mockadas via monkeypatch; nenhum processo real é executado.
"""

import os
import subprocess
import sys

import pytest

from ui.workers import download_worker as dw
from ui.workers.download_worker import DownloadWorker


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

class FakeItem:
    """Duplo de teste para models/download_item.py."""
    def __init__(self, **kwargs):
        self.title = kwargs.get("title", "My Video")
        self.output_path = kwargs.get("output_path", "/tmp/downloads")
        self.url = kwargs.get("url", "https://example.com/video")
        self.format_type = kwargs.get("format_type", "MP4")
        self.quality_id = kwargs.get("quality_id", None)
        self.clip_start = kwargs.get("clip_start", None)
        self.clip_end = kwargs.get("clip_end", None)
        self.overwrite = kwargs.get("overwrite", False)
        self.status = kwargs.get("status", "queued")
        self.file_path = kwargs.get("file_path", None)


class FakeProcess:
    """Duplo de teste para subprocess.Popen."""
    def __init__(self, stdout_lines=None, stderr_lines=None, returncode=0, pid=4242,
                 wait_side_effect=None, kill_side_effect=None):
        self.stdout = iter(stdout_lines or [])
        self.stderr = iter(stderr_lines or [])
        self.returncode = returncode
        self.pid = pid
        self.killed = False
        self._wait_side_effect = wait_side_effect
        self._kill_side_effect = kill_side_effect

    def wait(self, timeout=None):
        if self._wait_side_effect:
            self._wait_side_effect()
        return self.returncode

    def kill(self):
        self.killed = True
        if self._kill_side_effect:
            self._kill_side_effect()


@pytest.fixture
def patched_utils(monkeypatch, tmp_path):
    """Mocka todas as funções de core.utils importadas em download_worker."""
    node_file = tmp_path / "node_bin"
    node_file.write_text("")

    monkeypatch.setattr(dw, "get_ffmpeg_path", lambda: "/fake/ffmpeg/bin")
    monkeypatch.setattr(dw, "get_ffmpeg_exe", lambda: "/fake/ffmpeg/bin/ffmpeg")
    monkeypatch.setattr(dw, "get_ytdlp_path", lambda: "/fake/yt-dlp")
    monkeypatch.setattr(dw, "get_node_path", lambda: str(node_file))
    monkeypatch.setattr(dw, "get_cookies_path", lambda: "/fake/data/cookies.txt")
    monkeypatch.setattr(dw, "cookies_exists", lambda: False)
    monkeypatch.setattr(dw, "is_youtube", lambda url: "youtube.com" in url)
    monkeypatch.setattr(dw.sys, "platform", "linux")
    return {"node_file": str(node_file)}


def make_worker(item=None, **item_kwargs):
    item = item or FakeItem(**item_kwargs)
    return DownloadWorker(item)


def connect_capture(signal):
    captured = []
    signal.connect(lambda *args: captured.append(args if len(args) > 1 else (args[0] if args else None)))
    return captured


# ---------------------------------------------------------------------------
# _build_download_command
# ---------------------------------------------------------------------------

class TestBuildDownloadCommand:

    def test_mp3_full_download_command(self, patched_utils):
        worker = make_worker(format_type="MP3", url="https://vimeo.com/1", title="Song")
        cmd = worker._build_download_command()
        assert cmd[0] == "/fake/yt-dlp"
        assert cmd[1] == "https://vimeo.com/1"
        assert "-f" in cmd and "bestaudio" in cmd
        assert "-x" in cmd
        assert "--audio-format" in cmd and "mp3" in cmd
        assert "--audio-quality" in cmd and "192K" in cmd
        assert "--no-keep-video" not in cmd

    def test_mp3_clip_download_command(self, patched_utils):
        worker = make_worker(format_type="MP3", url="https://vimeo.com/1", title="Song")
        cmd = worker._build_download_command(for_clip=True)
        assert "--no-keep-video" in cmd
        assert "-x" not in cmd
        assert "--audio-format" not in cmd

    def test_mp4_auto_quality(self, patched_utils):
        worker = make_worker(format_type="MP4", url="https://vimeo.com/1", quality_id=None)
        cmd = worker._build_download_command()
        idx = cmd.index("-f")
        assert cmd[idx + 1] == "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

    def test_mp4_manual_quality_id(self, patched_utils):
        worker = make_worker(format_type="MP4", url="https://vimeo.com/1",
                              quality_id="137+140")
        cmd = worker._build_download_command()
        idx = cmd.index("-f")
        assert cmd[idx + 1] == "137+140"

    def test_mp4_quality_id_without_plus_uses_auto(self, patched_utils):
        # quality_id sem "+" não é considerado seleção manual válida
        worker = make_worker(format_type="MP4", url="https://vimeo.com/1", quality_id="137")
        cmd = worker._build_download_command()
        idx = cmd.index("-f")
        assert cmd[idx + 1] == "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

    def test_mp4_includes_merge_flags(self, patched_utils):
        worker = make_worker(format_type="MP4", url="https://vimeo.com/1")
        cmd = worker._build_download_command()
        assert "--merge-output-format" in cmd
        assert "mp4" in cmd
        assert "--no-mtime" in cmd
        assert "--no-continue" in cmd

    def test_mp4_youtube_url_includes_client_settings(self, patched_utils):
        worker = make_worker(format_type="MP4", url="https://www.youtube.com/watch?v=abc")
        cmd = worker._build_download_command()
        assert "--extractor-args" in cmd

    def test_mp4_non_youtube_excludes_client_settings(self, patched_utils):
        worker = make_worker(format_type="MP4", url="https://vimeo.com/1")
        cmd = worker._build_download_command()
        assert "--extractor-args" not in cmd

    def test_mp3_youtube_url_includes_client_settings(self, patched_utils):
        # sem isso o yt-dlp recebe "HTTP Error 403: Forbidden" do youtube em downloads de audio
        worker = make_worker(format_type="MP3", url="https://www.youtube.com/watch?v=abc")
        cmd = worker._build_download_command()
        assert "--extractor-args" in cmd

    def test_mp3_non_youtube_excludes_client_settings(self, patched_utils):
        worker = make_worker(format_type="MP3", url="https://vimeo.com/1")
        cmd = worker._build_download_command()
        assert "--extractor-args" not in cmd

    def test_output_template_uses_safe_title(self, patched_utils):
        worker = make_worker(title='vid:eo?"name', output_path="/tmp/out")
        cmd = worker._build_download_command()
        idx = cmd.index("-o")
        assert cmd[idx + 1] == os.path.join("/tmp/out", "videoname.%(ext)s")

    def test_output_override_used_verbatim(self, patched_utils):
        worker = make_worker(title="video")
        cmd = worker._build_download_command(output_override="/tmp/custom.%(ext)s")
        idx = cmd.index("-o")
        assert cmd[idx + 1] == "/tmp/custom.%(ext)s"

    def test_includes_ffmpeg_location(self, patched_utils):
        worker = make_worker()
        cmd = worker._build_download_command()
        idx = cmd.index("--ffmpeg-location")
        assert cmd[idx + 1] == "/fake/ffmpeg/bin"

    def test_includes_cookies_when_present(self, patched_utils, monkeypatch):
        monkeypatch.setattr(dw, "cookies_exists", lambda: True)
        worker = make_worker()
        cmd = worker._build_download_command()
        assert "--cookies" in cmd
        assert "/fake/data/cookies.txt" in cmd

    def test_excludes_cookies_when_absent(self, patched_utils):
        worker = make_worker()
        cmd = worker._build_download_command()
        assert "--cookies" not in cmd

    def test_node_path_exists_uses_node_prefix(self, patched_utils):
        worker = make_worker()
        cmd = worker._build_download_command()
        idx = cmd.index("--js-runtimes")
        assert cmd[idx + 1] == f"node:{patched_utils['node_file']}"

    def test_node_path_missing_falls_back_to_bare_node(self, patched_utils, monkeypatch):
        monkeypatch.setattr(dw, "get_node_path", lambda: "/nonexistent/node/path/xyz")
        worker = make_worker()
        cmd = worker._build_download_command()
        idx = cmd.index("--js-runtimes")
        assert cmd[idx + 1] == "node"

    def test_overwrite_adds_force_flag_for_full_download(self, patched_utils):
        worker = make_worker(overwrite=True)
        cmd = worker._build_download_command()
        assert "--force-overwrites" in cmd

    def test_overwrite_not_added_for_clip(self, patched_utils):
        worker = make_worker(overwrite=True)
        cmd = worker._build_download_command(for_clip=True)
        assert "--force-overwrites" not in cmd

    def test_no_overwrite_flag_by_default(self, patched_utils):
        worker = make_worker(overwrite=False)
        cmd = worker._build_download_command()
        assert "--force-overwrites" not in cmd

    def test_always_includes_static_flags(self, patched_utils):
        worker = make_worker()
        cmd = worker._build_download_command()
        for flag in ("--no-playlist", "--no-part", "--no-check-certificates", "--newline"):
            assert flag in cmd


# ---------------------------------------------------------------------------
# _run_ytdlp_process
# ---------------------------------------------------------------------------

class TestRunYtdlpProcess:

    def test_successful_run_returns_true_and_emits_100(self, patched_utils, monkeypatch):
        worker = make_worker()
        progress = connect_capture(worker.progress)
        fake_proc = FakeProcess(stdout_lines=["[download]  10.0% of 5MiB\n"], returncode=0)
        monkeypatch.setattr(dw.subprocess, "Popen", lambda *a, **k: fake_proc)

        result = worker._run_ytdlp_process(["fake", "cmd"])

        assert result is True
        assert 10 in progress
        assert progress[-1] == 100

    def test_failed_returncode_returns_false(self, patched_utils, monkeypatch):
        worker = make_worker()
        fake_proc = FakeProcess(stdout_lines=[], returncode=1)
        monkeypatch.setattr(dw.subprocess, "Popen", lambda *a, **k: fake_proc)

        result = worker._run_ytdlp_process(["fake", "cmd"])
        assert result is False

    def test_progress_percent_parsed_and_capped_at_99(self, patched_utils, monkeypatch):
        worker = make_worker()
        progress = connect_capture(worker.progress)
        fake_proc = FakeProcess(stdout_lines=["[download] 100.0% of 5MiB\n"], returncode=0)
        monkeypatch.setattr(dw.subprocess, "Popen", lambda *a, **k: fake_proc)

        worker._run_ytdlp_process(["fake", "cmd"])
        # 100.0% deve ser limitado a 99 antes do 100 final emitido no fim
        assert 99 in progress

    def test_progress_only_emitted_when_increasing(self, patched_utils, monkeypatch):
        worker = make_worker()
        progress = connect_capture(worker.progress)
        lines = [
            "[download]  10.0% of 5MiB\n",
            "[download]  10.0% of 5MiB\n",   # repetido, não deve emitir de novo
            "[download]  20.0% of 5MiB\n",
        ]
        fake_proc = FakeProcess(stdout_lines=lines, returncode=0)
        monkeypatch.setattr(dw.subprocess, "Popen", lambda *a, **k: fake_proc)

        worker._run_ytdlp_process(["fake", "cmd"])
        # apenas uma emissão de 10, uma de 20, e o 100 final
        assert progress.count(10) == 1
        assert progress.count(20) == 1

    def test_merge_started_suppresses_further_progress(self, patched_utils, monkeypatch):
        worker = make_worker()
        progress = connect_capture(worker.progress)
        lines = [
            "[download]  10.0% of 5MiB\n",
            "[ffmpeg] Merging formats into output\n",
            "[download]  50.0% of 5MiB\n",
        ]
        fake_proc = FakeProcess(stdout_lines=lines, returncode=0)
        monkeypatch.setattr(dw.subprocess, "Popen", lambda *a, **k: fake_proc)

        worker._run_ytdlp_process(["fake", "cmd"])
        # 50% nunca deve aparecer porque o merge já começou
        assert 50 not in progress
        assert progress == [10, 100]

    def test_second_stream_resets_progress_instead_of_freezing(self, patched_utils, monkeypatch):
        # download de MP4 padrão baixa video e audio como streams separados;
        # a segunda stream reinicia em 0% e não pode ficar presa no valor
        # máximo (99) atingido pela primeira - reproduz o bug da barra
        # travando em 99% assim que o video termina e o audio começa
        worker = make_worker()
        progress = connect_capture(worker.progress)
        lines = [
            "[download] Destination: video.f137.mp4\n",
            "[download]  50.0% of 5MiB\n",
            "[download] 100.0% of 5MiB\n",
            "[download] Destination: audio.f140.m4a\n",
            "[download]  30.0% of 1MiB\n",
            "[download] 100.0% of 1MiB\n",
        ]
        fake_proc = FakeProcess(stdout_lines=lines, returncode=0)
        monkeypatch.setattr(dw.subprocess, "Popen", lambda *a, **k: fake_proc)

        worker._run_ytdlp_process(["fake", "cmd"])
        # a segunda stream deve emitir seu proprio 30% mesmo depois do
        # primeiro stream ja ter chegado a 99
        assert 30 in progress
        assert progress == [50, 99, 30, 99, 100]

    def test_merging_formats_text_also_triggers_merge_state(self, patched_utils, monkeypatch):
        worker = make_worker()
        progress = connect_capture(worker.progress)
        lines = [
            "Merging formats into 'final.mp4'\n",
            "[download]  50.0% of 5MiB\n",
        ]
        fake_proc = FakeProcess(stdout_lines=lines, returncode=0)
        monkeypatch.setattr(dw.subprocess, "Popen", lambda *a, **k: fake_proc)

        worker._run_ytdlp_process(["fake", "cmd"])
        assert 50 not in progress

    def test_malformed_percent_line_does_not_raise(self, patched_utils, monkeypatch):
        worker = make_worker()
        lines = ["[download] not-a-percent% of 5MiB\n"]
        fake_proc = FakeProcess(stdout_lines=lines, returncode=0)
        monkeypatch.setattr(dw.subprocess, "Popen", lambda *a, **k: fake_proc)

        result = worker._run_ytdlp_process(["fake", "cmd"])
        assert result is True  # não deve lançar exceção

    def test_cancelled_breaks_loop_and_returns_false(self, patched_utils, monkeypatch):
        worker = make_worker()
        worker._is_cancelled = True
        cancelled_signal = connect_capture(worker.cancelled)

        killed = {"called": False}
        fake_proc = FakeProcess(stdout_lines=["[download]  10.0% of 5MiB\n"], returncode=0)

        def fake_kill_tree():
            killed["called"] = True

        monkeypatch.setattr(worker, "_kill_process_tree", fake_kill_tree)
        monkeypatch.setattr(dw.subprocess, "Popen", lambda *a, **k: fake_proc)

        result = worker._run_ytdlp_process(["fake", "cmd"])

        assert result is False
        assert killed["called"] is True
        assert worker.item.status == "cancelled"
        assert len(cancelled_signal) == 1

    def test_empty_lines_are_skipped(self, patched_utils, monkeypatch):
        worker = make_worker()
        lines = ["", "[download]  30.0% of 5MiB\n"]
        fake_proc = FakeProcess(stdout_lines=lines, returncode=0)
        monkeypatch.setattr(dw.subprocess, "Popen", lambda *a, **k: fake_proc)

        result = worker._run_ytdlp_process(["fake", "cmd"])
        assert result is True

    def test_windows_uses_create_no_window_flag(self, patched_utils, monkeypatch):
        monkeypatch.setattr(dw.sys, "platform", "win32")
        monkeypatch.setattr(dw.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
        captured_kwargs = {}

        def fake_popen(cmd, **kwargs):
            captured_kwargs.update(kwargs)
            return FakeProcess(stdout_lines=[], returncode=0)

        monkeypatch.setattr(dw.subprocess, "Popen", fake_popen)
        worker = make_worker()
        worker._run_ytdlp_process(["fake", "cmd"])

        assert captured_kwargs["creationflags"] == 0x08000000


# ---------------------------------------------------------------------------
# _run_ffmpeg
# ---------------------------------------------------------------------------

class TestRunFfmpeg:

    def test_successful_run_returns_true(self, patched_utils, monkeypatch):
        worker = make_worker()
        fake_proc = FakeProcess(stdout_lines=[b"", b""], returncode=0)
        monkeypatch.setattr(dw.subprocess, "Popen", lambda *a, **k: fake_proc)

        assert worker._run_ffmpeg(["ffmpeg", "-i", "in.mp4"]) is True

    def test_nonzero_returncode_returns_false(self, patched_utils, monkeypatch):
        worker = make_worker()
        fake_proc = FakeProcess(stdout_lines=[], returncode=1)
        monkeypatch.setattr(dw.subprocess, "Popen", lambda *a, **k: fake_proc)

        assert worker._run_ffmpeg(["ffmpeg", "-i", "in.mp4"]) is False

    def test_exception_creating_process_returns_false(self, patched_utils, monkeypatch):
        worker = make_worker()

        def raise_err(*a, **k):
            raise OSError("cannot start process")

        monkeypatch.setattr(dw.subprocess, "Popen", raise_err)
        assert worker._run_ffmpeg(["ffmpeg"]) is False

    def test_cancelled_kills_process_and_returns_false(self, patched_utils, monkeypatch):
        worker = make_worker()
        worker._is_cancelled = True
        killed = {"called": False}
        fake_proc = FakeProcess(stdout_lines=[b"line"], returncode=0)

        monkeypatch.setattr(worker, "_kill_process_tree", lambda: killed.update(called=True))
        monkeypatch.setattr(dw.subprocess, "Popen", lambda *a, **k: fake_proc)

        result = worker._run_ffmpeg(["ffmpeg"])
        assert result is False
        assert killed["called"] is True


# ---------------------------------------------------------------------------
# _run_clip_strategy
# ---------------------------------------------------------------------------

class TestRunClipStrategy:

    def test_successful_clip_flow_returns_output_path(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="clip video", output_path=str(tmp_path),
                         clip_start=1.0, clip_end=5.0, format_type="MP4")
        worker = make_worker(item)

        # simula que o download temporário já criou o arquivo full_tmp
        full_tmp = tmp_path / "clip video__full_tmp.mp4"
        full_tmp.write_text("data")

        monkeypatch.setattr(worker, "_run_ytdlp_process", lambda cmd: True)
        monkeypatch.setattr(worker, "_run_ffmpeg", lambda cmd: True)

        result = worker._run_clip_strategy()

        expected_out = str(tmp_path / "clip video.mp4")
        assert result == expected_out
        # o arquivo temporário deve ter sido removido ao final
        assert not full_tmp.exists()

    def test_cancelled_before_ffmpeg_cleans_up_and_returns_none(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="clip video", output_path=str(tmp_path), clip_start=1.0)
        worker = make_worker(item)

        def fake_run_ytdlp(cmd):
            worker._is_cancelled = True
            return True

        monkeypatch.setattr(worker, "_run_ytdlp_process", fake_run_ytdlp)
        result = worker._run_clip_strategy()
        assert result is None

    def test_download_failure_raises_and_cleans_up(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="clip video", output_path=str(tmp_path), clip_start=1.0)
        worker = make_worker(item)
        monkeypatch.setattr(worker, "_run_ytdlp_process", lambda cmd: False)

        with pytest.raises(Exception, match="Falha no download do vídeo completo"):
            worker._run_clip_strategy()

    def test_missing_temp_file_raises_exception(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="clip video", output_path=str(tmp_path), clip_start=1.0)
        worker = make_worker(item)
        monkeypatch.setattr(worker, "_run_ytdlp_process", lambda cmd: True)
        # não criamos nenhum arquivo __full_tmp

        with pytest.raises(Exception, match="Arquivo temporário não encontrado"):
            worker._run_clip_strategy()

    def test_uses_fallback_ffmpeg_command_when_first_attempt_fails(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="clip video", output_path=str(tmp_path),
                         clip_start=1.0, clip_end=5.0, format_type="MP4")
        worker = make_worker(item)
        full_tmp = tmp_path / "clip video__full_tmp.mp4"
        full_tmp.write_text("data")

        monkeypatch.setattr(worker, "_run_ytdlp_process", lambda cmd: True)

        calls = []

        def fake_ffmpeg(cmd):
            calls.append(cmd)
            return len(calls) == 2  # falha na primeira, sucesso na segunda (fallback)

        monkeypatch.setattr(worker, "_run_ffmpeg", fake_ffmpeg)

        result = worker._run_clip_strategy()

        assert len(calls) == 2
        assert "-c" in calls[0] and "copy" in calls[0]
        assert "libx264" in calls[1]
        assert result is not None

    def test_mp3_clip_does_not_attempt_fallback(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="clip audio", output_path=str(tmp_path),
                         clip_start=1.0, clip_end=5.0, format_type="MP3")
        worker = make_worker(item)
        full_tmp = tmp_path / "clip audio__full_tmp.m4a"
        full_tmp.write_text("data")

        monkeypatch.setattr(worker, "_run_ytdlp_process", lambda cmd: True)

        calls = []

        def fake_ffmpeg(cmd):
            calls.append(cmd)
            return False  # sempre falha

        monkeypatch.setattr(worker, "_run_ffmpeg", fake_ffmpeg)

        with pytest.raises(Exception, match="ffmpeg falhou ao cortar"):
            worker._run_clip_strategy()

        # apenas uma tentativa, sem fallback, pois é MP3
        assert len(calls) == 1

    def test_output_name_incremented_on_conflict(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="clip video", output_path=str(tmp_path),
                         clip_start=1.0, clip_end=5.0, format_type="MP4", overwrite=False)
        worker = make_worker(item)
        full_tmp = tmp_path / "clip video__full_tmp.mp4"
        full_tmp.write_text("data")
        # já existe um "clip video.mp4" final
        (tmp_path / "clip video.mp4").write_text("existing")

        monkeypatch.setattr(worker, "_run_ytdlp_process", lambda cmd: True)
        monkeypatch.setattr(worker, "_run_ffmpeg", lambda cmd: True)

        result = worker._run_clip_strategy()
        assert result == str(tmp_path / "clip video (1).mp4")

    def test_overwrite_true_does_not_increment(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="clip video", output_path=str(tmp_path),
                         clip_start=1.0, clip_end=5.0, format_type="MP4", overwrite=True)
        worker = make_worker(item)
        full_tmp = tmp_path / "clip video__full_tmp.mp4"
        full_tmp.write_text("data")
        (tmp_path / "clip video.mp4").write_text("existing")

        monkeypatch.setattr(worker, "_run_ytdlp_process", lambda cmd: True)
        monkeypatch.setattr(worker, "_run_ffmpeg", lambda cmd: True)

        result = worker._run_clip_strategy()
        assert result == str(tmp_path / "clip video.mp4")

    def test_cancelled_after_cut_removes_output_and_returns_none(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="clip video", output_path=str(tmp_path),
                         clip_start=1.0, clip_end=5.0, format_type="MP4")
        worker = make_worker(item)
        full_tmp = tmp_path / "clip video__full_tmp.mp4"
        full_tmp.write_text("data")
        out_path = tmp_path / "clip video.mp4"

        monkeypatch.setattr(worker, "_run_ytdlp_process", lambda cmd: True)

        def fake_ffmpeg(cmd):
            out_path.write_text("cut result")
            worker._is_cancelled = True
            return True

        monkeypatch.setattr(worker, "_run_ffmpeg", fake_ffmpeg)

        result = worker._run_clip_strategy()
        assert result is None
        assert not out_path.exists()


# ---------------------------------------------------------------------------
# run_download (orquestração)
# ---------------------------------------------------------------------------

class TestRunDownload:

    def test_successful_full_download_emits_finished(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="video", output_path=str(tmp_path), format_type="MP4")
        worker = make_worker(item)
        finished = connect_capture(worker.finished)

        # arquivo final "baixado"
        final_file = tmp_path / "video.mp4"

        monkeypatch.setattr(worker, "_build_download_command", lambda: ["cmd"])
        monkeypatch.setattr(worker, "_run_ytdlp_process", lambda cmd: True)

        def fake_find():
            final_file.write_text("data")
            return str(final_file)

        monkeypatch.setattr(worker, "_find_downloaded_file", fake_find)

        worker.run_download()

        assert item.status == "completed"
        assert item.file_path == str(final_file)
        assert len(finished) == 1

    def test_process_failure_emits_error(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="video", output_path=str(tmp_path), status="downloading")
        worker = make_worker(item)
        error_signal = connect_capture(worker.error)

        monkeypatch.setattr(worker, "_build_download_command", lambda: ["cmd"])
        monkeypatch.setattr(worker, "_run_ytdlp_process", lambda cmd: False)

        worker.run_download()

        assert item.status == "error"
        assert len(error_signal) == 1

    def test_process_failure_with_cancelled_status_no_error_emitted(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="video", output_path=str(tmp_path))
        worker = make_worker(item)
        error_signal = connect_capture(worker.error)
        finished_signal = connect_capture(worker.finished)

        def fake_run(cmd):
            item.status = "cancelled"
            return False

        monkeypatch.setattr(worker, "_build_download_command", lambda: ["cmd"])
        monkeypatch.setattr(worker, "_run_ytdlp_process", fake_run)

        worker.run_download()

        assert len(error_signal) == 0
        assert len(finished_signal) == 0

    def test_missing_final_file_emits_error(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="video", output_path=str(tmp_path))
        worker = make_worker(item)
        error_signal = connect_capture(worker.error)

        monkeypatch.setattr(worker, "_build_download_command", lambda: ["cmd"])
        monkeypatch.setattr(worker, "_run_ytdlp_process", lambda cmd: True)
        monkeypatch.setattr(worker, "_find_downloaded_file", lambda: "")

        worker.run_download()

        assert item.status == "error"
        assert len(error_signal) == 1
        assert "não encontrado" in error_signal[0][1]

    def test_clip_item_calls_clip_strategy(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="video", output_path=str(tmp_path), clip_start=1.0, clip_end=2.0)
        worker = make_worker(item)
        finished = connect_capture(worker.finished)

        final_file = tmp_path / "video.mp4"

        def fake_clip_strategy():
            final_file.write_text("data")
            return str(final_file)

        monkeypatch.setattr(worker, "_run_clip_strategy", fake_clip_strategy)

        worker.run_download()

        assert item.status == "completed"
        assert len(finished) == 1

    def test_cancelled_flag_skips_finished_emission(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="video", output_path=str(tmp_path))
        worker = make_worker(item)
        finished_signal = connect_capture(worker.finished)
        error_signal = connect_capture(worker.error)

        def fake_run(cmd):
            worker._is_cancelled = True
            return True

        monkeypatch.setattr(worker, "_build_download_command", lambda: ["cmd"])
        monkeypatch.setattr(worker, "_run_ytdlp_process", fake_run)
        monkeypatch.setattr(worker, "_find_downloaded_file", lambda: "")

        worker.run_download()

        assert len(finished_signal) == 0
        assert len(error_signal) == 0

    def test_cleans_up_partial_files_before_download(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="video", output_path=str(tmp_path))
        worker = make_worker(item)

        partial = tmp_path / "video.part"
        partial.write_text("junk")

        monkeypatch.setattr(worker, "_build_download_command", lambda: ["cmd"])
        monkeypatch.setattr(worker, "_run_ytdlp_process", lambda cmd: False)  # falha para encurtar o teste

        worker.run_download()

        assert not partial.exists()

    def test_cleanup_ignores_removal_errors(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="video", output_path=str(tmp_path))
        worker = make_worker(item)

        monkeypatch.setattr(dw.glob, "glob", lambda pattern: ["/fake/nonexistent/video.part"])
        monkeypatch.setattr(worker, "_build_download_command", lambda: ["cmd"])
        monkeypatch.setattr(worker, "_run_ytdlp_process", lambda cmd: False)

        # não deve levantar exceção mesmo que os.remove falhe (arquivo não existe)
        worker.run_download()
        assert item.status == "error"

    def test_generic_exception_sets_error_status(self, patched_utils, monkeypatch, tmp_path):
        item = FakeItem(title="video", output_path=str(tmp_path))
        worker = make_worker(item)
        error_signal = connect_capture(worker.error)

        def raise_err():
            raise RuntimeError("boom")

        monkeypatch.setattr(worker, "_build_download_command", raise_err)

        worker.run_download()

        assert item.status == "error"
        assert error_signal[0][1] == "boom"


# ---------------------------------------------------------------------------
# cancel / _kill_process_tree
# ---------------------------------------------------------------------------

class TestCancel:

    def test_cancel_sets_flag_and_kills_tree(self, patched_utils, monkeypatch):
        worker = make_worker()
        called = {"kill": False}
        monkeypatch.setattr(worker, "_kill_process_tree", lambda: called.update(kill=True))

        worker.cancel()

        assert worker._is_cancelled is True
        assert called["kill"] is True


class TestKillProcessTree:

    def test_no_process_returns_silently(self, patched_utils):
        worker = make_worker()
        worker.process = None
        worker._kill_process_tree()  # não deve lançar

    def test_linux_kills_process_directly(self, patched_utils):
        worker = make_worker()
        fake_proc = FakeProcess()
        worker.process = fake_proc
        worker._kill_process_tree()
        assert fake_proc.killed is True

    def test_windows_uses_taskkill_with_pid(self, patched_utils, monkeypatch):
        monkeypatch.setattr(dw.sys, "platform", "win32")
        monkeypatch.setattr(dw.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
        worker = make_worker()
        fake_proc = FakeProcess(pid=999)
        worker.process = fake_proc

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs

        monkeypatch.setattr(dw.subprocess, "run", fake_run)
        worker._kill_process_tree()

        assert captured["cmd"] == ["taskkill", "/F", "/T", "/PID", "999"]
        assert fake_proc.killed is False  # taskkill usado, não .kill()

    def test_windows_without_pid_falls_back_to_kill(self, patched_utils, monkeypatch):
        monkeypatch.setattr(dw.sys, "platform", "win32")
        worker = make_worker()
        fake_proc = FakeProcess()
        fake_proc.pid = None
        worker.process = fake_proc

        worker._kill_process_tree()
        assert fake_proc.killed is True

    def test_exception_falls_back_to_second_kill_attempt(self, patched_utils, monkeypatch):
        worker = make_worker()

        call_count = {"n": 0}

        class WeirdProcess(FakeProcess):
            def kill(self):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise OSError("first kill failed")
                super().kill()

        fake_proc = WeirdProcess()
        worker.process = fake_proc
        # força o branch "else" (linux) e ele lança na primeira tentativa de kill,
        # cai no except e tenta de novo
        worker._kill_process_tree()
        assert call_count["n"] == 2
        assert fake_proc.killed is True

    def test_both_kill_attempts_failing_is_swallowed(self, patched_utils, monkeypatch):
        worker = make_worker()

        class AlwaysFailProcess(FakeProcess):
            def kill(self):
                raise OSError("always fails")

        worker.process = AlwaysFailProcess()
        # não deve propagar exceção
        worker._kill_process_tree()


# ---------------------------------------------------------------------------
# _find_downloaded_file
# ---------------------------------------------------------------------------

class TestFindDownloadedFile:

    def test_returns_most_recent_matching_file(self, patched_utils, tmp_path, monkeypatch):
        item = FakeItem(title="video", output_path=str(tmp_path))
        worker = make_worker(item)

        older = tmp_path / "video.webm"
        newer = tmp_path / "video.mp4"
        older.write_text("a")
        newer.write_text("b")

        # garante ctime diferente de forma determinística
        times = iter([100.0, 200.0])
        real_getctime = os.path.getctime

        def fake_getctime(path):
            if path == str(older):
                return 100.0
            if path == str(newer):
                return 200.0
            return real_getctime(path)

        monkeypatch.setattr(dw.os.path, "getctime", fake_getctime)

        result = worker._find_downloaded_file()
        assert result == str(newer)

    def test_excludes_partial_and_temp_files(self, patched_utils, tmp_path):
        item = FakeItem(title="video", output_path=str(tmp_path))
        worker = make_worker(item)

        (tmp_path / "video.part").write_text("x")
        (tmp_path / "video.ytdl").write_text("x")
        (tmp_path / "video.temp").write_text("x")
        (tmp_path / "video__full_tmp.mp4").write_text("x")

        result = worker._find_downloaded_file()
        assert result == ""

    def test_returns_empty_string_when_no_files_found(self, patched_utils, tmp_path):
        item = FakeItem(title="video", output_path=str(tmp_path))
        worker = make_worker(item)
        result = worker._find_downloaded_file()
        assert result == ""

    def test_exception_returns_empty_string(self, patched_utils, monkeypatch, tmp_path, capsys):
        item = FakeItem(title="video", output_path=str(tmp_path))
        worker = make_worker(item)

        def raise_err(pattern):
            raise OSError("glob failed")

        monkeypatch.setattr(dw.glob, "glob", raise_err)
        result = worker._find_downloaded_file()
        assert result == ""