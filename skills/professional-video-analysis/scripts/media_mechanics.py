#!/usr/bin/env python3
# wmmn / 我密码呢
"""Measure visual camera motion and incoming transition signatures from a host-provided media file."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def get_ffmpeg() -> str | None:
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def resolve_media(manifest_path: Path) -> tuple[Path, dict[str, Any]]:
    manifest = load_json(manifest_path)
    raw = Path(str(manifest.get("media_path") or ""))
    media = raw if raw.is_absolute() else (manifest_path.parent / raw)
    if not media.exists():
        raise FileNotFoundError(f"媒体句柄中的 media_path 不存在：{media}")
    return media, manifest


def read_gray_frames(ffmpeg: str, media: Path, start: float, duration: float, fps: float, size: int) -> np.ndarray:
    vf = (
        f"fps={fps:.3f},"
        f"scale={size}:{size}:force_original_aspect_ratio=decrease,"
        f"pad={size}:{size}:(ow-iw)/2:(oh-ih)/2,format=gray"
    )
    proc = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{max(0.0, start):.3f}",
            "-i",
            str(media),
            "-t",
            f"{max(0.001, duration):.3f}",
            "-vf",
            vf,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        capture_output=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"ffmpeg 取帧失败：{detail or proc.returncode}")
    frame_size = size * size
    count = len(proc.stdout) // frame_size
    if count <= 0:
        return np.empty((0, size, size), dtype=np.float32)
    data = np.frombuffer(proc.stdout[: count * frame_size], dtype=np.uint8)
    return data.reshape(count, size, size).astype(np.float32)


def _window(shape: tuple[int, int]) -> np.ndarray:
    h, w = shape
    return np.outer(np.hanning(h), np.hanning(w)).astype(np.float32)


def phase_shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    """Return (dx, dy, confidence) for motion from a to b using phase correlation."""
    h, w = a.shape
    win = _window((h, w))
    aa = (a - float(a.mean())) * win
    bb = (b - float(b.mean())) * win
    spectrum = np.fft.fft2(bb) * np.conj(np.fft.fft2(aa))
    correlation = np.abs(np.fft.ifft2(spectrum / (np.abs(spectrum) + 1e-8)))
    peak_y, peak_x = np.unravel_index(int(np.argmax(correlation)), correlation.shape)
    dx = float(peak_x if peak_x <= w // 2 else peak_x - w)
    dy = float(peak_y if peak_y <= h // 2 else peak_y - h)
    peak = float(correlation[peak_y, peak_x])
    baseline = float(correlation.mean() + correlation.std() + 1e-8)
    confidence = max(0.0, min(1.0, (peak - correlation.mean()) / baseline))
    return dx, dy, confidence


def _crop(frame: np.ndarray, ratio: float = 0.18) -> np.ndarray:
    h, w = frame.shape
    dy = int(h * ratio)
    dx = int(w * ratio)
    return frame[dy:h - dy, dx:w - dx]


def scale_match(a: np.ndarray, b: np.ndarray, dx: float, dy: float) -> tuple[float, float]:
    """Estimate apparent scale of b relative to a after removing measured translation."""
    shift_x = int(round(dx))
    shift_y = int(round(dy))
    shifted_b = np.roll(b, shift=(shift_y, shift_x), axis=(0, 1))
    base = _crop(a)
    target = _crop(shifted_b)
    if base.size == 0 or target.size == 0:
        return 1.0, 0.0
    source = Image.fromarray(np.clip(target, 0, 255).astype(np.uint8))
    base_flat = base.astype(np.float32).ravel()
    base_flat = base_flat - base_flat.mean()
    best_scale = 1.0
    best_score = -2.0
    for scale in (0.94, 0.96, 0.98, 1.0, 1.02, 1.04, 1.06):
        resized = source.resize((max(1, int(source.width * scale)), max(1, int(source.height * scale))), Image.Resampling.BILINEAR)
        left = max(0, (resized.width - base.shape[1]) // 2)
        top = max(0, (resized.height - base.shape[0]) // 2)
        arr = np.asarray(resized, dtype=np.float32)[top:top + base.shape[0], left:left + base.shape[1]]
        if arr.shape != base.shape:
            continue
        flat = arr.ravel()
        flat = flat - flat.mean()
        denom = float(np.linalg.norm(base_flat) * np.linalg.norm(flat) + 1e-8)
        score = float(np.dot(base_flat, flat) / denom)
        if score > best_score:
            best_score = score
            best_scale = scale
    return best_scale, max(0.0, best_score)


def analyze_motion(frames: np.ndarray, fps: float, start_sec: float) -> dict[str, Any]:
    if len(frames) < 3:
        return {
            "type": "insufficient_frames",
            "label": "可测帧不足，无法判断运镜",
            "confidence": 0.0,
            "direction": None,
            "median_shift_px": None,
            "scale_ratio": None,
            "first_motion_sec": None,
            "evidence": "measured_visual_motion",
        }

    shifts: list[tuple[float, float, float]] = []
    scales: list[tuple[float, float]] = []
    for index in range(1, len(frames)):
        dx, dy, confidence = phase_shift(frames[index - 1], frames[index])
        scale, score = scale_match(frames[index - 1], frames[index], dx, dy)
        shifts.append((dx, dy, confidence))
        scales.append((scale, score))

    dx_values = np.array([item[0] for item in shifts], dtype=np.float32)
    dy_values = np.array([item[1] for item in shifts], dtype=np.float32)
    conf_values = np.array([item[2] for item in shifts], dtype=np.float32)
    scale_values = np.array([item[0] for item in scales], dtype=np.float32)
    scale_scores = np.array([item[1] for item in scales], dtype=np.float32)

    dx = float(np.median(dx_values))
    dy = float(np.median(dy_values))
    magnitude = math.hypot(dx, dy)
    consistency = float(np.mean(np.sign(dx_values) == np.sign(dx))) if abs(dx) > 1 else 0.5
    scale = float(np.median(scale_values))
    scale_consistency = float(np.mean(np.abs(scale_values - 1.0) > 0.012))
    base_confidence = float(np.median(conf_values))
    direction = "right" if dx > 0 else "left" if dx < 0 else None

    if abs(scale - 1.0) >= 0.025 and scale_consistency >= 0.55 and float(np.median(scale_scores)) >= 0.45:
        if scale < 1.0:
            motion_type, label = "apparent_zoom_in", "画面前景扩张，疑似推近（不能区分变焦与物理推进）"
        else:
            motion_type, label = "apparent_zoom_out", "画面收缩，疑似拉远（不能区分变焦与物理后退）"
        confidence = min(0.9, 0.45 + abs(scale - 1.0) * 4 + base_confidence * 0.2)
    elif magnitude < 0.65:
        motion_type, label = "static", "画面基本固定"
        confidence = min(0.95, 0.55 + base_confidence * 0.4)
    elif magnitude >= 0.9 and consistency >= 0.52:
        direction_label = "向右" if dx > 0 else "向左"
        if abs(dx) >= abs(dy) * 1.35:
            motion_type, label = "horizontal", f"画面整体{direction_label}平移（疑似横摇或横移）"
        elif abs(dy) >= abs(dx) * 1.35:
            vertical = "向下" if dy > 0 else "向上"
            motion_type, label = "vertical", f"画面整体{vertical}平移（疑似俯仰或升降）"
        else:
            motion_type, label = "diagonal", f"画面整体斜向平移（{direction_label}且上下移动）"
        confidence = min(0.9, 0.4 + min(magnitude, 8.0) / 20 + consistency * 0.2)
    else:
        motion_type, label = "complex", "画面存在运动，但方向不稳定，疑似手持、主体运动或混合运镜"
        confidence = min(0.7, 0.35 + base_confidence * 0.25)

    first_motion_sec = None
    if motion_type != "static":
        for index, (item_dx, item_dy, item_conf) in enumerate(shifts, 1):
            if math.hypot(item_dx, item_dy) >= 0.8 and item_conf >= 0.15:
                first_motion_sec = round(start_sec + index / fps, 3)
                break

    return {
        "type": motion_type,
        "label": label,
        "confidence": round(confidence, 3),
        "direction": direction,
        "median_shift_px": round(magnitude, 3),
        "scale_ratio": round(scale, 4),
        "first_motion_sec": first_motion_sec,
        "evidence": "measured_visual_motion",
    }


def _frame_difference(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a - b)) / 255.0)


def _half_difference(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    width = a.shape[1]
    left = _frame_difference(a[:, : width // 2], b[:, : width // 2])
    right = _frame_difference(a[:, width // 2 :], b[:, width // 2 :])
    return left, right


def classify_transition(frames: np.ndarray, boundary_rel_sec: float, fps: float) -> dict[str, Any]:
    if len(frames) < 4:
        return {"type": "unknown", "label": "可测帧不足，转场类型未确认", "confidence": 0.0, "evidence": "measured_visual_transition"}
    diffs = np.array([_frame_difference(frames[i - 1], frames[i]) for i in range(1, len(frames))], dtype=np.float32)
    brightness = np.array([float(frame.mean() / 255.0) for frame in frames], dtype=np.float32)
    center = int(round(boundary_rel_sec * fps))
    center = max(1, min(center, len(diffs) - 1))
    peak_index = int(np.argmax(diffs))
    peak = float(diffs[peak_index])
    ordered = np.sort(diffs)
    second_peak = float(ordered[-2]) if len(ordered) > 1 else 0.0
    abruptness = peak / (second_peak + 1e-6)
    local_floor = float(np.median(np.delete(diffs, peak_index))) if len(diffs) > 1 else 0.0
    contrast = peak / (local_floor + 1e-6)
    near_boundary = abs(peak_index - center) <= max(3, int(round(0.45 * fps)))

    left_right = [_half_difference(frames[i - 1], frames[i]) for i in range(1, len(frames))]
    half_gap = max(abs(left - right) for left, right in left_right) if left_right else 0.0

    if float(brightness.max()) > 0.96 and float(brightness.max() - np.median(brightness)) > 0.28:
        return {"type": "flash", "label": "闪白/闪光转场", "confidence": 0.78, "evidence": "measured_visual_transition"}
    if float(brightness.min()) < 0.06 and float(np.percentile(brightness, 85)) > 0.28:
        return {"type": "fade_through_black", "label": "经黑场淡入淡出", "confidence": 0.72, "evidence": "measured_visual_transition"}
    if near_boundary and peak >= 0.045 and (contrast >= 2.0 or (peak >= 0.16 and abruptness >= 1.45)):
        confidence = min(0.96, 0.55 + peak * 1.4 + min(abruptness, 3.0) * 0.08)
        return {"type": "hard_cut", "label": "硬切", "confidence": round(confidence, 3), "evidence": "measured_visual_transition"}
    if near_boundary and half_gap >= 0.055 and peak < 0.28:
        return {"type": "wipe_candidate", "label": "疑似划像/分区转场", "confidence": 0.5, "evidence": "measured_visual_transition"}
    gradual = diffs[max(0, center - 4) : min(len(diffs), center + 4)]
    if len(gradual) >= 3 and float(np.mean(gradual >= 0.025)) >= 0.65 and peak < 0.28:
        return {"type": "dissolve_candidate", "label": "疑似叠化/溶解", "confidence": 0.48, "evidence": "measured_visual_transition"}
    return {"type": "unknown", "label": "检测到切点，但转场类型未确认", "confidence": 0.25, "evidence": "measured_visual_transition"}


def build_mechanics(media: Path, manifest: dict[str, Any], scan: dict[str, Any], start_shot: int, end_shot: int | None, fps: float, size: int) -> dict[str, Any]:
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("缺少 ffmpeg；请安装 ffmpeg 或 imageio-ffmpeg。")
    rows = list(scan.get("shot_rows") or [])
    if not rows:
        raise ValueError("quick_scan.json 缺少 shot_rows，请先用新版 general-video-analysis 重新扫描。")
    selected = [row for row in rows if int(row.get("id", 0)) >= start_shot and (end_shot is None or int(row.get("id", 0)) <= end_shot)]
    if not selected:
        raise ValueError("指定镜头范围内没有可分析镜头。")

    shots = []
    first_transition = None
    first_camera_movement = None
    for row in selected:
        shot_id = int(row["id"])
        start = float(row["start"])
        end = float(row["end"])
        duration = max(0.001, end - start)
        motion_frames = read_gray_frames(ffmpeg, media, start, duration, fps, size)
        camera = analyze_motion(motion_frames, fps, start)

        if shot_id == 1:
            transition = {
                "time_sec": start,
                "type": "opening",
                "label": "开场（无前序转场）",
                "confidence": 1.0,
                "evidence": "structural",
            }
        else:
            window = 1.2
            win_start = max(0.0, start - window / 2)
            transition_frames = read_gray_frames(ffmpeg, media, win_start, window, max(fps * 2, 8), size)
            transition = classify_transition(transition_frames, start - win_start, max(fps * 2, 8))
            transition = {"time_sec": round(start, 3), **transition}

        if first_transition is None and transition["type"] != "opening":
            first_transition = dict(transition)
        if first_camera_movement is None and camera["type"] not in {"static", "insufficient_frames"} and float(camera["confidence"]) >= 0.45:
            first_camera_movement = {
                "shot_id": shot_id,
                "time_sec": camera.get("first_motion_sec") or round(start, 3),
                "type": camera["type"],
                "label": camera["label"],
                "confidence": camera["confidence"],
            }
        shots.append({"id": shot_id, "start_sec": start, "end_sec": end, "camera": camera, "transition_in": transition})

    return {
        "schema_version": "1.0",
        "status": "completed",
        "watermark": {"author": "我密码呢", "mark": "wmmn"},
        "source": {
            "provider": manifest.get("provider"),
            "source_hash": manifest.get("source_hash"),
            "duration_sec": (scan.get("media") or {}).get("duration_sec"),
        },
        "method": {
            "name": "phase_correlation_and_transition_signatures",
            "sampling_fps": fps,
            "frame_size_px": size,
            "claims": "visual motion and transition signatures, not physical rig metadata",
        },
        "shots": shots,
        "first_transition": first_transition,
        "first_camera_movement": first_camera_movement,
        "limitations": [
            "二维画面不能可靠区分物理推轨、变焦、升降与主体运动。",
            "溶片、划像和复杂合成转场只能给候选类型与置信度。",
            "低纹理、强运动模糊和强主体运动会降低运镜判断置信度。",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-manifest", required=True, type=Path)
    parser.add_argument("--scan-json", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="Output JSON path")
    parser.add_argument("--start-shot", type=int, default=1)
    parser.add_argument("--end-shot", type=int, default=None)
    parser.add_argument("--fps", type=float, default=4.0)
    parser.add_argument("--size", type=int, default=192)
    args = parser.parse_args()
    try:
        media, manifest = resolve_media(args.media_manifest)
        scan = load_json(args.scan_json)
        start_shot = max(1, args.start_shot)
        end_shot = args.end_shot if args.end_shot is not None else start_shot + 4
        payload = build_mechanics(media, manifest, scan, start_shot, end_shot, max(2.0, args.fps), max(96, args.size))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        failure = {"status": "blocked", "reason": "mechanics_analysis_failed", "detail": str(exc)}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"status": "completed", "out": str(args.out), "shots": len(payload["shots"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
