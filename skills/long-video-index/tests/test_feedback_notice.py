import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from feedback_notice import append_notice, read_notice, take_first_run_notice


class FeedbackNoticeTests(unittest.TestCase):
    def test_notice_has_forum_douyin_and_privacy_guidance(self):
        notice = read_notice()
        self.assertIn("论坛", notice)
        self.assertIn("抖音私信", notice)
        self.assertIn("我密码呢", notice)
        self.assertIn("wmmn · 我密码呢", notice)
        self.assertIn("测试提醒", notice)
        self.assertIn("`我密码呢`", notice)
        self.assertIn("COMMUNITY.md", notice)
        self.assertIn("Cookie", notice)
        self.assertIn("API Key", notice)

    def test_notice_is_shown_once_per_state(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "state.json"
            first = take_first_run_notice("auto", state)
            second = take_first_run_notice("auto", state)
            self.assertTrue(first["shown"])
            self.assertTrue(first["state_persisted"])
            self.assertTrue(state.is_file())
            self.assertFalse(second["shown"])
            self.assertTrue(second["state_persisted"])

    def test_never_mode_does_not_write_state(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "state.json"
            notice = take_first_run_notice("never", state)
            self.assertFalse(notice["shown"])
            self.assertFalse(state.exists())

    def test_append_notice_is_compact(self):
        text = append_notice("RESULT", {"shown": True, "text": "NOTICE"})
        self.assertEqual(text, "RESULT\n\n---\n\nNOTICE\n")


if __name__ == "__main__":
    unittest.main()
