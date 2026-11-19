"""Extra FFmpeg tools test: page wiring, command building and one real run.

Run from the project root:  python tests/ffmpeg_tools_test.py
"""
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    try:
        from app.config import ConfigManager
        from app.core.failures import FailureStore
        from app.core.history import HistoryStore
        from app.ui.app import MediaDownloaderApp, _ffmpeg_filter_path
        from app.utils.ffmpeg import FFmpegInfo, find_ffmpeg

        with tempfile.TemporaryDirectory() as tmp:
            config = ConfigManager(path=Path(tmp) / "config.json")
            app = MediaDownloaderApp(
                config=config,
                history=HistoryStore(path=Path(tmp) / "history.json"),
                failures=FailureStore(path=Path(tmp) / "failures.json"),
            )
            app.update()

            expected = {
                "extract", "compress", "trim", "convert",
                "gif", "merge", "subtitle", "cover",
            }
            if set(app.tool_status_labels) != expected:
                raise AssertionError(f"tool page mismatch: {sorted(app.tool_status_labels)}")
            if len(app.tool_file_labels) != 8:
                raise AssertionError("every tool needs a file picker")
            print("[ok] tools page: 8 tools with pickers and status labels")

            # Deterministic command checks independent of a real FFmpeg install.
            app.ffmpeg = FFmpegInfo(
                ffmpeg=Path(tmp) / "ffmpeg.exe", ffprobe=None, directory=Path(tmp)
            )
            source = str(Path(tmp) / "movie.mp4")
            suffixes = {
                "extract": "_audio.mp3", "compress": "_compressed.mp4",
                "trim": "_trim.mp4", "convert": "_converted.mkv",
                "gif": "_animated.gif", "merge": "_merged.mp4",
                "subtitle": "_subtitled.mp4", "cover": "_cover.jpg",
            }
            for tool, suffix in suffixes.items():
                out = app._tool_output_path(tool, source, {"format": "mkv"})
                if not out.endswith(suffix):
                    raise AssertionError(f"{tool}: bad output suffix {out!r}")
            print("[ok] output paths: 8 suffixes incl. selected convert format")

            convert_cmd = app._tool_command(
                "convert", source, str(Path(tmp) / "a.mkv"), {"format": "mkv"}
            )
            if convert_cmd is None or "libx264" not in convert_cmd:
                raise AssertionError("mkv conversion should use libx264")
            mp3_cmd = app._tool_command(
                "convert", source, str(Path(tmp) / "a.mp3"), {"format": "mp3"}
            )
            if mp3_cmd is None or "-vn" not in mp3_cmd or "libmp3lame" not in mp3_cmd:
                raise AssertionError("mp3 conversion should drop video")
            gif_cmd = app._tool_command(
                "gif", source, str(Path(tmp) / "a.gif"),
                {"start": "1", "duration": "2", "fps": "10", "width": "320"},
            )
            if gif_cmd is None or "fps=10,scale=320:-2" not in gif_cmd or "-loop" not in gif_cmd:
                raise AssertionError(f"GIF filter wrong: {gif_cmd!r}")
            audio = str(Path(tmp) / "voice.m4a")
            merge_cmd = app._tool_command(
                "merge", source, str(Path(tmp) / "m.mp4"), {"second": audio}
            )
            if merge_cmd is None or merge_cmd.count("-i") != 2 or "-shortest" not in merge_cmd:
                raise AssertionError(f"merge wrong: {merge_cmd!r}")
            sub = r"C:\subs\clip 1.srt"
            sub_cmd = app._tool_command(
                "subtitle", source, str(Path(tmp) / "s.mp4"), {"second": sub}
            )
            if sub_cmd is None or "subtitles=C\\:\\\\subs\\\\clip 1.srt" not in sub_cmd:
                raise AssertionError(f"subtitle escaping wrong: {sub_cmd!r}")
            cover_cmd = app._tool_command(
                "cover", source, str(Path(tmp) / "c.jpg"), {}
            )
            if cover_cmd is None or "-frames:v" not in cover_cmd or "-update" not in cover_cmd:
                raise AssertionError(f"cover wrong: {cover_cmd!r}")
            print("[ok] commands: convert/GIF/merge/subtitle/cover built correctly")

            if app._tool_command("gif", source, "x", {"duration": "0", "fps": "99"}) is not None:
                raise AssertionError("invalid GIF values must be rejected")
            if app._tool_command("merge", source, "x", {"second": ""}) is not None:
                raise AssertionError("merge without audio must be rejected")
            if _ffmpeg_filter_path("a'b.srt") != "a\\'b.srt":
                raise AssertionError("quote escaping failed")
            print("[ok] validation: bad values rejected, filter path escaped")

            # Optional real end-to-end check when FFmpeg is installed.
            real = find_ffmpeg()
            if real:
                app.ffmpeg = real
                clip = Path(tmp) / "clip.mp4"
                make = [
                    str(real.ffmpeg), "-y", "-f", "lavfi",
                    "-i", "testsrc=size=160x90:rate=10:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip),
                ]
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
                subprocess.run(make, capture_output=True, creationflags=flags, timeout=60)
                if clip.exists():
                    cover = Path(tmp) / "cover.jpg"
                    cmd = app._tool_command("cover", str(clip), str(cover), {})
                    if cmd is None:
                        raise AssertionError("real cover command was not built")
                    result = subprocess.run(cmd, capture_output=True, creationflags=flags, timeout=60)
                    if result.returncode != 0 or not cover.exists():
                        raise AssertionError(f"real cover extraction failed: {result.stderr[-200:]!r}")
                    print("[ok] real FFmpeg: generated a clip and extracted its cover")
            else:
                print("[skip] real FFmpeg not installed; command checks only")

            app.destroy()
            print("[ok] destroyed cleanly")
            return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
