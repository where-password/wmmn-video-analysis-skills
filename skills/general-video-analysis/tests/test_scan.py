import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_overview import apply_first_run_notice, render_overview, validate_content
from scan import classify, load_media_manifest, normalize_source_url, render_blocked_markdown, render_markdown


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
        self.assertNotIn("recommendation", result)

    def test_edited_video_has_internal_professional_signal(self):
        result = classify(60.0, 5, 4)
        self.assertEqual(result["status"], "professional_candidate")
        self.assertTrue(result["internal_only"])
        self.assertNotIn("recommendation", result)

    def test_duration_alone_does_not_create_a_route(self):
        result = classify(30.0, 1, 0, source_duration=7200.0)
        self.assertEqual(result["status"], "not_applicable_for_professional_analysis")
        self.assertTrue(result["internal_only"])
        self.assertNotIn("recommendation", result)

    def test_sampled_window_is_marked_internal(self):
        payload = {
            "media": {"duration_sec": 7200, "width": 1920, "height": 1080, "fps": 30},
            "structure": {
                "window_start_sec": 0.0,
                "window_end_sec": 30.0,
                "window_duration_sec": 30.0,
                "sampled": True,
                "shots": 10,
                "cuts": 9,
                "median_shot_sec": 3.0,
            },
            "applicability": classify(30.0, 10, 9, source_duration=7200.0),
        }
        rendered = render_markdown(payload)
        self.assertIn("内部结构扫描", rendered)
        self.assertIn("本次扫描 0.0–30.0 秒", rendered)
        self.assertIn("不得仅凭时长、镜头数或切点密度", rendered)

    def test_blocked_markdown_is_soft_and_actionable(self):
        rendered = render_blocked_markdown({"detail": "media unavailable"})
        self.assertIn("暂时没有取得", rendered)
        self.assertIn("可以改为提供", rendered)

    def test_media_manifest_resolves_relative_media_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            media = root / "video.mp4"
            media.write_bytes(b"demo")
            manifest = root / "media.json"
            manifest.write_text(json.dumps({"media_path": "video.mp4", "provider": "browser_devtools"}), encoding="utf-8")
            resolved, mode = load_media_manifest(manifest)
            self.assertEqual(resolved, media.resolve())
            self.assertEqual(mode, "host_media_manifest")

    def test_high_cut_rate_gets_complete_fast_cut_headline(self):
        result = classify(60.27, 58, 57)
        self.assertEqual(result["label"], "fast_cut")
        self.assertIn("高密度", result["headline"])
        self.assertIn("多镜头", result["headline"])

    def test_source_and_notice_keep_watermark(self):
        for rel in ["SKILL.md", "README.md", "NOTICE.md", "agent-manifest.json", "scripts/scan.py", "scripts/build_overview.py", "references/first-run-notice.md"]:
            self.assertIn("wmmn", (ROOT / rel).read_text(encoding="utf-8"))

    def test_first_run_notice_has_source_and_copyright_guidance(self):
        notice = (ROOT / "references" / "first-run-notice.md").read_text(encoding="utf-8")
        self.assertIn("历史记录、点赞或收藏", notice)
        self.assertIn("B站", notice)
        self.assertIn("版权", notice)
        self.assertIn("公司、商业", notice)
        self.assertIn("抖音私信", notice)
        self.assertIn("我密码呢", notice)

    def test_first_run_notice_is_appended_once_per_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / ".state" / "first-run-v1.json"
            first, shown_first, persisted_first = apply_first_run_notice("BASE", state, "auto")
            second, shown_second, persisted_second = apply_first_run_notice("BASE", state, "auto")
            self.assertTrue(shown_first)
            self.assertTrue(persisted_first)
            self.assertTrue(state.is_file())
            self.assertTrue(first.startswith("BASE"))
            self.assertIn("视频来源与使用边界", first)
            self.assertFalse(shown_second)
            self.assertTrue(persisted_second)
            self.assertEqual(second, "BASE")

    def test_internal_structure_markdown_keeps_watermark(self):
        payload = {
            "media": {"duration_sec": 60, "width": 1920, "height": 1080, "fps": 30},
            "structure": {"shots": 10, "cuts": 9, "median_shot_sec": 6},
            "applicability": {"headline": "这是一条多镜头视频。", "status": "general_only", "recommendation": None},
        }
        rendered = render_markdown(payload)
        self.assertIn("不直接展示给用户", rendered)
        self.assertIn("wmmn · 我密码呢", rendered)


class OverviewTests(unittest.TestCase):
    def content(self, comic_aigc_led=False, longform_knowledge=False, content_mode="original", content_stance="neutral"):
        data = {
            "schema_version": "1.0",
            "one_sentence": "这是一条关于异地恋沟通问题的口播内容。",
            "summary": "视频借一只狗的贴图形象代替真人出镜，用口播方式讲述一对异地恋情侣因沟通不足产生的矛盾。内容重点落在双方对消息回复速度和安全感的不同理解上。",
            "content_type": ["口播", "情感观点"],
            "themes": ["异地恋", "亲密关系", "沟通"],
            "content_mode": content_mode,
            "content_stance": content_stance,
            "content_tone": ["中性记录"] if content_stance in {"neutral", "unknown"} else ["调侃", "恶搞"],
            "mocking_targets": [] if content_stance in {"neutral", "unknown"} else ["测试对象"],
            "tone_basis": [] if content_stance in {"neutral", "unknown"} else ["测试中的可观察线索"],
            "routing": {
                "comic_aigc_led": comic_aigc_led,
                "longform_knowledge": longform_knowledge,
            },
            "basis": ["video", "transcript"],
        }
        return data

    def test_overview_is_content_first_and_hides_technical_structure(self):
        rendered = render_overview(validate_content(self.content()))
        self.assertIn("# 视频内容概览", rendered)
        self.assertIn("## 一句话总结", rendered)
        self.assertIn("## 内容总结", rendered)
        self.assertIn("异地恋、亲密关系、沟通", rendered)
        for hidden in ["分辨率", "FPS", "镜头数", "切点", "00:00", "关键片段"]:
            self.assertNotIn(hidden, rendered)

    def test_both_professional_directions_are_derived_from_routing(self):
        rendered = render_overview(validate_content(self.content(True, True, "remix", "mocking")))
        self.assertIn("professional-video-analysis", rendered)
        self.assertIn("long-video-index", rendered)
        self.assertIn("可以同时使用", rendered)
        self.assertNotIn("自动调用", rendered)

    def test_remix_does_not_have_to_use_long_video_route(self):
        rendered = render_overview(validate_content(self.content(True, False, "remix", "mocking")))
        self.assertIn("professional-video-analysis", rendered)
        self.assertNotIn("long-video-index", rendered)

    def test_general_meme_gets_tone_and_no_specialist_recommendation(self):
        data = self.content(False, False, "meme", "mocking")
        rendered = render_overview(validate_content(data))
        self.assertIn("## 内容基调", rendered)
        self.assertIn("## 调侃对象", rendered)
        self.assertIn("调侃、恶搞", rendered)
        self.assertNotIn("professional-video-analysis", rendered)
        self.assertNotIn("long-video-index", rendered)

    def test_recommendations_may_be_empty(self):
        rendered = render_overview(validate_content(self.content()))
        self.assertIn("可以结合具体需求再选择专业 Skill", rendered)

    def test_basis_controls_soft_limitation_copy(self):
        rendered = render_overview(validate_content(self.content()))
        self.assertIn("画面、逐字稿", rendered)
        self.assertIn("可能没有覆盖整条视频的全部细节", rendered)

    def test_confirmed_work_and_character_names_are_rendered(self):
        data = self.content(False, False, "meme", "mocking")
        data["ip_context"] = {
            "works": ["奥特曼系列"],
            "characters": ["迪迦", "贝利亚"],
            "people": [],
            "domains": ["特摄", "二次元"],
            "confidence": "high",
            "evidence": ["标题", "标签", "画面角色特征"],
        }
        rendered = render_overview(validate_content(data))
        self.assertIn("## 相关 IP / 人物", rendered)
        self.assertIn("作品/IP：奥特曼系列", rendered)
        self.assertIn("角色：迪迦、贝利亚", rendered)
        self.assertIn("领域：特摄、二次元", rendered)

    def test_people_and_virtual_domains_are_rendered(self):
        data = self.content()
        data["ip_context"] = {
            "works": [],
            "characters": [],
            "people": ["测试人物"],
            "domains": ["说唱", "虚拟主播"],
            "confidence": "medium",
            "evidence": ["用户提供的人物名称"],
        }
        rendered = render_overview(validate_content(data))
        self.assertIn("人物：测试人物", rendered)
        self.assertIn("领域：说唱、虚拟主播", rendered)

    def test_non_neutral_stance_requires_tone_basis(self):
        data = self.content(False, False, "meme", "mocking")
        data["tone_basis"] = []
        with self.assertRaisesRegex(ValueError, "tone_basis"):
            validate_content(data)

    def test_missing_routing_is_rejected(self):
        data = self.content()
        del data["routing"]
        with self.assertRaisesRegex(ValueError, "routing"):
            validate_content(data)

    def test_missing_summary_is_rejected(self):
        data = self.content()
        data["summary"] = ""
        with self.assertRaisesRegex(ValueError, "summary"):
            validate_content(data)

    def test_esports_meme_example_has_no_specialist_recommendation(self):
        data = json.loads((ROOT / "examples" / "content_analysis.example.json").read_text(encoding="utf-8"))
        rendered = render_overview(validate_content(data))
        self.assertIn("## 内容基调", rendered)
        self.assertIn("## 调侃对象", rendered)
        self.assertNotIn("professional-video-analysis", rendered)
        self.assertNotIn("long-video-index", rendered)

    def test_example_matches_rendered_contract(self):
        data = json.loads((ROOT / "examples" / "content_analysis.example.json").read_text(encoding="utf-8"))
        expected = (ROOT / "examples" / "video_overview.example.md").read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertEqual(render_overview(validate_content(data)).replace("\r\n", "\n"), expected)


if __name__ == "__main__":
    unittest.main()
