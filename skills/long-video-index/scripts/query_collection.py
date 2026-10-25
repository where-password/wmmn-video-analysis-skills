#!/usr/bin/env python3
# wmmn / 我密码呢
"""Retrieve exact transcript evidence from a multi-episode collection."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path
from typing import Any

from build_mentions import load_entities
from feedback_notice import append_notice, take_first_run_notice
from locate import query_terms
from transcript_io import format_range, sha256_text

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, required=True, help="Directory created by build_collection.py")
    parser.add_argument("--query", required=True, help="Literal keywords; separate independent terms with spaces")
    parser.add_argument("--episode", default=None, help="Optional episode id, ordinal, key, or exact title")
    parser.add_argument("--start", type=float, default=None, help="Optional start within each selected episode")
    parser.add_argument("--end", type=float, default=None, help="Optional end within each selected episode")
    parser.add_argument("--limit", type=int, default=5, help="Maximum candidate chunks")
    parser.add_argument("--evidence-per-hit", type=int, default=5, help="Maximum exact quotes per candidate")
    parser.add_argument("--aliases", type=Path, default=None, help="Optional entity/alias JSON for ASR spelling variants")
    parser.add_argument("--out", type=Path, default=None, help="Optional directory for query result files")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON for the AI-readable mode")
    parser.add_argument("--first-run", choices=["auto", "always", "never"], default="auto", help="Control the one-time feedback notice")
    parser.add_argument("--first-run-state", type=Path, default=None, help="Override the first-run marker path")
    return parser.parse_args()


def load_collection(collection_dir: Path) -> tuple[dict[str, Any], Path]:
    collection_path = collection_dir / "collection.json"
    db_path = collection_dir / "collection.sqlite"
    if not collection_path.is_file() or not db_path.is_file():
        raise ValueError("Collection directory must contain collection.json and collection.sqlite")
    return json.loads(collection_path.read_text(encoding="utf-8")), db_path


def resolve_episodes(collection_doc: dict[str, Any], selector: str | None) -> list[dict[str, Any]]:
    episodes = collection_doc.get("episodes") or []
    if not selector:
        return episodes
    needle = selector.strip().casefold()
    matches = [
        episode for episode in episodes
        if needle in {
            str(episode["id"]).casefold(),
            str(episode["ordinal"]).casefold(),
            str(episode["key"]).casefold(),
            str(episode["title"]).casefold(),
        }
    ]
    if not matches:
        raise ValueError("Episode selector did not match any episode id, ordinal, key, or title")
    if len(matches) > 1:
        raise ValueError("Episode selector is ambiguous; use the episode id")
    return matches

def build_term_groups(terms: list[str], entities: list[dict[str, Any]] | None) -> list[list[str]]:
    if not entities:
        return [[term] for term in terms]
    groups: list[list[str]] = []
    for term in terms:
        key = term.casefold()
        matched = None
        for entity in entities:
            variants = [entity["name"], *entity["aliases"]]
            if any(key == str(variant).casefold() for variant in variants):
                matched = variants
                break
        values = matched or [term]
        seen: set[str] = set()
        group: list[str] = []
        for value in values:
            folded = str(value).casefold()
            if folded not in seen:
                seen.add(folded)
                group.append(str(value))
        groups.append(group)
    return groups


def segment_window_hits(
    connection: sqlite3.Connection,
    episodes: list[dict[str, Any]],
    terms: list[str],
    normalized_groups: list[list[str]],
    window_start: float,
    window_end: float,
    evidence_per_hit: int,
    window_sec: float = 180.0,
) -> list[dict[str, Any]]:
    """Fallback for concepts that span adjacent retrieval chunks.

    Only episodes whose title matches every query group are scanned. Titles seed
    candidate episodes and ranking but never become evidence.
    """
    hits: list[dict[str, Any]] = []
    for episode in episodes:
        title_text = f"{episode['title']} {episode['key']}".casefold()
        if not all(any(alt in title_text for alt in group) for group in normalized_groups):
            continue
        rows = connection.execute(
            "SELECT * FROM segments WHERE episode_id = ? ORDER BY start_sec",
            (episode["id"],),
        ).fetchall()
        if not rows:
            continue
        title_match_count = len(normalized_groups)
        start_index = 0
        last_end = -1.0
        episode_hits = 0
        for end_index, row in enumerate(rows):
            end = float(row["end_sec"])
            while start_index <= end_index and float(rows[start_index]["start_sec"]) < end - window_sec:
                start_index += 1
            window_rows = rows[start_index:end_index + 1]
            if not window_rows:
                continue
            start = float(window_rows[0]["start_sec"])
            if start < last_end or end <= window_start or start >= window_end:
                continue
            context_text = " ".join(str(item["text"]) for item in window_rows).casefold()
            if not all(any(alt in context_text for alt in group) for group in normalized_groups):
                continue
            citations = []
            for item in window_rows:
                if item["end_sec"] <= window_start or item["start_sec"] >= window_end:
                    continue
                quote = str(item["text"])
                if sha256_text(quote) != item["quote_sha256"]:
                    raise ValueError("Evidence quote hash mismatch; rebuild the collection before querying")
                quote_casefold = quote.casefold()
                matched_terms = [
                    terms[index]
                    for index, group in enumerate(normalized_groups)
                    if any(alt in quote_casefold for alt in group)
                ]
                if matched_terms:
                    citations.append({
                        "evidence_id": item["evidence_id"],
                        "segment_id": item["segment_id"],
                        "start_sec": item["start_sec"],
                        "end_sec": item["end_sec"],
                        "timecode": format_range(item["start_sec"], item["end_sec"]),
                        "speaker": item["speaker"],
                        "quote": quote,
                        "quote_sha256": item["quote_sha256"],
                        "matched_terms": matched_terms,
                    })
            citations.sort(key=lambda item: (-len(item["matched_terms"]), item["start_sec"]))
            citations = citations[:evidence_per_hit]
            if not citations:
                continue
            score = 10.0 * len(normalized_groups)
            for group in normalized_groups:
                score += min(10, max(context_text.count(alt) for alt in group)) * 2.0
            score += title_match_count * 12.0 + 20.0
            hit_start = max(start, window_start)
            hit_end = min(end, window_end)
            episode_hits += 1
            hits.append({
                "episode": {
                    "id": episode["id"],
                    "ordinal": episode["ordinal"],
                    "title": episode["title"],
                    "transcript_sha256": episode["transcript_sha256"],
                },
                "chunk_id": None,
                "window_id": f"{episode['id']}:window-{episode_hits:04d}",
                "retrieval_method": "segment_window",
                "start_sec": hit_start,
                "end_sec": hit_end,
                "timecode": format_range(hit_start, hit_end),
                "context_start_sec": start,
                "context_end_sec": end,
                "context_text": " ".join(str(item["text"]) for item in window_rows),
                "score": round(score, 3),
                "ranking_signals": {
                    "title_match_count": title_match_count,
                    "title_all_terms": True,
                    "title_is_evidence": False,
                },
                "citations": citations,
            })
            last_end = end
            if episode_hits >= 3:
                break
    return hits


def query_collection(
    collection_dir: Path,
    query: str,
    episode_selector: str | None,
    start: float | None,
    end: float | None,
    limit: int,
    evidence_per_hit: int,
    aliases_path: Path | None = None,
) -> dict[str, Any]:
    terms = query_terms(query)
    if not terms:
        raise ValueError("Query must contain at least one non-space term")
    if limit < 1 or evidence_per_hit < 1:
        raise ValueError("--limit and --evidence-per-hit must be >= 1")
    if start is not None and not math.isfinite(float(start)):
        raise ValueError("--start must be finite")
    if end is not None and not math.isfinite(float(end)):
        raise ValueError("--end must be finite")

    entities = None
    aliases_sha256 = None
    if aliases_path is not None:
        entities, aliases_sha256 = load_entities(aliases_path.resolve())
    term_groups = build_term_groups(terms, entities)
    normalized_groups = [[str(value).casefold() for value in group] for group in term_groups]

    collection_doc, db_path = load_collection(collection_dir)
    episodes = resolve_episodes(collection_doc, episode_selector)
    episode_map = {episode["id"]: episode for episode in episodes}
    max_duration = max(float(episode["duration_sec"]) for episode in episodes)
    window_start = 0.0 if start is None else max(0.0, float(start))
    window_end = max_duration if end is None else min(max_duration, float(end))
    if window_end <= window_start:
        raise ValueError("--end must be greater than --start")

    phrase = " ".join(terms).casefold()
    episode_ids = [episode["id"] for episode in episodes]
    placeholders = ",".join("?" for _ in episode_ids)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        meta_rows = connection.execute("SELECT key, value FROM meta").fetchall()
        meta = {row["key"]: row["value"] for row in meta_rows}
        try:
            database_collection_doc = json.loads(meta["collection_json"])
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Collection database metadata is missing or invalid; rebuild the collection") from exc
        if database_collection_doc != collection_doc:
            raise ValueError("Collection summary and database metadata do not match; rebuild the collection")

        chunk_rows = connection.execute(
            f"SELECT * FROM chunks WHERE episode_id IN ({placeholders}) AND end_sec > ? AND start_sec < ? ORDER BY episode_id, start_sec",
            [*episode_ids, window_start, window_end],
        ).fetchall()
        hits: list[dict[str, Any]] = []
        for chunk in chunk_rows:
            context_text = str(chunk["text"])
            if sha256_text(context_text) != chunk["text_sha256"]:
                raise ValueError("Retrieval chunk hash mismatch; rebuild the collection before querying")
            text_casefold = context_text.casefold()
            if not all(any(alt in text_casefold for alt in group) for group in normalized_groups):
                continue
            episode = episode_map[chunk["episode_id"]]
            title_text = f"{episode['title']} {episode['key']}".casefold()
            title_match_count = sum(1 for group in normalized_groups if any(alt in title_text for alt in group))
            title_all_terms = title_match_count == len(normalized_groups)
            score = 10.0 * len(normalized_groups)
            for group in normalized_groups:
                score += min(10, max(text_casefold.count(alt) for alt in group)) * 2.0
            if phrase and phrase in text_casefold and len(terms) > 1:
                score += 8.0
            # Episode metadata only affects ranking. Citations remain the evidence.
            score += title_match_count * 12.0
            if title_all_terms:
                score += 20.0
            evidence_ids = json.loads(chunk["evidence_ids_json"])
            evidence_placeholders = ",".join("?" for _ in evidence_ids)
            evidence_rows = connection.execute(
                f"SELECT * FROM segments WHERE evidence_id IN ({evidence_placeholders}) ORDER BY start_sec",
                evidence_ids,
            ).fetchall() if evidence_ids else []
            citations = []
            for row in evidence_rows:
                if row["end_sec"] <= window_start or row["start_sec"] >= window_end:
                    continue
                quote = str(row["text"])
                if sha256_text(quote) != row["quote_sha256"]:
                    raise ValueError("Evidence quote hash mismatch; rebuild the collection before querying")
                quote_casefold = quote.casefold()
                matched_terms = [
                    terms[index]
                    for index, group in enumerate(normalized_groups)
                    if any(alt in quote_casefold for alt in group)
                ]
                if not matched_terms:
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
                    "matched_terms": matched_terms,
                })
            citations.sort(key=lambda item: (-len(item["matched_terms"]), item["start_sec"]))
            citations = citations[:evidence_per_hit]
            if not citations:
                continue
            hit_start = max(float(chunk["start_sec"]), window_start)
            hit_end = min(float(chunk["end_sec"]), window_end)
            hits.append({
                "episode": {
                    "id": episode["id"],
                    "ordinal": episode["ordinal"],
                    "title": episode["title"],
                    "transcript_sha256": episode["transcript_sha256"],
                },
                "chunk_id": chunk["chunk_id"],
                "window_id": None,
                "retrieval_method": "chunk",
                "start_sec": hit_start,
                "end_sec": hit_end,
                "timecode": format_range(hit_start, hit_end),
                "context_start_sec": chunk["start_sec"],
                "context_end_sec": chunk["end_sec"],
                "context_text": context_text,
                "score": round(score, 3),
                "ranking_signals": {
                    "title_match_count": title_match_count,
                    "title_all_terms": title_all_terms,
                    "title_is_evidence": False,
                },
                "citations": citations,
            })
        hits.extend(segment_window_hits(
            connection, episodes, terms, normalized_groups,
            window_start, window_end, evidence_per_hit,
        ))
        hits.sort(key=lambda item: (-item["score"], item["episode"]["ordinal"], item["start_sec"]))
        deduped: list[dict[str, Any]] = []
        for hit in hits:
            duplicate = False
            for kept in deduped:
                if kept["episode"]["id"] != hit["episode"]["id"]:
                    continue
                overlap = max(0.0, min(kept["end_sec"], hit["end_sec"]) - max(kept["start_sec"], hit["start_sec"]))
                shorter = min(kept["end_sec"] - kept["start_sec"], hit["end_sec"] - hit["start_sec"])
                if shorter > 0 and overlap / shorter >= 0.5:
                    duplicate = True
                    break
            if not duplicate:
                deduped.append(hit)
        hits = deduped[:limit]
        status = "completed" if hits else "no_matches"
        return {
            "schema_version": "1.0",
            "status": status,
            "watermark": {"author": "我密码呢", "mark": "wmmn"},
            "collection_id": collection_doc["collection_id"],
            "query": query,
            "terms": terms,
            "term_groups": term_groups,
            "aliases_sha256": aliases_sha256,
            "scope": {
                "all_episodes": episode_selector is None,
                "episode_count": len(episodes),
                "episodes": [
                    {"id": episode["id"], "ordinal": episode["ordinal"], "title": episode["title"]}
                    for episode in episodes
                ] if episode_selector is not None else [],
                "start_sec": window_start,
                "end_sec": window_end,
                "timecode": format_range(window_start, window_end),
            },
            "grounding_contract": {
                "use_only_citations": True,
                "read_context_before_answering": True,
                "absence_is_not_proof": True,
                "do_not_answer_from_catalog_titles": True,
            },
            "hit_count": len(hits),
            "hits": hits,
            "next_action": (
                "Read the context and cited transcript segments, answer only from that evidence, and cite episode plus time range."
                if hits
                else "Try fewer or different literal keywords, or confirm transcript coverage; no match does not prove the topic is absent."
            ),
            "limitations": [
                "Only literal transcript matches are returned; the tool does not infer synonyms or resolve pronouns.",
                "A hit shows where wording appears, not whether the claim is correct or representative.",
                "Transcript gaps and ASR errors limit what can be found.",
                "Alias expansion only uses the optional alias file supplied by the caller.",
            ],
        }
    finally:
        connection.close()


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 长视频跨集定位",
        "",
        "> 结果包含真实逐字稿和证据；这不是内容摘要，也不自动下结论。",
        "",
        f"- 查询：{result['query']}",
        f"- 集数范围：{result['scope']['episode_count']} 集",
        f"- 时间范围（每集内）：{result['scope']['timecode']}",
        f"- 候选：{result['hit_count']}",
        f"- collection_id：`{result['collection_id']}`",
    ]
    if result["status"] == "no_matches":
        lines.extend(["", "没有找到同时包含这些关键词的片段。不要据此断言语料库没有讨论该主题；请检查关键词和逐字稿覆盖。", "", ""])
        return "\n".join(lines)
    for ordinal, hit in enumerate(result["hits"], 1):
        episode = hit["episode"]
        lines.extend([
            "",
            f"## {ordinal}. 第 {episode['ordinal']} 集 · {episode['title']} · {hit['timecode']}",
            "",
            f"- 检索方式：{hit.get('retrieval_method', 'chunk')}；匹配分：{hit['score']}",
            f"- 检索单元：`{hit.get('chunk_id') or hit.get('window_id')}`",
            f"- 上下文范围：{format_range(hit['context_start_sec'], hit['context_end_sec'])}",
            "",
            "**上下文原文**",
            "",
            f"> {str(hit['context_text']).replace(chr(10), ' ')}",
            "",
            "**精确证据**",
        ])
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
    try:
        result = query_collection(
            args.collection.resolve(), args.query, args.episode, args.start, args.end,
            args.limit, args.evidence_per_hit, args.aliases,
        )
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
        print(json.dumps({
            "status": "blocked",
            "reason": "collection_query_failed",
            "detail": str(exc),
            "next_action": "Provide a valid collection directory and at least one literal keyword.",
        }, ensure_ascii=False), file=sys.stderr)
        return 2
    notice = take_first_run_notice(args.first_run, args.first_run_state)
    if notice["shown"]:
        result["feedback_notice"] = notice
    markdown = append_notice(render_markdown(result), notice)
    if args.out:
        out = args.out.resolve()
        out.mkdir(parents=True, exist_ok=True)
        (out / "collection_query.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out / "collection_query.md").write_text(markdown, encoding="utf-8")
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
        print(json.dumps({
            "status": "blocked",
            "reason": "output_write_failed",
            "detail": str(exc),
            "next_action": "Choose a writable output directory and retry.",
        }, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
