#!/usr/bin/env python3
# wmmn / 我密码呢
"""Visual layer: ffmpeg scene cuts, representative frames, and adjacent-shot change context."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from media_utils import get_ffmpeg, probe_media, relative_posix, run_command, write_json


def detect_cuts(
    ffmpeg: str,
    video: Path,
    start_sec: float,
    duration_sec: float,
    threshold: float,
) -> list[float]:
    proc = run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-ss",
            f"{start_sec:.3f}",
            "-i",
            str(video),
            "-t",
            f"{duration_sec:.3f}",
            "-filter:v",
            f"setpts=PTS-STARTPTS,select='gt(scene,{threshold})',showinfo",
            "-f",
            "null",
            "-",
        ]
    )
    cuts: list[float] = []
    window_end = start_sec + duration_sec
    for match in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", proc.stderr):
        relative_time = float(match.group(1))
        time_sec = start_sec + relative_time
        if start_sec < time_sec < window_end and (not cuts or abs(time_sec - cuts[-1]) > 0.05):
            cuts.append(time_sec)
    return cuts


def extract_frame(ffmpeg: str, video: Path, time_sec: float, path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    seek_start = max(0.0, time_sec - 1.0)
    seek_offset = max(0.0, time_sec - seek_start)
    proc = run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{seek_start:.3f}",
            "-i",
            str(video),
            "-ss",
            f"{seek_offset:.3f}",
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-y",
            str(path),
        ]
    )
    return proc.returncode == 0 and path.exists()


def candidate_times(start: float, end: float, count: int) -> list[float]:
    duration = max(0.0, end - start)
    if duration <= 0.1:
        return [round(start + duration / 2.0, 3)]
    count = max(1, count)
    return [round(start + duration * (index + 1) / (count + 1), 3) for index in range(count)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--threshold", type=float, default=0.35)
    parser.add_argument("--candidates", type=int, default=1, help="Candidate frames sampled per shot; 1 for fast scan, 3-5 only for a detailed request")
    parser.add_argument("--keyframes", type=int, default=None, help="Deprecated alias for --candidates")
    parser.add_argument("--display-source", default=None, help="Sanitized source label written to shots.json")
    parser.add_argument("--start-sec", type=float, default=0.0)
    parser.add_argument("--duration-sec", type=float, default=None)
    args = parser.parse_args()

    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        print("Missing ffmpeg. Install ffmpeg or imageio-ffmpeg.", file=sys.stderr)
        return 1
    video = args.video
    if not video.exists():
        print(f"Video not found: {video}", file=sys.stderr)
        return 1
    info = probe_media(video)
    source_duration = float(info.get("duration_sec") or 0.0)
    if source_duration <= 0:
        print("Cannot read video duration.", file=sys.stderr)
        return 1
    window_start = max(0.0, min(float(args.start_sec or 0.0), source_duration))
    requested_duration = float(args.duration_sec) if args.duration_sec is not None else source_duration - window_start
    window_duration = max(0.001, min(requested_duration, source_duration - window_start))
    window_end = window_start + window_duration

    out = args.out
    key_dir = out / "keyframes"
    key_dir.mkdir(parents=True, exist_ok=True)
    sample_count = args.keyframes if args.keyframes is not None else args.candidates
    sample_count = max(1, min(sample_count, 12))

    cuts = detect_cuts(ffmpeg, video, window_start, window_duration, args.threshold)
    boundaries = [window_start] + cuts + [window_end]
    shots: list[dict[str, Any]] = []
    for index in range(len(boundaries) - 1):
        start, end = boundaries[index], boundaries[index + 1]
        if end - start < 0.05:
            continue
        shot_id = index + 1
        frames: list[dict[str, Any]] = []
        for frame_index, time_sec in enumerate(candidate_times(start, end, sample_count), 1):
            frame_path = key_dir / f"shot_{shot_id:04d}_candidate_{frame_index:02d}.jpg"
            if extract_frame(ffmpeg, video, time_sec, frame_path):
                frames.append(
                    {
                        "time": time_sec,
                        "path": relative_posix(frame_path, out),
                        "role": "candidate",
                        "role_label": "候选帧",
                    }
                )
        representative_index = (
            min(range(len(frames)), key=lambda idx: abs(float(frames[idx]["time"]) - (start + end) / 2.0))
            if frames
            else None
        )
        if representative_index is not None:
            frames[representative_index]["role"] = "representative"
            frames[representative_index]["role_label"] = "代表帧"
        shots.append(
            {
                "id": shot_id,
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "keyframes": frames,
                "representative_keyframe": frames[representative_index]["path"] if representative_index is not None else None,
                "shot_size": None,
                "angle": None,
                "movement": None,
                "transition": "cut" if index > 0 else None,
                "description": None,
                "confidence": None,
            }
        )

    cut_rows: list[dict[str, Any]] = []
    for index, cut_time in enumerate(cuts, 1):
        previous_shot = next((shot for shot in shots if abs(float(shot["end"]) - cut_time) <= 0.12), None)
        following_shot = next((shot for shot in shots if abs(float(shot["start"]) - cut_time) <= 0.12), None)
        before_frame = previous_shot["keyframes"][-1]["path"] if previous_shot and previous_shot["keyframes"] else None
        after_frame = following_shot["keyframes"][0]["path"] if following_shot and following_shot["keyframes"] else None
        cut_rows.append(
            {
                "id": index,
                "time": round(cut_time, 3),
                "score": None,
                "detector": "ffmpeg_scene",
                "threshold": args.threshold,
                "before_frame": before_frame,
                "after_frame": after_frame,
                "status": "measured",
            }
        )

    data = {
        "schema_version": "1.0",
        "video": args.display_source or str(video),
        "duration_sec": round(source_duration, 3),
        "source_duration_sec": round(source_duration, 3),
        "fps": info.get("fps"),
        "analysis_window": {
            "mode": "custom" if window_start > 0 or window_duration < source_duration else "full",
            "start_sec": round(window_start, 3),
            "end_sec": round(window_end, 3),
            "window_duration_sec": round(window_duration, 3),
            "source_duration_sec": round(source_duration, 3),
            "coverage_ratio": round(window_duration / source_duration, 4),
        },
        "detector": {"name": "ffmpeg_scene", "threshold": args.threshold},
        "cuts": cut_rows,
        "shots": shots,
    }
    write_json(out / "shots.json", data)
    print(f"wrote {out / 'shots.json'} (shots={len(shots)}, cuts={len(cuts)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

