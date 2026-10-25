#!/usr/bin/env python3
# wmmn / 我密码呢
"""Query episode and timestamp evidence from an exact-alias mention index."""

from __future__ import annotations

import argparse
import json
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
    parser.add_argument("--index", type=Path, required=True, help="Directory created by build_mentions.py")
    parser.add_argument("--entity", required=True, help="Entity id, name, or an exact configured alias")
    parser.add_argument("--episode", default=None, help="Optional episode id, ordinal, or exact title")
    parser.add_argument("--limit", type=int, default=50, help="Maximum mention rows to return")
    parser.add_argument("--out", type=Path, default=None, help="Optional output directory")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--first-run", choices=["auto", "always", "never"], default="auto", help="Control the one-time feedback notice")
    parser.add_argument("--first-run-state", type=Path, default=None, help="Override the first-run marker path")
    return parser.parse_args()


def load_index(index_dir: Path) -> tuple[dict[str, Any], Path]:
    summary_path = index_dir / "mentions.json"
    db_path = index_dir / "mentions.sqlite"
    if not summary_path.is_file() or not db_path.is_file():
        raise ValueError("Mention index must contain mentions.json and mentions.sqlite")
    return json.loads(summary_path.read_text(encoding="utf-8")), db_path


def resolve_entity(summary: dict[str, Any], selector: str) -> dict[str, Any]:
    needle = selector.strip().casefold()
    matches = [
        entity for entity in summary.get("entities", [])
        if needle == str(entity["id"]).casefold()
        or needle == str(entity["name"]).casefold()
        or needle in {str(alias).casefold() for alias in entity.get("aliases", [])}
    ]
    if not matches:
        raise ValueError("Entity selector did not match any configured id, name, or alias")
    if len(matches) > 1:
        raise ValueError("Entity selector is ambiguous; use the entity id")
    return matches[0]


def query_mentions(index_dir: Path, selector: str, episode_selector: str | None, limit: int) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("--limit must be >= 1")
    summary, db_path = load_index(index_dir)
    entity = resolve_entity(summary, selector)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        meta_rows = connection.execute("SELECT key, value FROM meta").fetchall()
        meta = {row["key"]: row["value"] for row in meta_rows}
        try:
            database_summary = json.loads(meta["summary_json"])
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Mention database metadata is missing or invalid; rebuild the mention index") from exc
        if database_summary != summary:
            raise ValueError("Mention summary and database metadata do not match; rebuild the mention index")

        rows = connection.execute(
            "SELECT * FROM mentions WHERE entity_id = ? ORDER BY episode_ordinal, start_sec",
            (entity["id"],),
        ).fetchall()
        matched: list[dict[str, Any]] = []
        episode_hint = episode_selector.strip().casefold() if episode_selector else None
        for row in rows:
            if episode_hint and episode_hint not in {
                str(row["episode_id"]).casefold(),
                str(row["episode_ordinal"]).casefold(),
                str(row["episode_title"]).casefold(),
            }:
                continue
            quote = str(row["quote"])
            if sha256_text(quote) != row["quote_sha256"]:
                raise ValueError("Evidence quote hash mismatch; rebuild the mention index")
            matched.append({
                "episode_id": row["episode_id"],
                "episode_ordinal": row["episode_ordinal"],
                "episode_title": row["episode_title"],
                "start_sec": row["start_sec"],
                "end_sec": row["end_sec"],
                "timecode": format_range(row["start_sec"], row["end_sec"]),
                "alias": row["alias"],
                "occurrence_count": row["occurrence_count"],
                "evidence_id": row["evidence_id"],
                "segment_id": row["segment_id"],
                "quote": quote,
                "quote_sha256": row["quote_sha256"],
                "transcript_sha256": row["transcript_sha256"],
            })
        returned = matched[:limit]
        status = "completed" if matched else "no_matches"
        return {
            "schema_version": "1.0",
            "status": status,
            "watermark": {"author": "我密码呢", "mark": "wmmn"},
            "collection_id": summary["collection_id"],
            "entity": {
                "id": entity["id"],
                "name": entity["name"],
                "type": entity["type"],
                "aliases": entity["aliases"],
            },
            "scope": {
                "episode": episode_selector,
                "matched_mentions": len(matched),
                "returned_mentions": len(returned),
                "limit": limit,
            },
            "mentions": returned,
            "limitations": [
                "Results are exact alias matches, not semantic entity resolution.",
                "A mention does not establish attitude, correctness, or intent.",
                "Unlisted aliases may be missing from this index.",
            ],
        }
    finally:
        connection.close()

def render_markdown(result: dict[str, Any]) -> str:
    entity = result["entity"]
    lines = [
        "# 实体提及定位",
        "",
        f"- 实体：{entity['name']}（{entity['id']}）",
        f"- 类型：{entity['type']}",
        f"- 匹配提及：{result['scope']['matched_mentions']}",
        f"- 本次返回：{result['scope']['returned_mentions']}",
        f"- collection_id：`{result['collection_id']}`",
    ]
    if result["status"] == "no_matches":
        lines.extend(["", "没有找到已配置别名的字面提及。不要据此断言整个语料库从未讨论该实体；先检查别名表。", "", ""])
        return "\n".join(lines)
    current_episode = None
    for mention in result["mentions"]:
        episode_key = (mention["episode_ordinal"], mention["episode_title"])
        if episode_key != current_episode:
            current_episode = episode_key
            lines.extend(["", f"## 第 {mention['episode_ordinal']} 集 · {mention['episode_title']}"])
        lines.extend([
            "",
            f"**{mention['timecode']}** · 别名 `{mention['alias']}` · `{mention['evidence_id']}`",
            "",
            f"> {str(mention['quote']).replace(chr(10), ' ')}",
        ])
    if result["scope"]["matched_mentions"] > result["scope"]["returned_mentions"]:
        lines.extend(["", f"> 仅展示前 {result['scope']['returned_mentions']} 条；可用 `--limit` 调整。"])
    lines.extend(["", ""])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    try:
        result = query_mentions(args.index.resolve(), args.entity, args.episode, args.limit)
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
        print(json.dumps({
            "status": "blocked",
            "reason": "mention_query_failed",
            "detail": str(exc),
            "next_action": "Provide a valid mention index and a configured entity id, name, or alias.",
        }, ensure_ascii=False), file=sys.stderr)
        return 2
    notice = take_first_run_notice(args.first_run, args.first_run_state)
    if notice["shown"]:
        result["feedback_notice"] = notice
    markdown = append_notice(render_markdown(result), notice)
    if args.out:
        out = args.out.resolve()
        out.mkdir(parents=True, exist_ok=True)
        (out / "mention_query.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out / "mention_query.md").write_text(markdown, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else markdown)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except (OSError, sqlite3.Error) as exc:
        print(json.dumps({
            "status": "blocked",
            "reason": "output_write_failed",
            "detail": str(exc),
            "next_action": "Choose a writable output directory and retry.",
        }, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
