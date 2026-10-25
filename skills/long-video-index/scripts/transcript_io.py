#!/usr/bin/env python3
# wmmn / 我密码呢
"""Timestamped transcript parsing for long-video indexing. Standard library only."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


class TranscriptError(ValueError):
    """An actionable transcript input error."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_timecode(value: str | float | int) -> float:
    if isinstance(value, (int, float)):
        seconds = float(value)
    else:
        raw = str(value).strip().replace(",", ".")
        if not raw:
            raise TranscriptError("Empty timestamp")
        if re.fullmatch(r"\d+(?:\.\d+)?", raw):
            seconds = float(raw)
        else:
            parts = raw.split(":")
            if len(parts) not in {2, 3}:
                raise TranscriptError(f"Invalid timestamp: {value!r}")
            try:
                tail = float(parts[-1])
                minutes = int(parts[-2])
                hours = int(parts[-3]) if len(parts) == 3 else 0
            except ValueError as exc:
                raise TranscriptError(f"Invalid timestamp: {value!r}") from exc
            seconds = hours * 3600 + minutes * 60 + tail
    if not math.isfinite(seconds) or seconds < 0:
        raise TranscriptError(f"Timestamp must be finite and >= 0: {value!r}")
    return round(seconds, 3)


def format_time(seconds: float | None) -> str:
    total = max(0, int(round(float(seconds or 0))))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_range(start: float, end: float) -> str:
    return f"{format_time(start)}–{format_time(end)}"


def _coerce_segments(data: Any) -> tuple[list[Any], dict[str, Any]]:
    if isinstance(data, list):
        return data, {}
    if not isinstance(data, dict):
        raise TranscriptError("Transcript JSON must be an object or an array")
    for key in ("segments", "transcript", "cues"):
        candidate = data.get(key)
        if isinstance(candidate, list):
            return candidate, data
    raise TranscriptError("Transcript JSON must contain a segments array")


def _normalize_segments(raw_segments: list[Any]) -> list[dict[str, Any]]:
    if not raw_segments:
        raise TranscriptError("Transcript contains no segments")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for ordinal, item in enumerate(raw_segments, 1):
        if not isinstance(item, dict):
            raise TranscriptError(f"Segment {ordinal} must be an object")
        start_value = item.get("start", item.get("start_sec"))
        end_value = item.get("end", item.get("end_sec"))
        if start_value is None or end_value is None:
            raise TranscriptError(f"Segment {ordinal} is missing start/end timestamps")
        start = parse_timecode(start_value)
        end = parse_timecode(end_value)
        if end <= start:
            raise TranscriptError(f"Segment {ordinal} has end <= start ({start} -> {end})")
        text = str(item.get("text") or "").strip()
        if not text:
            raise TranscriptError(f"Segment {ordinal} has empty text")
        raw_id = str(item.get("id") or f"seg-{ordinal:06d}")
        segment_id = raw_id.strip()
        if not segment_id:
            segment_id = f"seg-{ordinal:06d}"
        if segment_id in seen_ids:
            raise TranscriptError(f"Duplicate segment id: {segment_id}")
        seen_ids.add(segment_id)
        segment: dict[str, Any] = {
            "id": segment_id,
            "start": start,
            "end": end,
            "text": text,
        }
        speaker = item.get("speaker", item.get("speaker_id"))
        if speaker is not None and str(speaker).strip():
            segment["speaker"] = str(speaker).strip()
        confidence = item.get("confidence", item.get("confidence_proxy"))
        if isinstance(confidence, (int, float)) and math.isfinite(float(confidence)):
            segment["confidence"] = round(float(confidence), 4)
        normalized.append(segment)
    normalized.sort(key=lambda row: (row["start"], row["end"]))
    for ordinal, row in enumerate(normalized, 1):
        row["ordinal"] = ordinal
    return normalized


def _parse_subtitle(path: Path, suffix: str) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    text = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise TranscriptError("Subtitle file is empty")
    rows: list[dict[str, Any]] = []
    for block in re.split(r"\n{2,}", text):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if suffix == ".vtt" and lines[0].upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), -1)
        if timing_index < 0:
            continue
        timing = lines[timing_index]
        left, right = timing.split("-->", 1)
        end_token = right.strip().split()[0]
        content = "\n".join(lines[timing_index + 1:]).strip()
        if not content:
            continue
        rows.append({"start": left.strip(), "end": end_token, "text": content})
    if not rows:
        raise TranscriptError("No timed subtitle cues found; provide JSON/SRT/VTT with timestamps")
    return _normalize_segments(rows)


def load_transcript(path: Path, fmt: str = "auto") -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise TranscriptError(f"Transcript does not exist: {path}")
    suffix = path.suffix.lower()
    selected = fmt.lower()
    if selected == "auto":
        selected = "json" if suffix == ".json" else "srt" if suffix == ".srt" else "vtt" if suffix == ".vtt" else ""
    if selected not in {"json", "srt", "vtt"}:
        raise TranscriptError("Unsupported transcript format; use JSON, SRT, or VTT")
    metadata: dict[str, Any] = {}
    if selected == "json":
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise TranscriptError(f"Invalid transcript JSON: {exc}") from exc
        raw_segments, metadata = _coerce_segments(data)
        segments = _normalize_segments(raw_segments)
    else:
        segments = _parse_subtitle(path, f".{selected}")
    last_end = max(row["end"] for row in segments)
    duration_value = metadata.get("duration_sec", metadata.get("duration"))
    declared_duration = parse_timecode(duration_value) if duration_value is not None else last_end
    duration_warnings = []
    if declared_duration < last_end:
        duration_warnings.append(
            f"declared transcript duration {declared_duration}s is shorter than last segment end {last_end}s; using {last_end}s"
        )
    duration = max(declared_duration, last_end)
    language = str(metadata.get("language") or "").strip() or None
    return {
        "segments": segments,
        "duration_sec": round(duration, 3),
        "duration_warnings": duration_warnings,
        "language": language,
        "transcript_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "transcript_name": path.name,
    }


def load_chapters(path: Path | None, duration: float) -> list[dict[str, Any]]:
    if path is None:
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise TranscriptError(f"Invalid chapters JSON: {exc}") from exc
    raw = data.get("chapters") if isinstance(data, dict) else data
    if not isinstance(raw, list) or not raw:
        raise TranscriptError("Chapters JSON must contain a non-empty chapters array")
    chapters: list[dict[str, Any]] = []
    for ordinal, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise TranscriptError(f"Chapter {ordinal} must be an object")
        title = str(item.get("title") or "").strip()
        if not title:
            raise TranscriptError(f"Chapter {ordinal} is missing title")
        start = parse_timecode(item.get("start", item.get("start_sec")))
        end_value = item.get("end", item.get("end_sec"))
        end = parse_timecode(end_value) if end_value is not None else duration
        if end <= start:
            raise TranscriptError(f"Chapter {ordinal} has end <= start")
        if end > duration + 0.01:
            raise TranscriptError(f"Chapter {ordinal} ends after transcript duration")
        chapters.append({"title": title, "start": start, "end": end, "ordinal": ordinal})
    chapters.sort(key=lambda row: row["start"])
    for previous, current in zip(chapters, chapters[1:]):
        if current["start"] < previous["end"] - 0.01:
            raise TranscriptError("Chapters overlap; provide non-overlapping ranges")
    return chapters
