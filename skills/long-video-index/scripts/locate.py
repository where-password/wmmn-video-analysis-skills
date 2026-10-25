#!/usr/bin/env python3
# wmmn / 我密码呢
"""Locate timestamped transcript evidence in a long-video index."""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from feedback_notice import append_notice, take_first_run_notice
from transcript_io import format_range, sha256_text


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True, help="Directory created by build_index.py")
    parser.add_argument("--query", required=True, help="Literal keywords; separate independent terms with spaces")
    parser.add_argument("--start", type=float, default=None, help="Optional source-absolute start time")
    parser.add_argument("--end", type=float, default=None, help="Optional source-absolute end time")
    parser.add_argument("--limit", type=int, default=5, help="Maximum candidate chunks")
    parser.add_argument("--evidence-per-hit", type=int, default=3, help="Maximum exact quotes per candidate")
    parser.add_argument("--out", type=Path, default=None, help="Optional directory for locate_result.json/.md")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--first-run", choices=["auto", "always", "never"], default="auto", help="Control the one-time feedback notice")
    parser.add_argument("--first-run-state", type=Path, default=None, help="Override the first-run marker path")
    return parser.parse_args()


def query_terms(query: str) -> list[str]:
    terms = [term.strip() for term in re.split(r"[\s,，;；、]+", query) if term.strip()]
    unique: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(term)
    return unique


def load_index(index_dir: Path) -> tuple[dict[str, Any], Path]:
    index_path = index_dir / "long_video_index.json"
    db_path = index_dir / "long_video_index.sqlite"
    if not index_path.is_file() or not db_path.is_file():
        raise ValueError("Index directory must contain long_video_index.json and long_video_index.sqlite")
    index_doc = json.loads(index_path.read_text(encoding="utf-8"))
    return index_doc, db_path


def section_for_chunk(sections: list[dict[str, Any]], start: float, end: float) -> dict[str, Any] | None:
    for section in sections:
        if end > section["start_sec"] and start < section["end_sec"]:
            return {"id": section["id"], "title": section["title"], "kind": section["kind"]}
    return None


def locate(index_dir: Path, query: str, start: float | None, end: float | None, limit: int, evidence_per_hit: int) -> dict[str, Any]:
    terms = query_terms(query)
    if not terms:
        raise ValueError("Query must contain at least one non-space term")
    if limit < 1 or evidence_per_hit < 1:
        raise ValueError("--limit and --evidence-per-hit must be >= 1")
    index_doc, db_path = load_index(index_dir)
    duration = float(index_doc.get("duration_sec") or 0)
    if start is not None and not math.isfinite(float(start)):
        raise ValueError("--start must be finite")
    if end is not None and not math.isfinite(float(end)):
        raise ValueError("--end must be finite")
    window_start = 0.0 if start is None else max(0.0, float(start))
    window_end = duration if end is None else min(duration, float(end))
    if window_end <= window_start:
        raise ValueError("--end must be greater than --start")
    normalized_terms = [term.casefold() for term in terms]
    phrase = " ".join(terms).casefold()
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        meta_rows = connection.execute("SELECT key, value FROM meta").fetchall()
        meta = {row["key"]: row["value"] for row in meta_rows}
        try:
            database_index_doc = json.loads(meta["index_json"])
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Index database metadata is missing or invalid; rebuild the index") from exc
        if database_index_doc != index_doc:
            raise ValueError("Index summary and database metadata do not match; rebuild the index before locating evidence")
        chunk_rows = connection.execute(
            "SELECT * FROM chunks WHERE end_sec > ? AND start_sec < ? ORDER BY start_sec",
            (window_start, window_end),
        ).fetchall()
        hits: list[dict[str, Any]] = []
        for chunk in chunk_rows:
            text = str(chunk["text"])
            if sha256_text(text) != chunk["text_sha256"]:
                raise ValueError("Retrieval chunk hash mismatch; rebuild the index before locating evidence")
            text_casefold = text.casefold()
            if not all(term in text_casefold for term in normalized_terms):
                continue
            score = 10.0 * len(normalized_terms)
            for term in normalized_terms:
                score += min(10, text_casefold.count(term)) * 2.0
            if phrase and phrase in text_casefold and len(terms) > 1:
                score += 8.0
            evidence_ids = json.loads(chunk["evidence_ids_json"])
            placeholders = ",".join("?" for _ in evidence_ids)
            evidence_rows = connection.execute(
                f"SELECT * FROM segments WHERE evidence_id IN ({placeholders}) ORDER BY start_sec",
                evidence_ids,
            ).fetchall() if evidence_ids else []
            citations = []
            for row in evidence_rows:
                if row["end_sec"] <= window_start or row["start_sec"] >= window_end:
                    continue
                quote = str(row["text"])
                if sha256_text(quote) != row["quote_sha256"]:
                    raise ValueError("Evidence quote hash mismatch; rebuild the index before locating evidence")
                quote_casefold = quote.casefold()
                matches = sum(1 for term in normalized_terms if term in quote_casefold)
                if matches == 0:
                    continue
                citations.append({
                    "evidence_id": row["evidence_id"],
                    "segment_id": row["segment_id"],
                    "start_sec": row["start_sec"],
                    "end_sec": row["end_sec"],
                    "timecode": format_range(row["start_sec"], row["end_sec"]),
                    "speaker": row["speaker"],
                    "quote": quote,
                    "quote_sha256": row["quote_sha256"],
                })
            citations.sort(key=lambda item: (-sum(1 for term in normalized_terms if term in item["quote"].casefold()), item["start_sec"]))
            citations = citations[:evidence_per_hit]
            if not citations:
                continue
            hit_start = max(float(chunk["start_sec"]), window_start)
            hit_end = min(float(chunk["end_sec"]), window_end)
            hits.append({
                "chunk_id": chunk["chunk_id"],
                "start_sec": hit_start,
                "end_sec": hit_end,
                "timecode": format_range(hit_start, hit_end),
                "section": section_for_chunk(index_doc.get("sections", []), hit_start, hit_end),
                "score": round(score, 3),
                "citations": citations,
            })
        hits.sort(key=lambda item: (-item["score"], item["start_sec"]))
        hits = hits[:limit]
        status = "completed" if hits else "no_matches"
        return {
            "schema_version": "1.0",
            "status": status,
            "watermark": {"author": "我密码呢", "mark": "wmmn"},
            "query": query,
            "terms": terms,
            "scope": {"start_sec": window_start, "end_sec": window_end, "timecode": format_range(window_start, window_end)},
            "index_id": index_doc["index_id"],
            "transcript_sha256": index_doc["source"]["transcript_sha256"],
            "hit_count": len(hits),
            "hits": hits,
            "next_action": (
                "Read the cited segments before drawing a conclusion; quote or summarize only what the evidence supports."
                if hits
                else "Try fewer or different literal keywords, or confirm that the transcript covers this topic; absence in the index is not proof of absence in the video."
            ),
            "limitations": [
                "Only literal transcript matches are returned; the tool does not infer synonyms or resolve pronouns.",
                "A hit shows where wording appears, not whether the claim is correct or representative.",
                "Transcript gaps and ASR errors limit what can be located.",
            ],
        }
    finally:
        connection.close()


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 长视频定位结果",
        "",
        "> 只展示时间码和逐字证据，不做专业拆解或内容价值判断。",
        "",
        f"- 查询：{result['query']}",
        f"- 范围：{result['scope']['timecode']}",
        f"- 候选：{result['hit_count']}",
        f"- index_id：`{result['index_id']}`",
    ]
    if result["status"] == "no_matches":
        lines.extend(["", "没有找到同时包含这些关键词的片段。不要据此断言视频没有讨论该主题；先检查逐字稿覆盖和关键词。", "", ""])
        return "\n".join(lines)
    for ordinal, hit in enumerate(result["hits"], 1):
        section = hit.get("section") or {}
        lines.extend(["", f"## {ordinal}. {hit['timecode']}", ""])
        if section:
            lines.append(f"- 章节/时间桶：{section.get('title')}")
        lines.append(f"- 检索块：`{hit['chunk_id']}`；匹配分：{hit['score']}")
        for citation in hit["citations"]:
            speaker = f" · {citation['speaker']}" if citation.get("speaker") else ""
            quote_hash = str(citation["quote_sha256"])[:12]
            lines.extend([
                "",
                f"**{citation['timecode']}{speaker}** · `{citation['evidence_id']}` · `sha256:{quote_hash}`",
                "",
                f"> {str(citation['quote']).replace(chr(10), ' ')}",
            ])
    lines.extend(["", ""])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    index_dir = args.index.resolve()
    try:
        result = locate(index_dir, args.query, args.start, args.end, args.limit, args.evidence_per_hit)
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
        failure = {
            "status": "blocked",
            "reason": "locate_failed",
            "detail": str(exc),
            "next_action": "Provide a valid index directory and at least one literal keyword.",
        }
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 2
    notice = take_first_run_notice(args.first_run, args.first_run_state)
    if notice["shown"]:
        result["feedback_notice"] = notice
    markdown = append_notice(render_markdown(result), notice)
    if args.out:
        out = args.out.resolve()
        out.mkdir(parents=True, exist_ok=True)
        (out / "locate_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out / "locate_result.md").write_text(markdown, encoding="utf-8")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except (OSError, sqlite3.Error) as exc:
        failure = {
            "status": "blocked",
            "reason": "output_write_failed",
            "detail": str(exc),
            "next_action": "Choose a writable output directory and retry.",
        }
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
