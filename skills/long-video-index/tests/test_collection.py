import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_mentions import alias_occurrences


def run_script(name, *args):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name), *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={
            **os.environ,
            "WMMN_LONG_VIDEO_FIRST_RUN_STATE": str(
                Path(tempfile.gettempdir()) / f"wmmn-long-video-tests-{os.getpid()}.json"
            ),
        },
    )


class CollectionTests(unittest.TestCase):
    def write_transcripts(self, root):
        directory = root / "transcripts"
        directory.mkdir()
        files = {
            "010_证据定位.json": {
                "language": "zh",
                "duration_sec": 120,
                "segments": [
                    {"id": "a", "start": 0, "end": 10, "text": "第二集讨论证据定位和快速检索。"},
                    {"id": "b", "start": 30, "end": 35, "text": "这一段强调证据链和原始时间码。"},
                ],
            },
            "002_基础概念.json": {
                "language": "zh",
                "duration_sec": 100,
                "segments": [
                    {"id": "a", "start": 0, "end": 8, "text": "这一集介绍漏洞挖掘。"},
                    {"id": "b", "start": 20, "end": 25, "text": "sqlmap 可以帮助验证注入风险。"},
                ],
            },
            "011_工具边界.json": {
                "language": "zh",
                "duration_sec": 90,
                "segments": [
                    {"id": "a", "start": 40, "end": 45, "text": "SQLMap 的使用边界需要说明。"},
                ],
            },
        }
        for name, payload in files.items():
            (directory / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return directory

    def build_collection(self, root, transcripts):
        out = root / "collection"
        result = run_script(
            "build_collection.py", "--transcripts", transcripts, "--out", out,
            "--collection-title", "测试语料库",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return out

    def write_entities(self, root, payload=None):
        path = root / "entities.json"
        path.write_text(json.dumps(payload or {"entities": [
            {"id": "sqlmap", "name": "sqlmap", "type": "tool", "aliases": ["SQLMap"]},
            {"id": "evidence", "name": "证据链", "type": "concept", "aliases": []},
        ]}, ensure_ascii=False), encoding="utf-8")
        return path

    def test_collection_contains_content_not_only_catalog(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = self.build_collection(root, self.write_transcripts(root))
            for name in ["collection.json", "collection.sqlite", "evidence.jsonl", "collection_outline.md"]:
                self.assertTrue((out / name).is_file(), name)
            doc = json.loads((out / "collection.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["counts"]["episodes"], 3)
            self.assertEqual([episode["title"] for episode in doc["episodes"]], ["基础概念", "证据定位", "工具边界"])
            self.assertTrue(doc["content_contract"]["catalog_is_navigation_only"])
            self.assertTrue(doc["content_contract"]["answer_grounding_required"])
            connection = sqlite3.connect(out / "collection.sqlite")
            try:
                texts = [row[0] for row in connection.execute("SELECT text FROM segments ORDER BY evidence_id")]
            finally:
                connection.close()
            self.assertTrue(any("sqlmap" in text for text in texts))
            for line in (out / "evidence.jsonl").read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                self.assertEqual(hashlib.sha256(row["quote"].encode("utf-8")).hexdigest(), row["quote_sha256"])

    def test_query_returns_actual_chunks_and_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = self.build_collection(root, self.write_transcripts(root))
            result = run_script(
                "query_collection.py", "--collection", out,
                "--query", "证据 检索", "--json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "completed")
            self.assertGreaterEqual(payload["hit_count"], 1)
            hit = payload["hits"][0]
            self.assertEqual(hit["episode"]["title"], "证据定位")
            self.assertIn("证据", hit["context_text"])
            self.assertTrue(hit["citations"])
            quote = hit["citations"][0]["quote"]
            self.assertEqual(hashlib.sha256(quote.encode("utf-8")).hexdigest(), hit["citations"][0]["quote_sha256"])
            self.assertTrue(payload["grounding_contract"]["use_only_citations"])
            self.assertTrue(payload["scope"]["all_episodes"])
            self.assertEqual(payload["scope"]["episode_count"], 3)
            self.assertEqual(payload["scope"]["episodes"], [])
            self.assertEqual(len(hit["episode"]["transcript_sha256"]), 64)

    def test_title_match_ranks_episode_without_becoming_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcripts = root / "rank-transcripts"
            transcripts.mkdir()
            payload = {
                "duration_sec": 60,
                "segments": [{"id": "a", "start": 0, "end": 5, "text": "Redis 未授权 访问 的通用讲解。"}],
            }
            (transcripts / "001_普通内容.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            (transcripts / "002_Redis未授权访问.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            collection = self.build_collection(root, transcripts)
            result = run_script(
                "query_collection.py", "--collection", collection,
                "--query", "Redis 未授权 访问", "--json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["hits"][0]["episode"]["ordinal"], 2)
            self.assertTrue(payload["hits"][0]["ranking_signals"]["title_all_terms"])
            self.assertFalse(payload["hits"][0]["ranking_signals"]["title_is_evidence"])

    def test_query_feedback_notice_is_shown_once(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            collection = self.build_collection(root, self.write_transcripts(root))
            state = root / "feedback-state.json"
            first = run_script(
                "query_collection.py", "--collection", collection,
                "--query", "sqlmap", "--json", "--first-run-state", state,
            )
            second = run_script(
                "query_collection.py", "--collection", collection,
                "--query", "sqlmap", "--json", "--first-run-state", state,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            first_payload = json.loads(first.stdout)
            second_payload = json.loads(second.stdout)
            self.assertTrue(first_payload["feedback_notice"]["shown"])
            self.assertIn("抖音私信", first_payload["feedback_notice"]["text"])
            self.assertIn("wmmn · 我密码呢", first_payload["feedback_notice"]["text"])
            self.assertNotIn("feedback_notice", second_payload)

    def test_query_episode_and_time_filters(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = self.build_collection(root, self.write_transcripts(root))
            result = run_script(
                "query_collection.py", "--collection", out, "--query", "证据链",
                "--episode", "2", "--start", "30", "--end", "36", "--json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["hit_count"], 1)
            self.assertEqual(payload["hits"][0]["episode"]["ordinal"], 2)
            self.assertTrue(all(30 <= item["start_sec"] < 36 for item in payload["hits"][0]["citations"]))
            missing = run_script("query_collection.py", "--collection", out, "--query", "完全不存在的词", "--json")
            self.assertEqual(missing.returncode, 0, missing.stderr)
            self.assertEqual(json.loads(missing.stdout)["status"], "no_matches")

    def test_mention_index_tracks_episode_and_time(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            collection = self.build_collection(root, self.write_transcripts(root))
            mentions_out = root / "mentions"
            result = run_script(
                "build_mentions.py", "--collection", collection,
                "--entities", self.write_entities(root), "--out", mentions_out,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads((mentions_out / "mentions.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["method"], "exact casefolded alias matching; no automatic entity discovery")
            sqlmap = next(entity for entity in summary["entities"] if entity["id"] == "sqlmap")
            self.assertEqual(sqlmap["episode_count"], 2)
            query = run_script("query_mentions.py", "--index", mentions_out, "--entity", "SQLMap", "--json")
            self.assertEqual(query.returncode, 0, query.stderr)
            payload = json.loads(query.stdout)
            self.assertEqual(payload["scope"]["matched_mentions"], 2)
            self.assertEqual([item["episode_ordinal"] for item in payload["mentions"]], [1, 3])
            self.assertTrue(all(len(item["transcript_sha256"]) == 64 for item in payload["mentions"]))
            filtered = run_script(
                "query_mentions.py", "--index", mentions_out, "--entity", "sqlmap",
                "--episode", "3", "--json",
            )
            self.assertEqual(filtered.returncode, 0, filtered.stderr)
            self.assertEqual(json.loads(filtered.stdout)["scope"]["matched_mentions"], 1)

    def test_optional_aliases_expand_asr_variants(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcripts = root / "alias-transcripts"
            transcripts.mkdir()
            payload = {
                "duration_sec": 60,
                "segments": [{"id": "a", "start": 0, "end": 5, "text": "BobSuite 基本 用法。"}],
            }
            (transcripts / "001_BurpSuite基本用法.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            collection = self.build_collection(root, transcripts)
            aliases = root / "aliases.json"
            aliases.write_text(json.dumps({"entities": [
                {"id": "burp", "name": "BurpSuite", "aliases": ["BobSuite", "PopSuite"]},
            ]}, ensure_ascii=False), encoding="utf-8")
            result = run_script(
                "query_collection.py", "--collection", collection,
                "--query", "BurpSuite 基本 用法", "--aliases", aliases, "--json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["hits"][0]["episode"]["ordinal"], 1)
            self.assertEqual(payload["term_groups"][0], ["BurpSuite", "BobSuite", "PopSuite"])

    def test_segment_window_fallback_finds_cross_chunk_terms(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcripts = root / "window-transcripts"
            transcripts.mkdir()
            payload = {
                "duration_sec": 220,
                "segments": [
                    {"id": "a", "start": 0, "end": 5, "text": "Redis 的基本概念。"},
                    {"id": "b", "start": 130, "end": 135, "text": "未授权的访问条件。"},
                    {"id": "c", "start": 160, "end": 165, "text": "访问验证的方法。"},
                ],
            }
            (transcripts / "001_Redis未授权访问.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            collection = self.build_collection(root, transcripts)
            result = run_script(
                "query_collection.py", "--collection", collection,
                "--query", "Redis 未授权 访问", "--json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["hits"][0]["retrieval_method"], "segment_window")
            self.assertTrue(payload["hits"][0]["window_id"].endswith("0001"))
            self.assertGreaterEqual(len(payload["hits"][0]["citations"]), 2)

    def test_failed_collection_overwrite_keeps_existing_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcripts = self.write_transcripts(root)
            out = self.build_collection(root, transcripts)
            names = ["collection.json", "collection.sqlite", "evidence.jsonl", "collection_outline.md"]
            before = {name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in names}
            (transcripts / "999_bad.json").write_text(json.dumps({
                "duration_sec": 10,
                "segments": [{"start": 5, "end": 3, "text": "无效"}],
            }, ensure_ascii=False), encoding="utf-8")
            result = run_script(
                "build_collection.py", "--transcripts", transcripts,
                "--out", out, "--overwrite",
            )
            self.assertEqual(result.returncode, 2)
            for name, digest in before.items():
                self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest)

    def test_collection_evidence_tamper_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = self.build_collection(root, self.write_transcripts(root))
            connection = sqlite3.connect(out / "collection.sqlite")
            try:
                connection.execute(
                    "UPDATE segments SET text = ? WHERE evidence_id = ?",
                    ("被篡改的逐字稿", "ep-0001:ev-000002"),
                )
                connection.commit()
            finally:
                connection.close()
            result = run_script("query_collection.py", "--collection", out, "--query", "sqlmap", "--json")
            self.assertEqual(result.returncode, 2)
            self.assertIn("Evidence quote hash mismatch", result.stderr)

    def test_overlapping_aliases_prefer_the_longer_match(self):
        self.assertEqual(
            alias_occurrences("Burp Suite and Burp", ["Burp", "Burp Suite"]),
            [("Burp Suite", 1), ("Burp", 1)],
        )

    def test_duplicate_cross_entity_alias_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            collection = self.build_collection(root, self.write_transcripts(root))
            entities = self.write_entities(root, {"entities": [
                {"id": "one", "name": "实体一", "aliases": ["同名"]},
                {"id": "two", "name": "实体二", "aliases": ["同名"]},
            ]})
            result = run_script(
                "build_mentions.py", "--collection", collection,
                "--entities", entities, "--out", root / "mentions",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("belongs to both", result.stderr)


if __name__ == "__main__":
    unittest.main()
