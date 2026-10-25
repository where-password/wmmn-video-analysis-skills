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
from transcript_io import TranscriptError, load_transcript
from build_index import coverage_stats
from locate import query_terms


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


class LongVideoIndexTests(unittest.TestCase):
    def make_transcript(self, root):
        path = root / "transcript.json"
        path.write_text(json.dumps({
            "language": "zh",
            "duration_sec": 3720,
            "segments": [
                {"id": "a", "start": 0, "end": 20, "text": "开场介绍长视频索引。"},
                {"id": "b", "start": 2415, "end": 2448, "text": "每个结果都要有时间码、原文和证据哈希。"},
                {"id": "c", "start": 3000, "end": 3031, "text": "这样才形成可复核的证据链。"},
                {"id": "d", "start": 3602, "end": 3634, "text": "定位后再决定是否交给专业拆解。"},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        return path

    def build(self, root, transcript):
        out = root / "index"
        chapters = root / "chapters.json"
        chapters.write_text(json.dumps({"chapters": [
            {"title": "方法", "start": 0, "end": 1200},
            {"title": "证据链", "start": 1200, "end": 3720},
        ]}, ensure_ascii=False), encoding="utf-8")
        result = run_script("build_index.py", "--transcript", transcript, "--chapters", chapters, "--source-title", "测试课程", "--out", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        return out

    def test_build_index_and_evidence_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = self.build(root, self.make_transcript(root))
            for name in ["long_video_index.json", "long_video_index.sqlite", "evidence.jsonl", "index_outline.md"]:
                self.assertTrue((out / name).is_file(), name)
            index = json.loads((out / "long_video_index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["status"], "completed")
            self.assertEqual(index["counts"]["segments"], 4)
            self.assertEqual([section["title"] for section in index["sections"]], ["方法", "证据链"])
            for line in (out / "evidence.jsonl").read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                self.assertEqual(hashlib.sha256(row["quote"].encode("utf-8")).hexdigest(), row["quote_sha256"])
            try:
                import jsonschema
                schema = json.loads((ROOT / "schemas" / "long_video_index.schema.json").read_text(encoding="utf-8"))
                jsonschema.validate(index, schema)
            except ImportError:
                pass

    def test_locate_returns_exact_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = self.build(root, self.make_transcript(root))
            result = run_script("locate.py", "--index", out, "--query", "时间码 证据", "--limit", 3, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "completed")
            self.assertGreaterEqual(payload["hit_count"], 1)
            citation = payload["hits"][0]["citations"][0]
            self.assertIn("时间码", citation["quote"])
            self.assertIn("证据", citation["quote"])
            self.assertEqual(hashlib.sha256(citation["quote"].encode("utf-8")).hexdigest(), citation["quote_sha256"])
            self.assertEqual(payload["transcript_sha256"], json.loads((out / "long_video_index.json").read_text(encoding="utf-8"))["source"]["transcript_sha256"])
            try:
                import jsonschema
                schema = json.loads((ROOT / "schemas" / "locate_result.schema.json").read_text(encoding="utf-8"))
                jsonschema.validate(payload, schema)
            except ImportError:
                pass

    def test_locate_time_filter_and_no_match(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = self.build(root, self.make_transcript(root))
            hit = run_script("locate.py", "--index", out, "--query", "证据链", "--start", 2990, "--end", 3050, "--json")
            self.assertEqual(hit.returncode, 0, hit.stderr)
            self.assertEqual(json.loads(hit.stdout)["hit_count"], 1)
            missing = run_script("locate.py", "--index", out, "--query", "完全不存在的词", "--json")
            self.assertEqual(missing.returncode, 0, missing.stderr)
            self.assertEqual(json.loads(missing.stdout)["status"], "no_matches")

    def test_index_summary_database_mismatch_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = self.build(root, self.make_transcript(root))
            index_path = out / "long_video_index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["duration_sec"] = 9999
            index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
            result = run_script("locate.py", "--index", out, "--query", "证据", "--json")
            self.assertEqual(result.returncode, 2)
            self.assertIn("do not match", result.stderr)

    def test_coverage_uses_interval_union_and_counts_edge_gaps(self):
        coverage = coverage_stats([
            {"start": 100.0, "end": 200.0},
            {"start": 120.0, "end": 150.0},
            {"start": 210.0, "end": 300.0},
        ], 400.0)
        self.assertAlmostEqual(coverage["speech_sec"], 190.0)
        self.assertAlmostEqual(coverage["coverage_ratio"], 0.475)
        self.assertAlmostEqual(coverage["largest_gap_sec"], 100.0)
        self.assertEqual(coverage["gaps_over_10s"], 3)

    def test_time_filter_excludes_citations_outside_requested_window(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcript = root / "window.json"
            transcript.write_text(json.dumps({
                "duration_sec": 3720,
                "segments": [
                    {"id": "a", "start": 0, "end": 5, "text": "共同词出现在前段。"},
                    {"id": "b", "start": 20, "end": 25, "text": "共同词也出现在后段。"},
                ],
            }, ensure_ascii=False), encoding="utf-8")
            out = self.build(root, transcript)
            result = run_script(
                "locate.py", "--index", out, "--query", "共同词",
                "--start", "0", "--end", "10", "--json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["hit_count"], 1)
            citations = payload["hits"][0]["citations"]
            self.assertEqual([citation["segment_id"] for citation in citations], ["a"])
            self.assertLessEqual(payload["hits"][0]["end_sec"], 10)

    def test_tampered_evidence_quote_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = self.build(root, self.make_transcript(root))
            connection = sqlite3.connect(out / "long_video_index.sqlite")
            try:
                connection.execute(
                    "UPDATE segments SET text = ? WHERE segment_id = ?",
                    ("被篡改的原话", "b"),
                )
                connection.commit()
            finally:
                connection.close()
            result = run_script("locate.py", "--index", out, "--query", "证据", "--json")
            self.assertEqual(result.returncode, 2)
            self.assertIn("Evidence quote hash mismatch", result.stderr)

    def test_failed_overwrite_keeps_existing_index(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = self.build(root, self.make_transcript(root))
            names = ["long_video_index.json", "long_video_index.sqlite", "evidence.jsonl", "index_outline.md"]
            before = {(out / name): hashlib.sha256((out / name).read_bytes()).hexdigest() for name in names}
            bad = root / "bad.json"
            bad.write_text(json.dumps({
                "duration_sec": 10,
                "segments": [{"start": 5, "end": 3, "text": "无效"}],
            }, ensure_ascii=False), encoding="utf-8")
            result = run_script("build_index.py", "--transcript", bad, "--out", out, "--overwrite")
            self.assertEqual(result.returncode, 2)
            for path, digest in before.items():
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_query_terms_are_casefold_deduplicated(self):
        self.assertEqual(query_terms("TV tv 电视, TV"), ["TV", "电视"])

    def test_non_finite_chunk_options_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcript = self.make_transcript(root)
            result = run_script(
                "build_index.py", "--transcript", transcript, "--out", root / "index",
                "--target-chunk-sec", "nan",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("must be finite", result.stderr)

    def test_srt_and_vtt_parsing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            srt = root / "sample.srt"
            srt.write_text("1\n00:00:01,250 --> 00:00:03,500\n第一句\n\n2\n00:00:04,000 --> 00:00:06,000\n第二句\n", encoding="utf-8")
            parsed = load_transcript(srt)
            self.assertEqual(parsed["segments"][0]["start"], 1.25)
            self.assertEqual(parsed["segments"][1]["end"], 6.0)
            vtt = root / "sample.vtt"
            vtt.write_text("WEBVTT\n\n00:01.000 --> 00:03.000\nHello evidence\n", encoding="utf-8")
            parsed_vtt = load_transcript(vtt)
            self.assertEqual(parsed_vtt["segments"][0]["text"], "Hello evidence")

    def test_invalid_and_non_timestamped_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            txt = root / "plain.txt"
            txt.write_text("没有时间码的逐字稿", encoding="utf-8")
            with self.assertRaises(TranscriptError):
                load_transcript(txt)
            bad = root / "bad.json"
            bad.write_text(json.dumps({"segments": [{"start": 4, "end": 2, "text": "bad"}]}), encoding="utf-8")
            with self.assertRaises(TranscriptError):
                load_transcript(bad)

    def test_rebuild_requires_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcript = self.make_transcript(root)
            out = self.build(root, transcript)
            second = run_script("build_index.py", "--transcript", transcript, "--out", out)
            self.assertNotEqual(second.returncode, 0)
            overwritten = run_script("build_index.py", "--transcript", transcript, "--out", out, "--overwrite")
            self.assertEqual(overwritten.returncode, 0, overwritten.stderr)


if __name__ == "__main__":
    unittest.main()
