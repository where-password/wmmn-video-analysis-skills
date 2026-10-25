import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
                Path(tempfile.gettempdir()) / f"wmmn-long-video-audit-tests-{os.getpid()}.json"
            ),
        },
    )


class AuditInputTests(unittest.TestCase):
    def write_transcripts(self, root):
        first = root / "001.json"
        first.write_text(json.dumps({
            "language": "zh",
            "duration_sec": 90,
            "segments": [
                {"start": 0, "end": 20, "text": "这是第一段课程内容。"},
                {"start": 20, "end": 40, "text": "这是第二段课程内容。"},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        duplicate = root / "001.srt"
        duplicate.write_text("1\n00:00:00,000 --> 00:00:10,000\n重复表示\n", encoding="utf-8")
        second = root / "002.srt"
        second.write_text("1\n00:00:01,000 --> 00:00:05,000\n这是 SRT 内容\n", encoding="utf-8")
        return first, duplicate, second

    def test_audit_lists_three_modes_without_selecting_one(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_transcripts(root)
            out = root / "audit"
            result = run_script("audit_input.py", "--transcripts", root, "--out", out, "--sample-files", 2)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((out / "audit_report.json").is_file())
            report = json.loads((out / "audit_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["no_default_mode"], True)
            self.assertEqual([item["id"] for item in report["modes"]], ["A", "B", "C"])
            self.assertEqual(report["episodes_parsed"], 2)
            self.assertEqual(report["files_scanned"], 2)
            self.assertEqual(report["schema_version"], "1.2")
            self.assertGreater(report["input"]["duration_hours"], 0)
            self.assertIsNotNone(report["system"]["ram_total_gb"])
            self.assertGreater(report["system"]["ram_total_gb"], 0)
            runtime = report["system"]["background_runtime"]
            self.assertTrue(runtime["background_capable"])
            self.assertEqual(runtime["estimated_index_cpu_cores"], 1)
            self.assertGreater(runtime["estimated_machine_cpu_share_percent"], 0)
            self.assertLessEqual(runtime["estimated_machine_cpu_share_percent"], 100)
            for mode in report["modes"]:
                self.assertIn("benefit", mode)
                self.assertTrue(mode["implementation"])
                self.assertEqual(mode["time_scope"], "已有带时间码逐字稿后的解析与索引阶段")
                self.assertTrue(mode["background_run"])
                self.assertFalse(mode["gpu_required"])
                self.assertEqual(
                    mode["estimated_machine_cpu_share_percent"],
                    runtime["estimated_machine_cpu_share_percent"],
                )
            markdown = (out / "audit_report.md").read_text(encoding="utf-8")
            self.assertIn("这里没有默认推荐", markdown)
            self.assertIn("| 档位 | 机器运行估算 | 人工估算 | 磁盘估算 |", markdown)
            self.assertIn("后台运行与机器占用", markdown)
            self.assertIn("理论占比", markdown)
            self.assertIn("C 档只做用户配置别名的确定性匹配", markdown)
            self.assertNotIn("从原始视频到索引的参考", markdown)
            self.assertNotIn("参考基线", markdown)
            try:
                import jsonschema
                schema = json.loads((ROOT / "schemas" / "audit_report.schema.json").read_text(encoding="utf-8"))
                jsonschema.validate(report, schema)
            except ImportError:
                pass

    def test_first_audit_output_has_one_time_watermark(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcript = root / "001.json"
            transcript.write_text(json.dumps({
                "duration_sec": 10,
                "segments": [{"start": 0, "end": 5, "text": "测试语料。"}],
            }, ensure_ascii=False), encoding="utf-8")
            state = root / "watermark-state.json"
            first_out = root / "audit-first"
            second_out = root / "audit-second"
            first = run_script("audit_input.py", "--transcripts", transcript, "--out", first_out, "--first-run-state", state)
            second = run_script("audit_input.py", "--transcripts", transcript, "--out", second_out, "--first-run-state", state)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            first_markdown = (first_out / "audit_report.md").read_text(encoding="utf-8")
            second_markdown = (second_out / "audit_report.md").read_text(encoding="utf-8")
            self.assertIn("wmmn · 我密码呢", first_markdown)
            self.assertIn("反馈提醒", first_markdown)
            self.assertNotIn("wmmn · 我密码呢", second_markdown)

    def test_duration_shortage_is_a_warning_not_a_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcript = root / "001.json"
            transcript.write_text(json.dumps({
                "duration_sec": 5,
                "segments": [{"start": 0, "end": 10, "text": "最后一段超过声明时长。"}],
            }, ensure_ascii=False), encoding="utf-8")
            out = root / "audit"
            result = run_script("audit_input.py", "--transcripts", transcript, "--out", out)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((out / "audit_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["errors"], [])
            self.assertEqual(len(report["duration_warnings"]), 1)
            self.assertAlmostEqual(report["input"]["duration_sec"], 10.0)

    def test_audit_blocks_when_no_transcript(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = run_script("audit_input.py", "--transcripts", root, "--out", root / "audit")
            self.assertEqual(result.returncode, 2)
            self.assertIn("no_transcripts", result.stderr)


if __name__ == "__main__":
    unittest.main()
