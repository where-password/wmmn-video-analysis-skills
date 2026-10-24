import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from media_mechanics import analyze_motion, classify_transition, phase_shift


class MediaMechanicsTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7)
        self.texture = rng.normal(100, 30, (128, 128)).astype(np.float32)

    def test_phase_shift_reports_direction(self):
        shifted = np.roll(self.texture, 4, axis=1)
        dx, dy, confidence = phase_shift(self.texture, shifted)
        self.assertGreater(dx, 3.0)
        self.assertAlmostEqual(dy, 0.0, places=1)
        self.assertGreater(confidence, 0.5)

    def test_static_sequence_is_static(self):
        result = analyze_motion(np.stack([self.texture for _ in range(5)]), 4.0, 0.0)
        self.assertEqual(result["type"], "static")
        self.assertGreaterEqual(result["confidence"], 0.5)

    def test_horizontal_sequence_is_horizontal(self):
        frames = np.stack([np.roll(self.texture, index * 2, axis=1) for index in range(5)])
        result = analyze_motion(frames, 4.0, 0.0)
        self.assertEqual(result["type"], "horizontal")
        self.assertEqual(result["direction"], "right")
        self.assertIsNotNone(result["first_motion_sec"])

    def test_apparent_zoom_out(self):
        base = Image.new("L", (256, 256), 30)
        draw = ImageDraw.Draw(base)
        for x in range(0, 256, 32):
            draw.line((x, 0, x, 255), fill=220, width=3)
        for y in range(0, 256, 32):
            draw.line((0, y, 255, y), fill=180, width=3)
        draw.ellipse((70, 50, 190, 210), fill=100, outline=255, width=4)
        frames = []
        for scale in (1.0, 0.97, 0.94, 0.91, 0.88, 0.85):
            image = base.resize((int(256 * scale), int(256 * scale)))
            canvas = Image.new("L", (256, 256), 0)
            canvas.paste(image, ((256 - image.width) // 2, (256 - image.height) // 2))
            frames.append(np.asarray(canvas, dtype=np.float32))
        result = analyze_motion(np.stack(frames), 4.0, 0.0)
        self.assertEqual(result["type"], "apparent_zoom_out")

    def test_hard_cut(self):
        frames = np.stack(
            [np.full((64, 64), 30, dtype=np.float32) for _ in range(5)]
            + [np.full((64, 64), 210, dtype=np.float32) for _ in range(5)]
        )
        result = classify_transition(frames, 0.6, 8.0)
        self.assertEqual(result["type"], "hard_cut")
        self.assertGreater(result["confidence"], 0.7)

    def test_fade_through_black(self):
        levels = np.linspace(180, 0, 5).tolist() + np.linspace(0, 180, 5).tolist()
        frames = np.stack([np.full((64, 64), level, dtype=np.float32) for level in levels])
        result = classify_transition(frames, 0.6, 8.0)
        self.assertEqual(result["type"], "fade_through_black")

    def test_flash(self):
        levels = [100, 100, 100, 100, 250, 100, 100, 100, 100]
        frames = np.stack([np.full((64, 64), level, dtype=np.float32) for level in levels])
        result = classify_transition(frames, 0.5, 8.0)
        self.assertEqual(result["type"], "flash")


if __name__ == "__main__":
    unittest.main()
