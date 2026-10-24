import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_benchmark import evaluate_case, evaluate_stability, match_cuts


class BenchmarkTests(unittest.TestCase):
    def test_cut_matching_within_tolerance(self):
        result = match_cuts([1.0, 2.1, 4.0], [1.05, 2.0], 0.15)
        self.assertEqual(result["matched_count"], 2)
        self.assertEqual(result["precision"], round(2 / 3, 4))
        self.assertEqual(result["recall"], 1.0)

    def test_cut_matching_rejects_outside_tolerance(self):
        result = match_cuts([1.0, 2.5], [1.0, 2.0], 0.1)
        self.assertEqual(result["matched_count"], 1)
        self.assertGreater(result["miss_rate"], 0)

    def test_case_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scan = {
                "shot_rows": [
                    {"id": 1, "start": 0.0, "end": 2.05},
                    {"id": 2, "start": 2.05, "end": 4.0},
                ]
            }
            mechanics = {
                "shots": [
                    {"id": 1, "camera": {"type": "static"}, "transition_in": {"type": "opening"}},
                    {"id": 2, "camera": {"type": "horizontal"}, "transition_in": {"type": "hard_cut"}},
                ]
            }
            (root / "scan.json").write_text(json.dumps(scan), encoding="utf-8")
            (root / "mechanics.json").write_text(json.dumps(mechanics), encoding="utf-8")
            case = {
                "id": "case-1",
                "scan_json": "scan.json",
                "mechanics_json": "mechanics.json",
                "ground_truth": {
                    "cuts": [2.0],
                    "shots": [
                        {"id": 1, "camera": "static", "transition_in": "opening"},
                        {"id": 2, "camera": "horizontal", "transition_in": "hard_cut"},
                    ],
                },
            }
            result = evaluate_case(case, root, 0.1)
            self.assertEqual(result["cuts"]["f1"], 1.0)
            self.assertEqual(result["camera"]["accuracy"], 1.0)
            self.assertEqual(result["transition"]["accuracy"], 1.0)

    def test_stability_group(self):
        results = [
            {"id": "a", "group_id": "g", "variant": "base", "cuts": {"predicted_count": 3, "f1": 1.0}, "camera": {"accuracy": 1.0}, "transition": {"accuracy": 1.0}},
            {"id": "b", "group_id": "g", "variant": "720p", "cuts": {"predicted_count": 3, "f1": 1.0}, "camera": {"accuracy": 0.8}, "transition": {"accuracy": 1.0}},
        ]
        stability = evaluate_stability(results)
        self.assertEqual(len(stability), 1)
        self.assertGreater(stability[0]["stability_score"], 0.9)


if __name__ == "__main__":
    unittest.main()
