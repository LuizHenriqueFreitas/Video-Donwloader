# ui/workers/download_worker.py

""" Here you will find (more relevant metods):
    - run_download() function;
    - build_download_command;
    - _run_ytdlp thread function;
    - _run_ffmepg thread function;
    - _run_clip alternative download;
    - _kill process fallbacks;
    - _find_file_path;

    About Logic implemented
        Download_builder function and Clip_strategy function
        both implement ytdlp and ffmpeg separatly, like
        util/video_info.py too.

        Maybe in next versions is a good ideia refatorate this 
        and move some of this file functions to another file.
"""

import os
import glob
import subprocess
import sys
import threading

from PySide6.QtCore import QObject, Signal

from core.utils import (
    get_ffmpeg_path,
    get_ffmpeg_exe,
    get_ytdlp_path,
    get_node_path,
    get_cookies_path,
    cookies_exists,
    is_youtube,
    safe_filename,
    YOUTUBE_CLIENT_SETTINGS
)

# main class from this file
class DownloadWorker(QObject):
    progress = Signal(int)
    finished = Signal(object)
    error = Signal(object, str)
    cancelled = Signal(object)

    def __init__(self, item):
        super().__init__()
        # this "item" came from models/download_item.py
        self.item = item
        self.process = None
        self._is_cancelled = False
        self._last_stderr = ""


    """ ======================
        RUN DOWNLOAD FUNCTION
      ====================== """
    # main class function, manage all download configuration
    def run_download(self):
        # check if the donwload was cancelled
        if self._is_cancelled:
            self.item.status = "cancelled"
            self.cancelled.emit(self.item)
            return

        try:
            self.item.status = "downloading"
            self.progress.emit(0)

            # below checking if file is unique on the outpot path
            safe_title = safe_filename(self.item.title)
            base = os.path.join(self.item.output_path, safe_title)
            for pattern in [f"{base}*.part", f"{base}*.ytdl", f"{base}*.temp", f"{base}*.frag*"]:
                for f in glob.glob(pattern):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

            # check if it's a clip from a entire video
            is_clip = (getattr(self.item, "clip_start", None) is not None
                       or getattr(self.item, "clip_end", None) is not None)

            # if it's a clip, call the specific function
            if is_clip:
                final_path = self._run_clip_strategy()
            # if isn't a clip, build download command line and run process
            else:
                command = self._build_download_command()
                success = self._run_ytdlp_process(command)

                if not success:
                    if self.item.status == "cancelled":
                        return
                    # this will need to be translate on location update
                    detail = self._last_stderr.splitlines()[-1] if self._last_stderr else ""
                    message = f"Falha no download (yt-dlp retornou erro): {detail}" if detail else "Falha no download (yt-dlp retornou erro)"
                    raise Exception(message)

                final_path = self._find_downloaded_file()

            # if cancelled, skip reminder code
            if self._is_cancelled:
                self.item.status = "cancelled"
                self.cancelled.emit(self.item)
                return

            # check file path
            if not final_path or not os.path.exists(final_path):
                # this will need to be translate on location update
                raise Exception("Arquivo final não encontrado")

            # finish run process
            self.item.file_path = final_path
            self.item.status = "completed"
            self.finished.emit(self.item)

        # Exception sender if there's an error ocurred
        except Exception as e:
            if self._is_cancelled:
                return
            self.item.status = "error"
            self.error.emit(self.item, str(e))


    """ ==========================
        TRIMMER TOOL OPTIONS
       ========================= """

    """ Maybe could that be changed to another file, just to that function
        because has a lot o code on this file, and that is a very different function.
    """

    # if is a clip, need to use that function
    def _run_clip_strategy(self):
        # get necessary resources
        ffmpeg_exe = get_ffmpeg_exe()
        safe_title = safe_filename(self.item.title)

        """ The clip download logic is that: 
            - First download the entire clip, so you will need to have all the 
            clip size on your disk. 
            - After downloaded the app will use ffmpeg to cut the file to the clip.
            - And after this the complete file will be deleted.
            - At the final you will have just the clip part you select.

            That was decided because is a stable and simple option.
        """
        tmp_title = f"{safe_title}__full_tmp"
        tmp_template = os.path.join(self.item.output_path, f"{tmp_title}.%(ext)s")

        # call commandline builder and start download process
        command = self._build_download_command(output_override=tmp_template, for_clip=True)
        success = self._run_ytdlp_process(command)

        # if canceled checker
        if self._is_cancelled:
            self._cleanup_pattern(os.path.join(self.item.output_path, f"{tmp_title}*"))
            return None

        # if error checker
        if not success:
            self._cleanup_pattern(os.path.join(self.item.output_path, f"{tmp_title}*"))
            # this will need to be translate on location update
            detail = self._last_stderr.splitlines()[-1] if self._last_stderr else ""
            message = f"Falha no download do vídeo completo: {detail}" if detail else "Falha no download do vídeo completo"
            raise Exception(message)

        # temporary full file verification
        full_files = glob.glob(os.path.join(self.item.output_path, f"{tmp_title}*"))
        full_files = [f for f in full_files if not f.endswith((".part", ".ytdl", ".temp"))]
        # if temp file was not found return an error
        if not full_files:
            # this will need to be translate on location update
            raise Exception("Arquivo temporário não encontrado")
        full_path = max(full_files, key=os.path.getctime)

        # emit UI progress information
        self.progress.emit(99)

        """ From here we already has the temp full video localy
            we'll just extract the wished clip using ffmepg operations.
        """
        # get start and end clip time stamps
        clip_start = getattr(self.item, "clip_start", None)
        clip_end = getattr(self.item, "clip_end", None)

        # get clip format (extension, like .mp4 or .mp3) and output path
        fmt = (self.item.format_type or "MP4").upper()
        out_ext = ".mp3" if fmt == "MP3" else ".mp4"
        out_path = os.path.join(self.item.output_path, f"{safe_title}{out_ext}")

        # if path exists and is not to overwrite older file with same name
        # increment "(x)", where x is a number at the end of file name
        if os.path.exists(out_path) and not getattr(self.item, "overwrite", False):
            base_name = safe_title
            i = 1
            while os.path.exists(out_path):
                out_path = os.path.join(self.item.output_path, f"{base_name} ({i}){out_ext}")
                i += 1

        # start ffmpeg command line
        ffmpeg_cmd = [ffmpeg_exe, "-hwaccel", "none", "-y", "-i", full_path]
        
        """ Above add the border timestamps because you can let the original 
            video start or end times if is you let the original start and end 
            time so you donwload the full video, not a clip
        """
        # add start and end clip times if exists
        if clip_start is not None:
            ffmpeg_cmd += ["-ss", f"{float(clip_start):.3f}"]
        if clip_end is not None:
            ffmpeg_cmd += ["-to", f"{float(clip_end):.3f}"]

        # configure the extension commandline section
        if fmt == "MP3":
            ffmpeg_cmd += ["-vn", "-c:a", "libmp3lame", "-q:a", "2"]
        else:
            ffmpeg_cmd += ["-c", "copy"]

        # add output path to ffmpeg command line
        ffmpeg_cmd.append(out_path)

        # run ffmpeg with the command line generated earlier
        cut_ok = self._run_ffmpeg(ffmpeg_cmd)

        # fallback if theres a cut bad requesto for some reason
        # just work for .mp4 files
        if not cut_ok and not self._is_cancelled and fmt != "MP3":
            # build fallback commandline
            ffmpeg_cmd2 = [ffmpeg_exe, "-hwaccel", "none", "-y", "-i", full_path]
            # add time stamps border
            if clip_start is not None:
                ffmpeg_cmd2 += ["-ss", f"{float(clip_start):.3f}"]
            if clip_end is not None:
                ffmpeg_cmd2 += ["-to", f"{float(clip_end):.3f}"]
            # fallback comand line args
            ffmpeg_cmd2 += ["-c:v", "libx264", "-c:a", "aac", "-preset", "fast"]
            ffmpeg_cmd2.append(out_path)
            # try again with fallback commandline
            cut_ok = self._run_ffmpeg(ffmpeg_cmd2)

        # remove temporary resources
        try:
            os.remove(full_path)
        except Exception:
            pass

        # if was canceld, remove temporary resouces in use
        if self._is_cancelled:
            try:
                os.remove(out_path)
            except Exception:
                pass
            return None

        if not cut_ok:
            # this will need to be translate on location update
            raise Exception("ffmpeg falhou ao cortar o trecho")

        # final response is the final file path
        return out_path

    # ffmpeg internal process function
    def _run_ffmpeg(self, cmd):
        # windows controller to avoid prompt windows
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        # try to run ffmpeg on separete thread
        try:
            # configurating subprocess
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
            )

            # ffmpeg execution function
            def _drain():
                try:
                    for _ in self.process.stderr:
                        pass
                except Exception:
                    pass

            # start a separete thread, how it is daemon, if the function end the thread is turned off
            threading.Thread(target=_drain, daemon=True).start()

            # check output - kill process tree is there's an error
            for _ in self.process.stdout:
                if self._is_cancelled:
                    self._kill_process_tree()
                    self.cancelled.emit(self.item)
                    return False

            # subprocess finishing
            self.process.wait()
            return self.process.returncode == 0
        
        # return error if bad request tring ffmpeg command
        except Exception:
            return False

    # cleaning internal function - called on error sections
    def _cleanup_pattern(self, pattern):
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except Exception:
                pass


    """ =========================
        DOWNLOAD BUILD COMMAND
     ========================== """
    
    # this function is the download command line constructor
    def _build_download_command(self, output_override=None, for_clip=False):
        # get resouces from utils
        ffmpeg_path = get_ffmpeg_path()
        ytdlp_path = get_ytdlp_path()
        safe_title = safe_filename(self.item.title)

        # check if allow overwrite or need to increment name
        if output_override:
            output_template = output_override
        else:
            output_template = os.path.join(self.item.output_path, f"{safe_title}.%(ext)s")

        # start build yt-dlp command line
        command = [
            ytdlp_path,
            self.item.url,
            "-o", output_template,
            "--ffmpeg-location", ffmpeg_path,
            "--no-playlist",
            "--no-part",
            "--no-check-certificates",
            "--newline",
        ]

        # check cookies
        if cookies_exists():
            command += ["--cookies", get_cookies_path()]

        # get node
        node_path = get_node_path()
        if node_path and os.path.exists(node_path):
            command += ["--js-runtimes", f"node:{node_path}"]
        else:
            command += ["--js-runtimes", "node"]

        # if is the case, set overwrite file mode
        if getattr(self.item, "overwrite", False) and not for_clip:
            command += ["--force-overwrites"]

        # set yt-dlp youtube data client - needed for both MP3 and MP4,
        # otherwise youtube returns "HTTP Error 403: Forbidden" on the default client
        if is_youtube(self.item.url):
            command += YOUTUBE_CLIENT_SETTINGS

        # MP3 download command line
        if self.item.format_type.upper() == "MP3":
            if for_clip:
                # if is a media clip donwload
                command += ["-f", "bestaudio", "--no-keep-video"]
            else:
                # if is a full media audio download
                command += [
                    "-f", "bestaudio",
                    "-x",
                    "--audio-format", "mp3",
                    "--audio-quality", "192K",
                ]
            return command

        # MP4 download command line
        if self.item.format_type.upper() == "MP4":
            # set quality selected
            if self.item.quality_id and "+" in self.item.quality_id:
                # manual selected quality
                video_format = self.item.quality_id
            else:
                # auto best quality
                video_format = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

            # ends yt-dlp command line
            command += [
                "-f", video_format,
                "--merge-output-format", "mp4",
                "--no-mtime",
                "--no-continue",
            ]

            return command

        return command


    """ ====================
            RUN PROCESS
      ==================="""

    def _run_ytdlp_process(self, command):
        # windows controller to avoid prompt windows
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        # configurating subprocess
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            creationflags=creationflags,
        )

        # ytdlp execution function
        stderr_lines = []
        def _drain_stderr():
            try:
                for line in self.process.stderr:
                    stderr_lines.append(line)
            except Exception:
                pass

        # start a separete thread, how it is daemon, if the function end the thread is turned off
        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        # process management
        last_emitted = -1
        merge_started = False

        # check process output
        for line in self.process.stdout:
            # check if was cancelled
            if self._is_cancelled:
                break
            # continue if there's no line
            if not line:
                continue
            # treat line to checkout
            line = line.strip()

            # recognizes whe entry to merging video and audio to same file
            if "Merging formats" in line or "[ffmpeg]" in line:
                merge_started = True
                continue

            # a new "Destination:" line means yt-dlp started a new stream
            # (ex.: video finished, now downloading audio) - percent restarts
            # from 0%, so the high-water mark needs to reset too, otherwise
            # the bar gets stuck at the previous stream's last percent
            if "[download] Destination:" in line:
                last_emitted = -1
                continue

            # get the download '%' to be used on interface
            if "[download]" in line and "%" in line:
                try:
                    percent = float(line.split("%")[0].split()[-1])
                    # if merge state just cotinue because will be paused at 99%
                    if merge_started:
                        continue
                    p = min(99, int(percent))
                    # updates always p was updated
                    if p > last_emitted:
                        last_emitted = p
                        self.progress.emit(p)
                except Exception:
                    pass

        # if it was cancelled - kill all involved process
        if self._is_cancelled:
            self._kill_process_tree()
            try:
                self.process.wait(timeout=5)
            except Exception:
                pass
            self.item.status = "cancelled"
            self.cancelled.emit(self.item)
            return False

        # finishing process
        self.process.wait()
        stderr_thread.join(timeout=5)
        self._last_stderr = "".join(stderr_lines).strip()
        # when merging is concluded emit 100%
        self.progress.emit(100)
        return self.process.returncode == 0


    """ ==========================
            CANCEL PROCESS
      ======================= """

    # cancel function
    def cancel(self):
        # turn _is_cancelled true
        self._is_cancelled = True
        # kill all involved process
        self._kill_process_tree()

    # kill process functions
    def _kill_process_tree(self):
        p = self.process
        # fallback if there's no process
        if not p:
            return
        # try to kill process
        try:
            # for windows OS
            if sys.platform == "win32":
                pid = getattr(p, "pid", None)
                if pid is not None:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                else:
                    p.kill()
            # for linux
            else:
                p.kill()
        # if doens't work, send an error message
        except Exception:
            # try another time
            try:
                p.kill()
            # send error
            except Exception:
                pass


    """ ========================
            FILE FINDER
      ======================= """

    # this function get the system file path
    def _find_downloaded_file(self):
        # try to find the path - very similar in some function above
        try:
            safe_title = safe_filename(self.item.title)
            pattern = os.path.join(self.item.output_path, f"{safe_title}*")
            files = [f for f in glob.glob(pattern)
                     if not f.endswith((".part", ".ytdl", ".temp"))
                     and "__full_tmp" not in f]
            if not files:
                return ""
            return max(files, key=os.path.getctime)
        # bad requesto on try returns empty -> ""
        except Exception as e:
            # this will need to be translate on location update
            # is just a console debug message
            print("Erro ao localizar arquivo:", e)
            return ""