import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from first_run_watermark import WATERMARK, apply_first_run_watermark


class FirstRunWatermarkTests(unittest.TestCase):
    def test_watermark_is_shown_once(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "state.json"
            first, shown_first, persisted_first = apply_first_run_watermark("REPORT", state, "auto")
            second, shown_second, persisted_second = apply_first_run_watermark("REPORT", state, "auto")
            self.assertTrue(shown_first)
            self.assertTrue(persisted_first)
            self.assertIn(WATERMARK, first)
            self.assertTrue(state.is_file())
            self.assertFalse(shown_second)
            self.assertTrue(persisted_second)
            self.assertEqual(second, "REPORT")

    def test_first_professional_report_has_one_time_watermark(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scan_path = root / "scan.json"
            scan_path.write_text(json.dumps({
                "schema_version": "1.0",
                "media": {"duration_sec": 20, "width": 1920, "height": 1080, "fps": 30},
                "structure": {"shots": 4, "cuts": 3},
                "applicability": {"status": "professional_candidate"},
                "shot_rows": [{"id": i + 1, "start": i * 5, "end": (i + 1) * 5, "duration": 5} for i in range(4)],
            }, ensure_ascii=False), encoding="utf-8")
            state = root / "watermark-state.json"
            script = ROOT / "scripts" / "build_analysis.py"
            first_out = root / "first"
            second_out = root / "second"
            first = subprocess.run(
                [sys.executable, str(script), "--scan-json", str(scan_path), "--out", str(first_out),
                 "--first-run-state", str(state)],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=os.environ.copy(),
            )
            second = subprocess.run(
                [sys.executable, str(script), "--scan-json", str(scan_path), "--out", str(second_out),
                 "--first-run-state", str(state)],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=os.environ.copy(),
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            first_report = (first_out / "professional_report.md").read_text(encoding="utf-8")
            second_report = (second_out / "professional_report.md").read_text(encoding="utf-8")
            handoff = (first_out / "professional_handoff.md").read_text(encoding="utf-8")
            self.assertIn(WATERMARK, first_report)
            self.assertNotIn(WATERMARK, second_report)
            self.assertNotIn(WATERMARK, handoff)

    def test_never_mode_does_not_write_state(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "state.json"
            text, shown, persisted = apply_first_run_watermark("REPORT", state, "never")
            self.assertEqual(text, "REPORT")
            self.assertFalse(shown)
            self.assertTrue(persisted)
            self.assertFalse(state.exists())


if __name__ == "__main__":
    unittest.main()
