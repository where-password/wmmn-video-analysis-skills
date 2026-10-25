#!/usr/bin/env python3
# wmmn / 我密码呢
"""Build a multi-episode, evidence-backed corpus from timestamped transcripts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

from audit_input import collect_files
from build_index import build_chunks, build_sections, coverage_stats
from transcript_io import TranscriptError, format_range, format_time, load_transcript, sha256_text

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcripts", type=Path, required=True, help="Transcript file or directory containing JSON/SRT/VTT files")
    parser.add_argument("--out", type=Path, required=True, help="Collection output directory")
    parser.add_argument("--collection-title", default=None, help="Display title; defaults to the input directory/file name")
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


def natural_sort_key(path: Path) -> list[Any]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.as_posix())]


def episode_title(path: Path) -> str:
    clean = re.sub(r"^\s*\d+\s*[\s._-]+", "", path.stem).strip()
    return clean or path.stem


def build_episode(path: Path, root: Path, ordinal: int, args: argparse.Namespace) -> dict[str, Any]:
    episode_id = f"ep-{ordinal:04d}"
    transcript = load_transcript(path)
    segments = transcript["segments"]
    for segment_ordinal, row in enumerate(segments, 1):
        row["ordinal"] = segment_ordinal
        row["evidence_id"] = f"{episode_id}:ev-{segment_ordinal:06d}"
    chunks = build_chunks(segments, args.target_chunk_sec, args.max_chunk_sec)
    for chunk in chunks:
        chunk["id"] = f"{episode_id}:{chunk['id']}"
        chunk["episode_id"] = episode_id
    sections = build_sections(chunks, [], float(transcript["duration_sec"]), args.section_sec)
    for section in sections:
        section["id"] = f"{episode_id}:{section['id']}"
    section_by_chunk = {
        chunk_id: section["id"]
        for section in sections
        for chunk_id in section["chunk_ids"]
    }
    for chunk in chunks:
        chunk["section_id"] = section_by_chunk.get(chunk["id"])

    relative = path.relative_to(root).as_posix()
    episode = {
        "id": episode_id,
        "ordinal": ordinal,
        "key": path.relative_to(root).with_suffix("").as_posix(),
        "title": episode_title(path),
        "transcript_file": relative,
        "transcript_sha256": transcript["transcript_sha256"],
        "duration_sec": float(transcript["duration_sec"]),
        "language": transcript.get("language"),
        "coverage": coverage_stats(segments, float(transcript["duration_sec"])),
        "counts": {
            "segments": len(segments),
            "chunks": len(chunks),
            "sections": len(sections),
            "characters": sum(len(row["text"]) for row in segments),
        },
        "sections": [
            {
                "id": section["id"],
                "kind": section["kind"],
                "title": section["title"],
                "start_sec": section["start"],
                "end_sec": section["end"],
                "chunk_count": section["chunk_count"],
            }
            for section in sections
        ],
    }
    return {
        "episode": episode,
        "segments": segments,
        "chunks": chunks,
        "sections": sections,
        "transcript": transcript,
    }

def write_database(path: Path, collection_doc: dict[str, Any], built_episodes: list[dict[str, Any]]) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript("""
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE episodes(
            episode_id TEXT PRIMARY KEY,
            ordinal INTEGER NOT NULL,
            episode_key TEXT NOT NULL,
            title TEXT NOT NULL,
            transcript_file TEXT NOT NULL,
            transcript_sha256 TEXT NOT NULL,
            duration_sec REAL NOT NULL,
            segment_count INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL,
            section_count INTEGER NOT NULL
        );
        CREATE TABLE sections(
            section_id TEXT PRIMARY KEY,
            episode_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            start_sec REAL NOT NULL,
            end_sec REAL NOT NULL,
            chunk_ids_json TEXT NOT NULL,
            chunk_count INTEGER NOT NULL
        );
        CREATE TABLE segments(
            evidence_id TEXT PRIMARY KEY,
            episode_id TEXT NOT NULL,
            segment_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            start_sec REAL NOT NULL,
            end_sec REAL NOT NULL,
            speaker TEXT,
            text TEXT NOT NULL,
            quote_sha256 TEXT NOT NULL,
            UNIQUE(episode_id, segment_id)
        );
        CREATE TABLE chunks(
            chunk_id TEXT PRIMARY KEY,
            episode_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            section_id TEXT,
            start_sec REAL NOT NULL,
            end_sec REAL NOT NULL,
            text TEXT NOT NULL,
            text_sha256 TEXT NOT NULL,
            segment_ids_json TEXT NOT NULL,
            evidence_ids_json TEXT NOT NULL
        );
        CREATE INDEX idx_episodes_ordinal ON episodes(ordinal);
        CREATE INDEX idx_segments_episode_time ON segments(episode_id, start_sec, end_sec);
        CREATE INDEX idx_chunks_episode_time ON chunks(episode_id, start_sec, end_sec);
        """)
        connection.executemany(
            "INSERT INTO meta(key, value) VALUES (?, ?)",
            [
                ("collection_id", collection_doc["collection_id"]),
                ("schema_version", collection_doc["schema_version"]),
                ("collection_json", json.dumps(collection_doc, ensure_ascii=False, separators=(",", ":"))),
            ],
        )
        for built in built_episodes:
            episode = built["episode"]
            connection.execute(
                "INSERT INTO episodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    episode["id"], episode["ordinal"], episode["key"], episode["title"],
                    episode["transcript_file"], episode["transcript_sha256"], episode["duration_sec"],
                    episode["counts"]["segments"], episode["counts"]["chunks"], episode["counts"]["sections"],
                ),
            )
            connection.executemany(
                "INSERT INTO sections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        section["id"], episode["id"], section["ordinal"], section["kind"], section["title"],
                        section["start"], section["end"], json.dumps(section["chunk_ids"], ensure_ascii=False),
                        section["chunk_count"],
                    )
                    for section in built["sections"]
                ],
            )
            connection.executemany(
                "INSERT INTO segments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        segment["evidence_id"], episode["id"], segment["id"], segment["ordinal"],
                        segment["start"], segment["end"], segment.get("speaker"), segment["text"],
                        sha256_text(segment["text"]),
                    )
                    for segment in built["segments"]
                ],
            )
            connection.executemany(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        chunk["id"], episode["id"], chunk["ordinal"], chunk.get("section_id"),
                        chunk["start"], chunk["end"], chunk["text"], chunk["text_sha256"],
                        json.dumps(chunk["segment_ids"], ensure_ascii=False),
                        json.dumps(chunk["evidence_ids"], ensure_ascii=False),
                    )
                    for chunk in built["chunks"]
                ],
            )
        connection.commit()
    finally:
        connection.close()


def write_evidence(path: Path, collection_id: str, built_episodes: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for built in built_episodes:
            episode = built["episode"]
            for segment in built["segments"]:
                handle.write(json.dumps({
                    "collection_id": collection_id,
                    "episode_id": episode["id"],
                    "episode_ordinal": episode["ordinal"],
                    "episode_title": episode["title"],
                    "evidence_id": segment["evidence_id"],
                    "segment_id": segment["id"],
                    "ordinal": segment["ordinal"],
                    "start_sec": segment["start"],
                    "end_sec": segment["end"],
                    "speaker": segment.get("speaker"),
                    "quote": segment["text"],
                    "quote_sha256": sha256_text(segment["text"]),
                    "transcript_sha256": episode["transcript_sha256"],
                }, ensure_ascii=False))
                handle.write("\n")

def render_outline(collection_doc: dict[str, Any]) -> str:
    counts = collection_doc["counts"]
    lines = [
        f"# 长视频语料库 · {collection_doc['title']}",
        "",
        "> 这里只提供目录导航。内容检索和回答必须读取 collection.sqlite 中的真实逐字稿片段与证据。",
        "",
        "## 语料规模",
        "",
        f"- 集数：{counts['episodes']}",
        f"- 总时长：{format_time(counts['duration_sec'])}",
        f"- 逐字稿片段：{counts['segments']}",
        f"- 检索块：{counts['chunks']}",
        f"- collection_id：`{collection_doc['collection_id']}`",
        "",
        "## 集数目录",
        "",
        "| 序号 | 标题 | 时长 | 片段 | 检索块 | 语音覆盖 |",
        "| ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for episode in collection_doc["episodes"]:
        lines.append(
            f"| {episode['ordinal']} | {episode['title']} | {format_time(episode['duration_sec'])} | "
            f"{episode['counts']['segments']} | {episode['counts']['chunks']} | "
            f"{episode['coverage']['coverage_ratio'] * 100:.1f}% |"
        )
    lines.extend([
        "",
        "## 使用方式",
        "",
        "```bash",
        "python scripts/query_collection.py --collection <COLLECTION_DIR> --query \"关键词 关键词\" --json",
        "```",
        "",
        "查询结果会返回真实逐字稿块、集数、时间码和证据。没有命中时不要用模型常识补答案。",
        "",
    ])
    return "\n".join(lines)


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    validate_options(args)
    source = args.transcripts.resolve()
    files = collect_files(source)
    if not files:
        raise ValueError("No JSON/SRT/VTT transcript found")
    root = source if source.is_dir() else source.parent
    files.sort(key=natural_sort_key)
    if len(files) > 9999:
        raise ValueError("Collection supports at most 9999 episode files in the current layout")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    output_names = ["collection.json", "collection.sqlite", "evidence.jsonl", "collection_outline.md"]
    existing = [out / name for name in output_names if (out / name).exists()]
    if existing and not args.overwrite:
        raise ValueError("Collection output already exists. Pass --overwrite to replace known collection files.")

    built_episodes = [build_episode(path, root, ordinal, args) for ordinal, path in enumerate(files, 1)]
    fingerprint = hashlib.sha256()
    for built in built_episodes:
        episode = built["episode"]
        fingerprint.update(f"{episode['key']}\0{episode['transcript_sha256']}\0".encode("utf-8"))
    collection_id = "lc-" + fingerprint.hexdigest()[:20]
    title = (args.collection_title or source.stem or "Untitled corpus").strip()
    total_duration = sum(item["episode"]["duration_sec"] for item in built_episodes)
    collection_doc = {
        "schema_version": "1.0",
        "status": "completed",
        "watermark": {"author": "我密码呢", "mark": "wmmn"},
        "collection_id": collection_id,
        "title": title,
        "content_contract": {
            "catalog_is_navigation_only": True,
            "search_unit": "chunk containing exact timestamped transcript text",
            "answer_grounding_required": True,
            "absence_is_not_proof": True,
        },
        "counts": {
            "episodes": len(built_episodes),
            "duration_sec": round(total_duration, 3),
            "segments": sum(item["episode"]["counts"]["segments"] for item in built_episodes),
            "chunks": sum(item["episode"]["counts"]["chunks"] for item in built_episodes),
            "sections": sum(item["episode"]["counts"]["sections"] for item in built_episodes),
            "characters": sum(item["episode"]["counts"]["characters"] for item in built_episodes),
        },
        "parameters": {
            "target_chunk_sec": args.target_chunk_sec,
            "max_chunk_sec": args.max_chunk_sec,
            "section_sec": args.section_sec,
        },
        "episodes": [item["episode"] for item in built_episodes],
        "files": {
            "database": "collection.sqlite",
            "evidence": "evidence.jsonl",
            "outline": "collection_outline.md",
        },
        "limitations": [
            "The catalog is navigation only; answers must read retrieved transcript chunks.",
            "Literal retrieval does not infer synonyms or resolve pronouns.",
            "Transcript gaps and ASR errors limit what can be found.",
            "The collection does not acquire media, run ASR, analyze shots, or produce professional breakdowns.",
        ],
    }

    with tempfile.TemporaryDirectory(prefix=f".{out.name}-build-", dir=out.parent) as staging_raw:
        staging = Path(staging_raw)
        write_database(staging / "collection.sqlite", collection_doc, built_episodes)
        write_json_atomic(staging / "collection.json", collection_doc)
        write_evidence(staging / "evidence.jsonl", collection_id, built_episodes)
        (staging / "collection_outline.md").write_text(render_outline(collection_doc), encoding="utf-8")
        for name in output_names:
            (staging / name).replace(out / name)

    print(json.dumps({
        "status": "completed",
        "out": str(out),
        "collection_id": collection_id,
        "episodes": len(built_episodes),
        "segments": collection_doc["counts"]["segments"],
        "chunks": collection_doc["counts"]["chunks"],
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
            "reason": "invalid_transcript" if isinstance(exc, TranscriptError) else "collection_build_failed",
            "detail": str(exc),
            "next_action": "Provide a directory of timestamped JSON/SRT/VTT transcripts and a writable output directory.",
        }
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
