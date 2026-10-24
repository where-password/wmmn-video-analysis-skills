#!/usr/bin/env python3
# wmmn / 我密码呢
"""Fast, host-invoked video structure scan. No professional critique."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from media_utils import get_ffmpeg, probe_media, relative_posix, sha256_file, write_json
from visual import detect_cuts, extract_frame


def parse_window(value: str | None) -> tuple[float, float] | None:
    if value is None:
        return None
    parts = value.split(":", 1)
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("--window must be START:DURATION")
    start, duration = float(parts[0]), float(parts[1])
    if start < 0 or duration <= 0:
        raise argparse.ArgumentTypeError("--window requires start >= 0 and duration > 0")
    return start, duration


def normalize_source_url(source: str) -> str:
    """Keep acquisition platform-agnostic; the host/yt-dlp owns URL quirks."""
    return source


def find_media(media_dir: Path) -> Path:
    manifest_path = media_dir / "download_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = [media_dir / name for name in manifest.get("files", []) if (media_dir / name).is_file()]
        if len(files) == 1:
            return files[0]
        if not files:
            raise RuntimeError("download_manifest.json exists but no media file was found")
        raise RuntimeError(f"Expected one media file, found {len(files)}; refusing to guess")
    media = [path for path in media_dir.iterdir() if path.is_file() and path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".flv"}]
    if len(media) == 1:
        return media[0]
    raise RuntimeError("Could not determine a single downloaded media file")


def load_media_manifest(path: Path) -> tuple[Path, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    media_path = Path(str(data.get("media_path") or "")).expanduser()
    if not media_path.is_absolute():
        media_path = (path.parent / media_path).resolve()
    if not media_path.exists():
        raise FileNotFoundError(f"media_path from manifest does not exist: {media_path}")
    return media_path, "host_media_manifest"


def resolve_source(source: str, out: Path) -> tuple[Path, str]:
    local = Path(source).expanduser()
    if local.exists():
        return local.resolve(), "host_media_handle"
    if not source.lower().startswith(("http://", "https://")):
        raise FileNotFoundError(f"Source is neither a local file nor an HTTP(S) URL: {source}")
    normalized = normalize_source_url(source)
    media_dir = out / "media" / "public"
    media_dir.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(Path(__file__).with_name("download.py")), "--url", normalized, "--out", str(media_dir), "--no-playlist"]
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError("URL media unavailable: " + (proc.stderr or proc.stdout).strip())
    return find_media(media_dir), "public_url"


def make_contact_sheet(ffmpeg: str, media: Path, out: Path, start: float, duration: float, count: int = 8) -> str | None:
    from PIL import Image, ImageDraw, ImageFont

    frame_dir = out / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for index in range(count):
        time_sec = start + duration * (index + 0.5) / count
        frame_path = frame_dir / f"sample_{index + 1:02d}.jpg"
        if extract_frame(ffmpeg, media, time_sec, frame_path):
            rows.append((time_sec, frame_path))
    if not rows:
        return None
    thumb_w, thumb_h = 320, 180
    label_h = 26
    columns = 4
    sheet_rows = (len(rows) + columns - 1) // columns
    footer_h = 28
    sheet = Image.new("RGB", (columns * thumb_w, sheet_rows * (thumb_h + label_h) + footer_h), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    watermark_font = None
    font_candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/simhei.ttf",
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ]
    for font_path in font_candidates:
        if font_path.exists():
            try:
                watermark_font = ImageFont.truetype(str(font_path), 14)
                break
            except Exception:
                pass
    for index, (time_sec, path) in enumerate(rows):
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            x = (index % columns) * thumb_w
            y = (index // columns) * (thumb_h + label_h)
            sheet.paste(image, (x, y))
            draw.text((x + 8, y + thumb_h + 5), f"{int(time_sec // 60):02d}:{time_sec % 60:05.2f}", fill=(255, 255, 255))
    watermark_text = "wmmn · 我密码呢" if watermark_font else "wmmn"
    draw.text((10, sheet.height - footer_h + 6), watermark_text, fill=(220, 220, 220), font=watermark_font)
    result = out / "quick_contact_sheet.jpg"
    sheet.save(result, quality=88)
    return relative_posix(result, out)


def classify(duration: float, shots: int, cuts: int) -> dict[str, Any]:
    cuts_per_minute = cuts * 60.0 / duration if duration else 0.0
    seconds = int(round(duration))
    if shots <= 1:
        return {
            "status": "not_applicable_for_professional_analysis",
            "label": "single_shot",
            "headline": f"这是一条约 {seconds} 秒的固定机位、单镜头内容，镜头语言信息很少。",
            "reason": "single_shot_or_no_detected_cut",
            "recommendation": None,
        }
    if duration > 1800:
        return {
            "status": "long_video_candidate",
            "label": "long_video",
            "headline": f"这是一条超过 {seconds // 60} 分钟的长视频，适合先做索引和定位，不适合直接逐镜深拆。",
            "reason": "duration_over_30_minutes",
            "recommendation": {
                "skill": "long-video-index",
                "why": "这类长视频更适合先做逐字稿索引、主题定位和快速筛查。",
                "limits": ["本次快速扫描不建立语料库，也不做长视频检索。"],
            },
        }
    if cuts_per_minute >= 20.0:
        label = "fast_cut"
        headline = f"这是一条约 {seconds} 秒的高密度快剪/混剪视频，核心靠连续切镜和画面变化推进。"
    elif cuts_per_minute >= 6.0:
        label = "edited_video"
        headline = f"这是一条约 {seconds} 秒的多镜头剪辑视频，节奏偏快。"
    else:
        label = "multi_shot"
        headline = f"这是一条约 {seconds} 秒的多镜头视频，剪辑节奏相对平稳。"
    professional = shots >= 4 or cuts_per_minute >= 6.0
    return {
        "status": "professional_candidate" if professional else "general_only",
        "label": label,
        "headline": headline,
        "reason": "multiple_shot_structure",
        "recommendation": {
            "skill": "professional-video-analysis",
            "why": "有明确的多镜头和可测剪辑结构，适合继续拆镜头、节奏、运镜和复刻方案。",
            "limits": [
                "专业 Skill 只覆盖可测量的制作结构。",
                "它不能复刻幽默、网感、个人风格，也不能保证传播效果。",
            ],
        } if professional else None,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    structure = payload["structure"]
    applicability = payload["applicability"]
    recommendation = applicability.get("recommendation")
    lines = [
        "# 视频判断",
        "",
        applicability.get("headline", "这是一条结构信息不足的视频。"),
        "",
        "## 结构判断",
        "",
        f"检测到约 {structure.get('shots')} 个镜头、{structure.get('cuts')} 个切点，平均 {structure.get('median_shot_sec')} 秒一个镜头。",
        "具体题材（整活、风景、音乐等）不能只靠镜头结构可靠确认；如果宿主有标题、字幕或内容说明，可以再补充。",
        "",
        "## 适不适合专业拆解",
        "",
    ]
    if recommendation:
        lines.extend([
            f"适合继续做专业拆解，推荐 `{recommendation['skill']}`。",
            f"原因：{recommendation['why']}",
        ])
    else:
        lines.append("不建议继续做镜头语言专业拆解；当前结构信号不足，或更适合文本/内容整理流程。")
    lines.extend([
        "",
        "## 不能保证",
        "",
        "不能判断为什么好看、为什么好笑、是否有网感、能否传播，也不能复刻创作者的个人风格。",
    ])
    if recommendation:
        lines.extend(["", "## 限制", ""])
        lines.extend(f"- {item}" for item in recommendation.get("limits", []))
    lines.extend(["", "---", "> wmmn · 我密码呢"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=None, help="Local media path or URL")
    parser.add_argument("--media-manifest", type=Path, default=None, help="Host-provided media_handle JSON; preferred when a browser/viewer acquired the media")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--window", type=parse_window, default=None)
    parser.add_argument("--max-analysis-sec", type=float, default=120.0)
    parser.add_argument("--scene-threshold", type=float, default=0.35)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    timings: dict[str, float] = {}
    try:
        ffmpeg = get_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("ffmpeg is required")
        if not args.source and not args.media_manifest:
            raise RuntimeError("Provide --source or --media-manifest")
        stage = time.perf_counter()
        if args.media_manifest:
            media, acquisition_mode = load_media_manifest(args.media_manifest)
        else:
            media, acquisition_mode = resolve_source(str(args.source), out)
        timings["acquire_sec"] = round(time.perf_counter() - stage, 3)
        stage = time.perf_counter()
        info = probe_media(media)
        timings["probe_sec"] = round(time.perf_counter() - stage, 3)
        full_duration = float(info.get("duration_sec") or 0.0)
        if full_duration <= 0:
            raise RuntimeError("Cannot read media duration")
        window = args.window
        sampled = False
        if window is None:
            if full_duration > 1800:
                start, duration = 0.0, min(30.0, full_duration)
                sampled = True
            elif full_duration > args.max_analysis_sec:
                start, duration = 0.0, args.max_analysis_sec
                sampled = True
            else:
                start, duration = 0.0, full_duration
        else:
            start, duration = window
            start = max(0.0, min(start, full_duration))
            duration = max(0.001, min(duration, full_duration - start))
        stage = time.perf_counter()
        cuts = detect_cuts(ffmpeg, media, start, duration, args.scene_threshold)
        timings["detect_cuts_sec"] = round(time.perf_counter() - stage, 3)
        shots = len(cuts) + 1
        boundaries = [0.0] + [cut - start for cut in cuts] + [duration]
        shot_lengths = [boundaries[i + 1] - boundaries[i] for i in range(len(boundaries) - 1)]
        absolute_boundaries = [start] + cuts + [start + duration]
        shot_rows = [
            {
                "id": index + 1,
                "start": round(absolute_boundaries[index], 3),
                "end": round(absolute_boundaries[index + 1], 3),
                "duration": round(absolute_boundaries[index + 1] - absolute_boundaries[index], 3),
            }
            for index in range(len(absolute_boundaries) - 1)
            if absolute_boundaries[index + 1] - absolute_boundaries[index] >= 0.04
        ]
        structure = {
            "window_start_sec": round(start, 3),
            "window_end_sec": round(start + duration, 3),
            "window_duration_sec": round(duration, 3),
            "sampled": sampled,
            "shots": shots,
            "cuts": len(cuts),
            "cuts_per_minute": round(len(cuts) * 60.0 / duration, 2) if duration else 0.0,
            "median_shot_sec": round(sorted(shot_lengths)[len(shot_lengths) // 2], 3) if shot_lengths else None,
        }
        applicability = classify(duration, shots, len(cuts))
        stage = time.perf_counter()
        contact = make_contact_sheet(ffmpeg, media, out, start, duration)
        timings["contact_sheet_sec"] = round(time.perf_counter() - stage, 3)
        stage = time.perf_counter()
        media_sha256 = sha256_file(media)
        timings["hash_sec"] = round(time.perf_counter() - stage, 3)
        timings["total_sec"] = round(time.perf_counter() - started, 3)
        payload = {
            "schema_version": "1.0",
            "status": "completed",
            "watermark": {"author": "我密码呢", "mark": "wmmn"},
            "source": "<source>",
            "acquisition": {"mode": acquisition_mode, "media_sha256": media_sha256},
            "media": {"duration_sec": round(full_duration, 3), "width": info.get("width"), "height": info.get("height"), "fps": info.get("fps")},
            "structure": structure,

            "shot_rows": shot_rows,
            "applicability": applicability,
            "artifacts": {"contact_sheet": contact, "frames_dir": relative_posix(out / "frames", out) if (out / "frames").exists() else None},
            "timings_sec": timings,
            "limitations": [
                "This is a structural scan only; it does not judge content, humor, narrative, aesthetics, or audience response.",
                "Cut detection is threshold-based and may miss soft transitions or very short flashes.",
                "No transcript, BPM, OCR, camera-motion, or continuity analysis is included.",
            ],
        }
        write_json(out / "quick_scan.json", payload)
        (out / "quick_scan.md").write_text(render_markdown(payload), encoding="utf-8")
        print(json.dumps({"status": "completed", "out": str(out), "applicability": applicability["status"], "timings_sec": timings}, ensure_ascii=False))
        print()
        print((out / "quick_scan.md").read_text(encoding="utf-8"))
        return 0
    except Exception as exc:
        failure = {"status": "blocked", "reason": "scan_failed", "detail": str(exc)}
        write_json(out / "quick_scan.json", failure)
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())














