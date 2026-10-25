#!/usr/bin/env python3
# wmmn / 我密码呢
"""Build a timestamp index and evidence ledger for an existing long-video transcript."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

from transcript_io import (
    TranscriptError,
    format_range,
    format_time,
    load_chapters,
    load_transcript,
    sha256_text,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", type=Path, required=True, help="Timestamped JSON, SRT, or VTT transcript")
    parser.add_argument("--out", type=Path, required=True, help="Output directory for the index")
    parser.add_argument("--chapters", type=Path, default=None, help="Optional non-overlapping chapter JSON")
    parser.add_argument("--source-title", default=None, help="Display title; defaults to transcript filename")
    parser.add_argument("--source-url", default=None, help="Optional public URL; omit private URLs")
    parser.add_argument("--media-sha256", default=None, help="Optional source media SHA-256")
    parser.add_argument("--language", default=None, help="Optional language code")
    parser.add_argument("--rights", default="unknown", choices=["public", "owned", "authorized", "internal", "unknown"])
    parser.add_argument("--target-chunk-sec", type=float, default=120.0)
    parser.add_argument("--max-chunk-sec", type=float, default=180.0)
    parser.add_argument("--section-sec", type=float, default=600.0)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def validate_options(args: argparse.Namespace) -> None:
    values = {
        "--target-chunk-sec": args.target_chunk_sec,
        "--max-chunk-sec": args.max_chunk_sec,
        "--section-sec": args.section_sec,
    }
    for name, value in values.items():
        if not math.isfinite(float(value)):
            raise TranscriptError(f"{name} must be finite")
    if args.target_chunk_sec <= 0:
        raise TranscriptError("--target-chunk-sec must be > 0")
    if args.max_chunk_sec < args.target_chunk_sec:
        raise TranscriptError("--max-chunk-sec must be >= --target-chunk-sec")
    if args.section_sec <= 0:
        raise TranscriptError("--section-sec must be > 0")


def build_chunks(segments: list[dict[str, Any]], target_sec: float, max_sec: float) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        ordinal = len(chunks) + 1
        evidence_ids = [row["evidence_id"] for row in current]
        chunks.append({
            "id": f"chunk-{ordinal:06d}",
            "ordinal": ordinal,
            "start": current[0]["start"],
            "end": current[-1]["end"],
            "text": " ".join(str(row["text"]).strip() for row in current).strip(),
            "segment_ids": [row["id"] for row in current],
            "evidence_ids": evidence_ids,
        })
        current = []

    for segment in segments:
        if current:
            span = segment["end"] - current[0]["start"]
            gap = segment["start"] - current[-1]["end"]
            if span > max_sec or (gap >= 12.0 and span >= target_sec * 0.4):
                flush()
        current.append(segment)
        if current and current[-1]["end"] - current[0]["start"] >= target_sec:
            flush()
    flush()
    for chunk in chunks:
        chunk["text_sha256"] = sha256_text(chunk["text"])
    return chunks


def build_sections(
    chunks: list[dict[str, Any]],
    chapters: list[dict[str, Any]],
    duration: float,
    section_sec: float,
) -> list[dict[str, Any]]:
    raw_sections: list[dict[str, Any]] = []
    if chapters:
        for chapter in chapters:
            raw_sections.append({
                "kind": "chapter",
                "title": chapter["title"],
                "start": chapter["start"],
                "end": chapter["end"],
            })
    else:
        cursor = 0.0
        ordinal = 1
        while cursor < duration - 0.01:
            end = min(duration, cursor + section_sec)
            raw_sections.append({
                "kind": "time_window",
                "title": f"时间桶 {format_range(cursor, end)}",
                "start": cursor,
                "end": end,
            })
            cursor = end
            ordinal += 1
    sections: list[dict[str, Any]] = []
    for ordinal, section in enumerate(raw_sections, 1):
        ids = [
            chunk["id"] for chunk in chunks
            if chunk["end"] > section["start"] and chunk["start"] < section["end"]
        ]
        sections.append({
            "id": f"section-{ordinal:04d}",
            "ordinal": ordinal,
            "kind": section["kind"],
            "title": section["title"],
            "start": section["start"],
            "end": section["end"],
            "chunk_ids": ids,
            "chunk_count": len(ids),
        })
    return sections


def coverage_stats(segments: list[dict[str, Any]], duration: float) -> dict[str, Any]:
    """Measure the union of timed speech, so overlapping cues are not double-counted."""
    cursor = 0.0
    speech_sec = 0.0
    gaps: list[float] = []
    for row in segments:
        start = max(0.0, min(duration, float(row["start"])))
        end = max(start, min(duration, float(row["end"])))
        if start > cursor:
            gaps.append(start - cursor)
        if end > cursor:
            speech_sec += end - max(start, cursor)
            cursor = end
    if cursor < duration:
        gaps.append(duration - cursor)
    return {
        "first_segment_start_sec": segments[0]["start"],
        "last_segment_end_sec": segments[-1]["end"],
        "speech_sec": round(speech_sec, 3),
        "coverage_ratio": round(min(1.0, speech_sec / duration), 4) if duration else 0.0,
        "largest_gap_sec": round(max(gaps, default=0.0), 3),
        "gaps_over_10s": sum(1 for gap in gaps if gap >= 10.0),
    }


def write_database(
    path: Path,
    index_doc: dict[str, Any],
    segments: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> None:
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    try:
        connection.executescript("""
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE segments(
            evidence_id TEXT PRIMARY KEY,
            segment_id TEXT UNIQUE NOT NULL,
            ordinal INTEGER NOT NULL,
            start_sec REAL NOT NULL,
            end_sec REAL NOT NULL,
            speaker TEXT,
            text TEXT NOT NULL,
            quote_sha256 TEXT NOT NULL
        );
        CREATE INDEX idx_segments_time ON segments(start_sec, end_sec);
        CREATE TABLE chunks(
            chunk_id TEXT PRIMARY KEY,
            ordinal INTEGER NOT NULL,
            start_sec REAL NOT NULL,
            end_sec REAL NOT NULL,
            text TEXT NOT NULL,
            text_sha256 TEXT NOT NULL,
            segment_ids_json TEXT NOT NULL,
            evidence_ids_json TEXT NOT NULL
        );
        CREATE INDEX idx_chunks_time ON chunks(start_sec, end_sec);
        CREATE TABLE sections(
            section_id TEXT PRIMARY KEY,
            ordinal INTEGER NOT NULL,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            start_sec REAL NOT NULL,
            end_sec REAL NOT NULL,
            chunk_ids_json TEXT NOT NULL,
            chunk_count INTEGER NOT NULL
        );
        """)
        connection.executemany(
            "INSERT INTO meta(key, value) VALUES (?, ?)",
            [
                ("index_id", index_doc["index_id"]),
                ("transcript_sha256", index_doc["source"]["transcript_sha256"]),
                ("index_json", json.dumps(index_doc, ensure_ascii=False, separators=(",", ":"))),
            ],
        )
        connection.executemany(
            "INSERT INTO segments VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    row["evidence_id"], row["id"], row["ordinal"], row["start"], row["end"],
                    row.get("speaker"), row["text"], sha256_text(row["text"]),
                )
                for row in segments
            ],
        )
        connection.executemany(
            "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    row["id"], row["ordinal"], row["start"], row["end"], row["text"], row["text_sha256"],
                    json.dumps(row["segment_ids"], ensure_ascii=False),
                    json.dumps(row["evidence_ids"], ensure_ascii=False),
                )
                for row in chunks
            ],
        )
        connection.executemany(
            "INSERT INTO sections VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    row["id"], row["ordinal"], row["kind"], row["title"], row["start"], row["end"],
                    json.dumps(row["chunk_ids"], ensure_ascii=False), row["chunk_count"],
                )
                for row in sections
            ],
        )
        connection.commit()
    finally:
        connection.close()


def render_outline(index_doc: dict[str, Any]) -> str:
    source = index_doc["source"]
    counts = index_doc["counts"]
    coverage = index_doc["coverage"]
    lines = [
        f"# 长视频索引 · {source['title']}",
        "",
        "> 这是定位索引，不是内容摘要或专业拆解。每条引用都保留时间码、原文和哈希。",
        "",
        "## 索引概况",
        "",
        f"- 时长：{format_time(index_doc['duration_sec'])}",
        f"- 逐字稿：{counts['segments']} 段 / {counts['chunks']} 个检索块",
        f"- 章节：{counts['sections']} 个（{'人工/上游提供' if counts['chapters'] else '按时间桶生成'}）",
        f"- 语音覆盖：{coverage['coverage_ratio'] * 100:.1f}%",
        f"- 最大空白：{coverage['largest_gap_sec']:.1f} 秒",
        f"- index_id：`{index_doc['index_id']}`",
        "",
        "## 时间地图",
        "",
        "| 时间范围 | 类型 | 标题 | 检索块 |",
        "| --- | --- | --- | ---: |",
    ]
    for section in index_doc["sections"]:
        lines.append(
            f"| {format_range(section['start_sec'], section['end_sec'])} | {section['kind']} | "
            f"{section['title']} | {section['chunk_count']} |"
        )
    lines.extend([
        "",
        "## 定位方式",
        "",
        "```bash",
        "python scripts/locate.py --index <INDEX_DIR> --query \"关键词 关键词\"",
        "```",
        "",
        "定位结果只说明“这些片段出现了相关词句”，不自动证明观点成立。需要结论时，应先阅读引用片段，再区分转述、推断和事实。",
        "",
    ])
    return "\n".join(lines)


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_evidence_jsonl(path: Path, segments: list[dict[str, Any]], transcript_sha256: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in segments:
            handle.write(json.dumps({
                "evidence_id": row["evidence_id"],
                "segment_id": row["id"],
                "ordinal": row["ordinal"],
                "start_sec": row["start"],
                "end_sec": row["end"],
                "speaker": row.get("speaker"),
                "quote": row["text"],
                "quote_sha256": sha256_text(row["text"]),
                "transcript_sha256": transcript_sha256,
            }, ensure_ascii=False))
            handle.write("\n")


def main() -> int:
    args = parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    output_names = [
        "long_video_index.json",
        "long_video_index.sqlite",
        "evidence.jsonl",
        "index_outline.md",
    ]
    existing = [out / name for name in output_names if (out / name).exists()]
    if existing and not args.overwrite:
        raise ValueError("Index output already exists. Pass --overwrite to replace the known index files.")

    # Validate and build in a sibling staging directory. An invalid rebuild must not
    # delete or partially replace an existing valid index.
    validate_options(args)
    transcript = load_transcript(args.transcript)
    segments = transcript["segments"]
    duration = float(transcript["duration_sec"])
    duration_warnings = list(transcript.get("duration_warnings") or [])
    chapters = load_chapters(args.chapters, duration)
    for ordinal, row in enumerate(segments, 1):
        row["evidence_id"] = f"ev-{ordinal:06d}"
    chunks = build_chunks(segments, args.target_chunk_sec, args.max_chunk_sec)
    sections = build_sections(chunks, chapters, duration, args.section_sec)
    coverage = coverage_stats(segments, duration)
    fingerprint = hashlib.sha256()
    fingerprint.update(transcript["transcript_sha256"].encode("ascii"))
    for row in segments:
        fingerprint.update(f"{row['start']:.3f}|{row['end']:.3f}|{sha256_text(row['text'])}\n".encode("ascii"))
    index_id = "lv-" + fingerprint.hexdigest()[:20]
    title = (args.source_title or transcript.get("transcript_name") or "Untitled long video").strip()
    language = (args.language or transcript.get("language") or "").strip() or None
    index_doc = {
        "schema_version": "1.0",
        "status": "completed",
        "watermark": {"author": "我密码呢", "mark": "wmmn"},
        "index_id": index_id,
        "source": {
            "title": title,
            "url": args.source_url,
            "transcript_file": transcript["transcript_name"],
            "transcript_sha256": transcript["transcript_sha256"],
            "media_sha256": args.media_sha256,
            "language": language,
            "rights": args.rights,
        },
        "duration_sec": duration,
        "counts": {
            "segments": len(segments),
            "chunks": len(chunks),
            "sections": len(sections),
            "chapters": len(chapters),
            "characters": sum(len(row["text"]) for row in segments),
        },
        "coverage": coverage,
        "parameters": {
            "target_chunk_sec": args.target_chunk_sec,
            "max_chunk_sec": args.max_chunk_sec,
            "section_sec": args.section_sec,
        },
        "sections": [
            {
                "id": row["id"],
                "kind": row["kind"],
                "title": row["title"],
                "start_sec": row["start"],
                "end_sec": row["end"],
                "chunk_count": row["chunk_count"],
            }
            for row in sections
        ],
        "files": {
            "database": "long_video_index.sqlite",
            "evidence": "evidence.jsonl",
            "outline": "index_outline.md",
        },
        "limitations": [
            *duration_warnings,
            "The index only covers the supplied transcript; gaps in the transcript are not analyzed.",
            "Search results identify timestamped wording, not verified claims, intent, or content quality.",
            "This Skill does not transcribe media, acquire video, inspect shots, or produce professional production plans.",
        ],
    }

    with tempfile.TemporaryDirectory(prefix=f".{out.name}-build-", dir=out.parent) as staging_raw:
        staging = Path(staging_raw)
        write_database(staging / "long_video_index.sqlite", index_doc, segments, chunks, sections)
        write_json_atomic(staging / "long_video_index.json", index_doc)
        write_evidence_jsonl(staging / "evidence.jsonl", segments, transcript["transcript_sha256"])
        (staging / "index_outline.md").write_text(render_outline(index_doc), encoding="utf-8")
        for name in output_names:
            (staging / name).replace(out / name)

    print(json.dumps({
        "status": "completed",
        "out": str(out),
        "index_id": index_id,
        "segments": len(segments),
        "chunks": len(chunks),
        "sections": len(sections),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except (TranscriptError, ValueError, OSError, sqlite3.Error) as exc:
        failure = {
            "status": "blocked",
            "reason": "invalid_transcript" if isinstance(exc, TranscriptError) else "index_build_failed",
            "detail": str(exc),
            "next_action": "Provide a timestamped JSON/SRT/VTT transcript and a writable output directory.",
        }
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
