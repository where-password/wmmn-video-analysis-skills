#!/usr/bin/env python3
# wmmn / 我密码呢
"""Build an optional exact-alias entity mention index for a transcript collection."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

from transcript_io import sha256_text

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, required=True, help="Directory created by build_collection.py")
    parser.add_argument("--entities", type=Path, required=True, help="JSON entity and alias list")
    parser.add_argument("--out", type=Path, required=True, help="Mention index output directory")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def load_collection(collection_dir: Path) -> tuple[dict[str, Any], Path]:
    collection_path = collection_dir / "collection.json"
    db_path = collection_dir / "collection.sqlite"
    if not collection_path.is_file() or not db_path.is_file():
        raise ValueError("Collection directory must contain collection.json and collection.sqlite")
    return json.loads(collection_path.read_text(encoding="utf-8")), db_path


def load_entities(path: Path) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8-sig"))
    items = data.get("entities") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        raise ValueError("Entities JSON must contain a non-empty entities array")
    entities: list[dict[str, Any]] = []
    ids: set[str] = set()
    aliases_seen: dict[str, str] = {}
    for ordinal, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Entity {ordinal} must be an object")
        entity_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not entity_id or not name:
            raise ValueError(f"Entity {ordinal} requires id and name")
        if entity_id in ids:
            raise ValueError(f"Duplicate entity id: {entity_id}")
        ids.add(entity_id)
        raw_aliases = item.get("aliases") or [name]
        if not isinstance(raw_aliases, list):
            raise ValueError(f"Entity {entity_id} aliases must be an array")
        aliases: list[str] = []
        local_seen: set[str] = set()
        for raw_alias in [name, *raw_aliases]:
            alias = str(raw_alias).strip()
            key = alias.casefold()
            if not alias or key in local_seen:
                continue
            owner = aliases_seen.get(key)
            if owner and owner != entity_id:
                raise ValueError(f"Alias {alias!r} belongs to both {owner} and {entity_id}")
            aliases_seen[key] = entity_id
            local_seen.add(key)
            aliases.append(alias)
        entities.append({
            "id": entity_id,
            "name": name,
            "type": str(item.get("type") or "entity").strip() or "entity",
            "aliases": aliases,
        })
    return entities, hashlib.sha256(raw).hexdigest()

def alias_occurrences(text: str, aliases: list[str]) -> list[tuple[str, int]]:
    """Count non-overlapping alias matches, preferring the longest alias at one position."""
    folded = text.casefold()
    matches: list[tuple[int, int, str]] = []
    for alias in aliases:
        needle = alias.casefold()
        start = folded.find(needle)
        while start >= 0:
            matches.append((start, start + len(needle), alias))
            start = folded.find(needle, start + 1)
    selected: list[tuple[int, int, str]] = []
    for start, end, alias in sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]))):
        if any(not (end <= previous_start or start >= previous_end) for previous_start, previous_end, _ in selected):
            continue
        selected.append((start, end, alias))
    counts: dict[str, int] = {}
    for _, _, alias in selected:
        counts[alias] = counts.get(alias, 0) + 1
    return list(counts.items())


def create_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript("""
    CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE entities(
        entity_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        aliases_json TEXT NOT NULL,
        mention_count INTEGER NOT NULL,
        episode_count INTEGER NOT NULL
    );
    CREATE TABLE mentions(
        mention_id TEXT PRIMARY KEY,
        entity_id TEXT NOT NULL,
        entity_name TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        alias TEXT NOT NULL,
        occurrence_count INTEGER NOT NULL,
        episode_id TEXT NOT NULL,
        episode_ordinal INTEGER NOT NULL,
        episode_title TEXT NOT NULL,
        start_sec REAL NOT NULL,
        end_sec REAL NOT NULL,
        evidence_id TEXT NOT NULL,
        segment_id TEXT NOT NULL,
        quote TEXT NOT NULL,
        quote_sha256 TEXT NOT NULL,
        transcript_sha256 TEXT NOT NULL
    );
    CREATE INDEX idx_mentions_entity_order ON mentions(entity_id, episode_ordinal, start_sec);
    CREATE INDEX idx_mentions_episode ON mentions(episode_id, start_sec);
    """)
    return connection


def render_markdown(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    lines = [
        "# 跨集实体提及索引",
        "",
        "> 本索引按用户提供的别名做确定性匹配，不做自动实体识别，也不判断提及态度。",
        "",
        f"- 实体数：{counts['entities']}",
        f"- 提及记录：{counts['mentions']}",
        f"- 出现次数：{counts['occurrences']}",
        f"- 涉及集数：{counts['episodes_with_mentions']}",
        f"- collection_id：`{summary['collection_id']}`",
        "",
        "| 实体 | 类型 | 提及记录 | 出现次数 | 涉及集数 |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for entity in summary["entities"]:
        lines.append(
            f"| {entity['name']} | {entity['type']} | {entity['mention_records']} | "
            f"{entity['mention_count']} | {entity['episode_count']} |"
        )
    lines.extend([
        "",
        "具体集数、时间范围和原话请用：",
        "",
        "```bash",
        "python scripts/query_mentions.py --index <MENTIONS_DIR> --entity \"实体名\" --json",
        "```",
        "",
    ])
    return "\n".join(lines)

def scan_mentions(
    collection_doc: dict[str, Any],
    collection_db: Path,
    entities: list[dict[str, Any]],
    output_db: sqlite3.Connection,
) -> tuple[dict[str, dict[str, Any]], int, int]:
    stats = {
        entity["id"]: {"mention_records": 0, "mention_count": 0, "episodes": set()}
        for entity in entities
    }
    source = sqlite3.connect(collection_db)
    source.row_factory = sqlite3.Row
    mention_ordinal = 0
    occurrences = 0
    try:
        meta_rows = source.execute("SELECT key, value FROM meta").fetchall()
        meta = {row["key"]: row["value"] for row in meta_rows}
        try:
            database_collection_doc = json.loads(meta["collection_json"])
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Collection database metadata is missing or invalid; rebuild the collection") from exc
        if database_collection_doc != collection_doc:
            raise ValueError("Collection summary and database metadata do not match; rebuild the collection")

        rows = source.execute(
            "SELECT s.*, e.ordinal AS episode_ordinal, e.title AS episode_title, e.transcript_sha256 AS transcript_sha256 "
            "FROM segments s JOIN episodes e ON e.episode_id = s.episode_id "
            "ORDER BY e.ordinal, s.start_sec"
        )
        for row in rows:
            quote = str(row["text"])
            if sha256_text(quote) != row["quote_sha256"]:
                raise ValueError("Evidence quote hash mismatch; rebuild the collection before building mentions")
            for entity in entities:
                for alias, occurrence_count in alias_occurrences(quote, entity["aliases"]):
                    mention_ordinal += 1
                    occurrences += occurrence_count
                    stats[entity["id"]]["mention_records"] += 1
                    stats[entity["id"]]["mention_count"] += occurrence_count
                    stats[entity["id"]]["episodes"].add(int(row["episode_ordinal"]))
                    output_db.execute(
                        "INSERT INTO mentions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            f"mention-{mention_ordinal:08d}", entity["id"], entity["name"], entity["type"],
                            alias, occurrence_count, row["episode_id"], row["episode_ordinal"],
                            row["episode_title"], row["start_sec"], row["end_sec"], row["evidence_id"],
                            row["segment_id"], quote, row["quote_sha256"], row["transcript_sha256"],
                        ),
                    )
    finally:
        source.close()
    return stats, mention_ordinal, occurrences

def main() -> int:
    args = parse_args()
    collection_doc, collection_db = load_collection(args.collection.resolve())
    entities, entities_sha256 = load_entities(args.entities.resolve())
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    output_names = ["mentions.json", "mentions.sqlite", "mentions.md"]
    existing = [out / name for name in output_names if (out / name).exists()]
    if existing and not args.overwrite:
        raise ValueError("Mention output already exists. Pass --overwrite to replace known mention files.")

    with tempfile.TemporaryDirectory(prefix=f".{out.name}-build-", dir=out.parent) as staging_raw:
        staging = Path(staging_raw)
        db = create_database(staging / "mentions.sqlite")
        try:
            stats, mention_records, occurrences = scan_mentions(collection_doc, collection_db, entities, db)
            summary_entities = []
            for entity in entities:
                entity_stats = stats[entity["id"]]
                summary_entities.append({
                    **entity,
                    "mention_records": entity_stats["mention_records"],
                    "mention_count": entity_stats["mention_count"],
                    "episode_count": len(entity_stats["episodes"]),
                    "episode_ordinals": sorted(entity_stats["episodes"]),
                })
            summary = {
                "schema_version": "1.0",
                "status": "completed",
                "watermark": {"author": "我密码呢", "mark": "wmmn"},
                "collection_id": collection_doc["collection_id"],
                "entities_sha256": entities_sha256,
                "counts": {
                    "entities": len(entities),
                    "mentions": mention_records,
                    "occurrences": occurrences,
                    "episodes_with_mentions": len({row for entity in summary_entities for row in entity["episode_ordinals"]}),
                },
                "entities": summary_entities,
                "files": {"database": "mentions.sqlite", "report": "mentions.md"},
                "method": "exact casefolded alias matching; no automatic entity discovery",
                "limitations": [
                    "Alias matching is deterministic but can include false positives.",
                    "Unlisted aliases and synonyms are not discovered automatically.",
                    "A mention is not a claim that the entity is discussed positively, negatively, or correctly.",
                ],
            }
            db.executemany(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                [
                    ("collection_id", summary["collection_id"]),
                    ("summary_json", json.dumps(summary, ensure_ascii=False, separators=(",", ":"))),
                    ("entities_sha256", entities_sha256),
                ],
            )
            db.executemany(
                "INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        entity["id"], entity["name"], entity["type"],
                        json.dumps(entity["aliases"], ensure_ascii=False),
                        entity["mention_count"], entity["episode_count"],
                    )
                    for entity in summary_entities
                ],
            )
            db.commit()
        finally:
            db.close()
        (staging / "mentions.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (staging / "mentions.md").write_text(render_markdown(summary), encoding="utf-8")
        for name in output_names:
            (staging / name).replace(out / name)

    print(json.dumps({
        "status": "completed",
        "out": str(out),
        "collection_id": summary["collection_id"],
        "entities": summary["counts"]["entities"],
        "mentions": summary["counts"]["mentions"],
        "occurrences": summary["counts"]["occurrences"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
        print(json.dumps({
            "status": "blocked",
            "reason": "mention_build_failed",
            "detail": str(exc),
            "next_action": "Provide a valid collection, an entities JSON file, and a writable output directory.",
        }, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
