import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from evidence_frames import annotate_frame, candidate_times, make_contact_sheet, timecode


class EvidenceFrameTests(unittest.TestCase):
    def test_timecode(self):
        self.assertEqual(timecode(0), "00:00:00.000")
        self.assertEqual(timecode(65.4321), "00:01:05.432")

    def test_candidate_times_are_inside_shot(self):
        times = candidate_times(10.0, 12.0)
        self.assertEqual([role for role, _ in times], ["start", "middle", "end"])
        self.assertTrue(all(10.0 < seconds < 12.0 for _, seconds in times))
        self.assertLessEqual(times[0][1], times[1][1])
        self.assertLessEqual(times[1][1], times[2][1])

    def test_annotate_frame_keeps_shot_metadata_bar(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frame.jpg"
            Image.new("RGB", (320, 180), (40, 80, 120)).save(path)
            width, height = annotate_frame(path, 3, "middle", 12.345)
            self.assertEqual(width, 320)
            self.assertGreater(height, 180)
            self.assertTrue(path.exists())

    def test_contact_sheet_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames = []
            for index in range(3):
                path = root / f"{index}.jpg"
                Image.new("RGB", (320, 180), (index * 40, 60, 120)).save(path)
                frames.append({"absolute_path": str(path)})
            out = root / "sheet.jpg"
            width, height = make_contact_sheet(frames, out)
            self.assertGreater(width, 0)
            self.assertGreater(height, 0)
            self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
