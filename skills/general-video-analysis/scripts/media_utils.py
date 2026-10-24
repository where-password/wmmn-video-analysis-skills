#!/usr/bin/env python3
# wmmn / 我密码呢
"""Shared media, hashing, JSON, and process helpers."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def relative_posix(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def run_command(cmd: Sequence[str], *, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(cmd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def run_binary_command(cmd: Sequence[str], *, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, check=check)


def get_ffmpeg() -> str | None:
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def get_ffprobe() -> str | None:
    path = shutil.which("ffprobe")
    if path:
        return path
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        return None
    candidate = Path(ffmpeg).with_name("ffprobe.exe" if Path(ffmpeg).suffix.lower() == ".exe" else "ffprobe")
    return str(candidate) if candidate.exists() else None


def probe_media(path: Path) -> dict[str, Any]:
    """Return a compact, tool-agnostic media description."""
    ffprobe = get_ffprobe()
    if ffprobe:
        proc = run_command(
            [
                ffprobe,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ]
        )
        if proc.returncode == 0:
            raw = json.loads(proc.stdout or "{}")
            streams = raw.get("streams") or []
            video = next((s for s in streams if s.get("codec_type") == "video"), None)
            audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
            fmt = raw.get("format") or {}
            fps = None
            if video and video.get("avg_frame_rate") and "/" in video["avg_frame_rate"]:
                num, den = video["avg_frame_rate"].split("/", 1)
                try:
                    fps = float(num) / float(den) if float(den) else None
                except ValueError:
                    fps = None
            return {
                "path": str(path),
                "duration_sec": _float_or_none(fmt.get("duration")),
                "size_bytes": _int_or_none(fmt.get("size")),
                "format_name": fmt.get("format_name"),
                "has_video": video is not None,
                "has_audio": audio is not None,
                "width": _int_or_none((video or {}).get("width")),
                "height": _int_or_none((video or {}).get("height")),
                "fps": fps,
                "video_codec": (video or {}).get("codec_name"),
                "audio_codec": (audio or {}).get("codec_name"),
                "sample_rate": _int_or_none((audio or {}).get("sample_rate")),
            }

    try:
        import av

        with av.open(str(path)) as container:
            vstream = next((s for s in container.streams if s.type == "video"), None)
            astream = next((s for s in container.streams if s.type == "audio"), None)
            duration = None
            if container.duration:
                duration = container.duration / 1_000_000.0
            return {
                "path": str(path),
                "duration_sec": duration,
                "size_bytes": path.stat().st_size,
                "format_name": container.format.name if container.format else None,
                "has_video": vstream is not None,
                "has_audio": astream is not None,
                "width": getattr(vstream, "codec_context", None).width if vstream else None,
                "height": getattr(vstream, "codec_context", None).height if vstream else None,
                "fps": float(vstream.average_rate) if vstream and vstream.average_rate else None,
                "video_codec": getattr(vstream, "codec_context", None).name if vstream else None,
                "audio_codec": getattr(astream, "codec_context", None).name if astream else None,
                "sample_rate": getattr(astream, "codec_context", None).sample_rate if astream else None,
            }
    except Exception as exc:
        ffmpeg = get_ffmpeg()
        if ffmpeg:
            proc = run_command([ffmpeg, "-hide_banner", "-i", str(path), "-f", "null", "-"])
            output = proc.stderr or ""
            duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
            duration = None
            if duration_match:
                hours, minutes, seconds = duration_match.groups()
                duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
            video_match = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", output)
            fps_match = re.search(r"Video:.*?(\d+(?:\.\d+)?)\s*fps", output)
            return {
                "path": str(path),
                "duration_sec": duration,
                "size_bytes": path.stat().st_size if path.exists() else None,
                "format_name": None,
                "has_video": "Video:" in output,
                "has_audio": "Audio:" in output,
                "width": int(video_match.group(1)) if video_match else None,
                "height": int(video_match.group(2)) if video_match else None,
                "fps": float(fps_match.group(1)) if fps_match else None,
                "video_codec": None,
                "audio_codec": None,
                "sample_rate": None,
                "probe_method": "ffmpeg_fallback",
            }
        return {
            "path": str(path),
            "duration_sec": None,
            "size_bytes": path.stat().st_size if path.exists() else None,
            "format_name": None,
            "has_video": None,
            "has_audio": None,
            "width": None,
            "height": None,
            "fps": None,
            "video_codec": None,
            "audio_codec": None,
            "sample_rate": None,
            "probe_error": str(exc),
        }


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

