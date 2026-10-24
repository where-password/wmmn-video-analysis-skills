#!/usr/bin/env python3
# wmmn / 我密码呢
"""Extract time-coded start/mid/end evidence frames for selected shots."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from media_mechanics import get_ffmpeg, resolve_media

WATERMARK = "wmmn · 我密码呢"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def timecode(seconds: float) -> str:
    milliseconds = int(round(max(0.0, seconds) * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def candidate_times(start: float, end: float) -> list[tuple[str, float]]:
    duration = max(0.001, end - start)
    inset = min(0.25, duration * 0.08)
    first = start + inset
    last = max(first, end - inset)
    middle = (start + end) / 2.0
    return [
        ("start", round(first, 3)),
        ("middle", round(middle, 3)),
        ("end", round(last, 3)),
    ]


def extract_frame(ffmpeg: str, media: Path, seconds: float, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{max(0.0, seconds):.3f}",
            "-i",
            str(media),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-y",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0 or not path.exists():
        raise RuntimeError(f"ffmpeg 提取证据帧失败（{seconds:.3f}s）：{proc.stderr.strip()}")


def font_for_size(size: int) -> ImageFont.ImageFont:
    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return ImageFont.load_default()


def annotate_frame(path: Path, shot_id: int, role: str, seconds: float) -> tuple[int, int]:
    image = Image.open(path).convert("RGB")
    width, height = image.size
    bar_height = max(34, int(height * 0.065))
    canvas = Image.new("RGB", (width, height + bar_height), (18, 18, 18))
    canvas.paste(image, (0, 0))
    draw = ImageDraw.Draw(canvas)
    font = font_for_size(max(13, int(bar_height * 0.38)))
    text = f"{WATERMARK}  |  shot {shot_id:03d}  |  {role}  |  {timecode(seconds)}"
    draw.text((10, height + max(4, (bar_height - 18) // 2)), text, fill=(235, 235, 235), font=font)
    canvas.save(path, quality=92)
    return canvas.size


def make_contact_sheet(frames: list[dict[str, Any]], out_path: Path) -> tuple[int, int]:
    columns = 3
    cell_w, cell_h = 360, 240
    rows = max(1, (len(frames) + columns - 1) // columns)
    footer_h = 34
    sheet = Image.new("RGB", (columns * cell_w, rows * cell_h + footer_h), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    font = font_for_size(14)
    for index, frame in enumerate(frames):
        image = Image.open(frame["absolute_path"]).convert("RGB")
        image = ImageOps.contain(image, (cell_w - 12, cell_h - 12))
        x = (index % columns) * cell_w + (cell_w - image.width) // 2
        y = (index // columns) * cell_h + (cell_h - image.height) // 2
        sheet.paste(image, (x, y))
    draw.text((10, rows * cell_h + 9), f"{WATERMARK}  |  time-coded evidence sheet", fill=(235, 235, 235), font=font)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, quality=92)
    return sheet.size


def build_evidence(media: Path, manifest: dict[str, Any], scan: dict[str, Any], out: Path, start_shot: int, end_shot: int) -> dict[str, Any]:
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("缺少 ffmpeg；请安装 ffmpeg 或 imageio-ffmpeg。")
    rows = list(scan.get("shot_rows") or [])
    if not rows:
        raise ValueError("quick_scan.json 缺少 shot_rows。")
    selected = [row for row in rows if start_shot <= int(row.get("id", 0)) <= end_shot]
    if not selected:
        raise ValueError("指定范围内没有可提取证据帧的镜头。")

    frame_dir = out / "frames"
    shot_rows = []
    all_frame_records = []
    for row in selected:
        shot_id = int(row["id"])
        start = float(row["start"])
        end = float(row["end"])
        frame_records = []
        for role, seconds in candidate_times(start, end):
            frame_path = frame_dir / f"shot_{shot_id:04d}_{role}.jpg"
            extract_frame(ffmpeg, media, seconds, frame_path)
            width, height = annotate_frame(frame_path, shot_id, role, seconds)
            record = {
                "role": role,
                "time_sec": seconds,
                "timecode": timecode(seconds),
                "path": frame_path.relative_to(out).as_posix(),
                "sha256": sha256_file(frame_path),
                "width": width,
                "height": height,
                "watermark": WATERMARK,
            }
            frame_records.append(record)
            all_frame_records.append({**record, "absolute_path": str(frame_path)})
        shot_rows.append({
            "id": shot_id,
            "start_sec": start,
            "end_sec": end,
            "frames": frame_records,
        })

    sheet_path = out / "evidence_contact_sheet.jpg"
    sheet_size = make_contact_sheet(all_frame_records, sheet_path)
    return {
        "schema_version": "1.0",
        "status": "completed",
        "watermark": {"author": "我密码呢", "mark": "wmmn"},
        "source": {
            "provider": manifest.get("provider"),
            "source_hash": manifest.get("source_hash"),
            "duration_sec": (scan.get("media") or {}).get("duration_sec"),
        },
        "contact_sheet": {
            "path": sheet_path.name,
            "width": sheet_size[0],
            "height": sheet_size[1],
            "sha256": sha256_file(sheet_path),
        },
        "shots": shot_rows,
        "limitations": [
            "证据帧用于追溯镜头观察，不替代完整视频和人工复核。",
            "首帧与尾帧故意内缩少量时间，避免取到相邻镜头。",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-manifest", required=True, type=Path)
    parser.add_argument("--scan-json", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--start-shot", type=int, default=1)
    parser.add_argument("--end-shot", type=int, default=None)
    args = parser.parse_args()
    try:
        media, manifest = resolve_media(args.media_manifest)
        scan = load_json(args.scan_json)
        start_shot = max(1, args.start_shot)
        end_shot = args.end_shot if args.end_shot is not None else start_shot + 4
        args.out.mkdir(parents=True, exist_ok=True)
        payload = build_evidence(media, manifest, scan, args.out, start_shot, end_shot)
        (args.out / "evidence_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        failure = {"status": "blocked", "reason": "evidence_frames_failed", "detail": str(exc)}
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "evidence_manifest.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"status": "completed", "out": str(args.out), "shots": len(payload["shots"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
