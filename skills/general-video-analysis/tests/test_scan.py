import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from scan import classify, load_media_manifest, normalize_source_url, render_markdown


class ScanUnitTests(unittest.TestCase):
    def test_urls_are_platform_agnostic(self):
        urls = [
            "https://example.com/watch/1",
            "https://example.com/watch/2",
            "https://example.com/watch/3",
        ]
        for url in urls:
            self.assertEqual(normalize_source_url(url), url)

    def test_single_shot_is_not_professional_candidate(self):
        result = classify(60.0, 1, 0)
        self.assertEqual(result["status"], "not_applicable_for_professional_analysis")
        self.assertIn("单镜头", result["headline"])
        self.assertIsNone(result["recommendation"])

    def test_edited_video_recommends_professional_skill(self):
        result = classify(60.0, 5, 4)
        self.assertEqual(result["status"], "professional_candidate")
        self.assertEqual(result["recommendation"]["skill"], "professional-video-analysis")
        self.assertTrue(result["recommendation"]["limits"])

    def test_media_manifest_resolves_relative_media_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            media = root / "video.mp4"
            media.write_bytes(b"demo")
            manifest = root / "media.json"
            manifest.write_text(json.dumps({"media_path": "video.mp4", "provider": "browser_devtools"}), encoding="utf-8")
            resolved, mode = load_media_manifest(manifest)
            self.assertEqual(resolved, media)
            self.assertEqual(mode, "host_media_manifest")

    def test_high_cut_rate_gets_complete_fast_cut_headline(self):
        result = classify(60.27, 58, 57)
        self.assertEqual(result["label"], "fast_cut")
        self.assertIn("高密度快剪", result["headline"])
        self.assertIn("连续切镜", result["headline"])

    def test_source_and_notice_keep_watermark(self):
        root = Path(__file__).resolve().parent.parent
        for rel in ["SKILL.md", "README.md", "NOTICE.md", "agent-manifest.json", "scripts/scan.py"]:
            self.assertIn("wmmn", (root / rel).read_text(encoding="utf-8"))

    def test_user_facing_markdown_keeps_watermark(self):
        payload = {
            "media": {"duration_sec": 60, "width": 1920, "height": 1080, "fps": 30},
            "structure": {"shots": 10, "cuts": 9, "median_shot_sec": 6},
            "applicability": {"headline": "这是一条多镜头视频。", "status": "general_only", "recommendation": None},
        }
        rendered = render_markdown(payload)
        self.assertIn("wmmn · 我密码呢", rendered)


if __name__ == "__main__":
    unittest.main()

