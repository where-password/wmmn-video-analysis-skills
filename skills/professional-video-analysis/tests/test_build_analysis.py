import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_analysis import build_payload, normalize_content_context, render_handoff, render_markdown, validate_content_route, validate_context


class ProfessionalAnalysisTests(unittest.TestCase):
    def scan(self, status="professional_candidate", shots=4):
        return {
            "schema_version": "1.0",
            "media": {"duration_sec": shots * 5, "width": 1920, "height": 1080, "fps": 30},
            "structure": {"shots": shots, "cuts": max(0, shots - 1)},
            "applicability": {"status": status},
            "shot_rows": [{"id": i + 1, "start": i * 5, "end": (i + 1) * 5, "duration": 5} for i in range(shots)],
        }

    def content_analysis(self, comic_aigc_led=True):
        return {
            "one_sentence": "这是一条关于亲情与选择的短篇漫剧。",
            "content_type": ["短篇情感漫剧", "动画剧情"],
            "themes": ["亲情", "选择"],
            "content_tone": ["叙事", "温情"],
            "content_mode": "original",
            "routing": {"comic_aigc_led": comic_aigc_led, "longform_knowledge": False},
            "ip_context": {
                "works": ["测试作品"],
                "characters": ["测试角色"],
                "people": [],
                "domains": ["动画", "漫剧"],
                "confidence": "medium",
            },
        }

    def test_comic_without_assets_is_not_blocked(self):
        payload = build_payload(self.scan(), {"domain": "comic_drama"})
        self.assertEqual(payload["verdict"]["status"], "structurally_feasible")
        self.assertIn("角色参考", payload["verdict"]["asset_recommendation"])
        self.assertEqual(payload["domain"], "comic_drama")
        self.assertIn("资产情况不作为分析门槛", render_markdown(payload))

    def test_content_analysis_enriches_report_and_handoff(self):
        content_context = normalize_content_context(self.content_analysis())
        payload = build_payload(self.scan(), {"domain": "comic_drama"}, content_context=content_context)
        report = render_markdown(payload)
        handoff = render_handoff(payload)
        self.assertIn("## 内容上下文", report)
        self.assertIn("作品/IP：测试作品", report)
        self.assertIn("角色：测试角色", report)
        self.assertIn("## 内容上下文", handoff)
        self.assertEqual(payload["evidence"]["content_analysis"], "provided")

    def test_content_route_mismatch_requires_explicit_override(self):
        content_context = normalize_content_context(self.content_analysis(comic_aigc_led=False))
        with self.assertRaisesRegex(ValueError, "comic_aigc_led"):
            validate_content_route(content_context, {"domain": "comic_drama"})
        validate_content_route(content_context, {"domain": "comic_drama"}, allow_mismatch=True)

    def test_decision_card_is_actionable_and_at_report_top(self):
        context = {
            "domain": "comic_drama",
            "shots": [{
                "id": shot_id, "scene": "房间", "characters": ["角色"], "action": "走动", "shot_size": "中景",
                "camera": "固定", "transition": "开场", "first_frame": "左", "last_frame": "右",
            } for shot_id in range(1, 6)],
        }
        payload = build_payload(self.scan(shots=6), context)
        report = render_markdown(payload)
        self.assertIn("## 制作决策卡", report)
        self.assertIn("建议下一步", report)
        self.assertEqual(payload["decision_card"]["status"], "ready")
        self.assertIn(1, payload["decision_card"]["priority_shots"])
        self.assertLess(report.index("## 制作决策卡"), report.index("## 内容上下文") if "## 内容上下文" in report else len(report))

    def test_teaching_has_lesson_plan(self):
        payload = build_payload(self.scan(), {"domain": "teaching"})
        self.assertEqual(payload["verdict"]["status"], "partially_feasible")
        self.assertIn("lesson_plan_template", payload["prompt_pack"])

    def test_non_professional_scan_is_insufficient(self):
        payload = build_payload(self.scan("not_applicable_for_professional_analysis", 1), {})
        self.assertEqual(payload["verdict"]["status"], "insufficient_evidence")
        self.assertEqual(payload["domain"], "unknown")

    def test_shot_plan_marks_unobserved_camera(self):
        payload = build_payload(self.scan(), {"domain": "comic_drama", "available_assets": ["角色锚点"]})
        self.assertEqual(payload["shot_plan"][0]["camera"], "not_observed")
        self.assertEqual(payload["shot_plan"][0]["status"], "unverified")

    def test_default_batch_details_five_shots_and_summarizes_rest(self):
        payload = build_payload(self.scan(shots=22), {"domain": "comic_drama", "available_assets": ["角色锚点"]})
        self.assertEqual(payload["batch"]["batch_shot_count"], 5)
        self.assertEqual(payload["batch"]["remaining_shots_est"], 17)
        self.assertEqual(len(payload["shot_plan"]), 5)
        self.assertGreater(len(payload["remaining_segments"]), 0)
        self.assertEqual([item["id"] for item in payload["next_options"]], ["A", "B", "C", "D"])

    def test_continue_batch_uses_next_shot_range(self):
        payload = build_payload(
            self.scan(shots=12),
            {"domain": "comic_drama", "available_assets": ["角色锚点"]},
            detail_start=6,
            detail_count=5,
        )
        self.assertEqual(payload["batch"]["batch_start"], 6)
        self.assertEqual(payload["batch"]["batch_end"], 10)
        self.assertEqual(payload["batch"]["remaining_shots_est"], 2)

    def test_batch_title_and_position_are_dynamic(self):
        payload = build_payload(
            self.scan(shots=12),
            {"domain": "comic_drama", "available_assets": ["角色锚点"]},
            detail_start=6,
            detail_count=5,
        )
        report = render_markdown(payload)
        self.assertIn("第 2 批 · 镜头 6–10", report)
        self.assertIn("此前已有约 5 个镜头", report)
        self.assertNotIn("第 1 批", report)

    def test_prompts_are_assembled_from_observed_fields(self):
        context = {
            "domain": "comic_drama",
            "available_assets": ["角色锚点"],
            "shots": [{
                "id": 1,
                "scene": "夜间房间",
                "characters": ["蓝发角色"],
                "action": "从桌后探头",
                "shot_size": "中景",
                "camera": "固定",
                "transition": "开场",
                "first_frame": "角色藏在桌后",
                "last_frame": "角色露出半张脸",
            }],
        }
        payload = build_payload(self.scan(shots=6), context)
        shot = payload["shot_plan"][0]
        self.assertEqual(shot["status"], "observed")
        self.assertEqual(shot["prompt_source"], "assembled_from_observations")
        self.assertIn("夜间房间", shot["image_prompt"])
        self.assertIn("从桌后探头", shot["motion_prompt"])

    def test_missing_semantic_observations_do_not_create_fake_shot_details(self):
        payload = build_payload(self.scan(shots=6), {"domain": "comic_drama", "available_assets": ["角色锚点"]})
        report = render_markdown(payload)
        self.assertEqual(payload["batch"]["detail_mode"], "structure_only")
        self.assertIn("这批还缺画面观察", report)
        self.assertNotIn("### 镜头 1", report)

    def test_remaining_overview_contains_range_and_rhythm(self):
        payload = build_payload(self.scan(shots=22), {"domain": "comic_drama", "available_assets": ["角色锚点"]})
        first = payload["remaining_segments"][0]
        self.assertEqual(first["shot_range"], "6-15")
        self.assertEqual(first["shot_count"], 10)
        self.assertIn("镜头 6-15", render_markdown(payload))

    def test_missing_shot_rows_fails_with_actionable_message(self):
        scan = self.scan()
        scan.pop("shot_rows")
        with self.assertRaisesRegex(ValueError, "shot_rows"):
            build_payload(scan, {"domain": "comic_drama"})

    def test_detail_start_beyond_last_shot_fails(self):
        with self.assertRaisesRegex(ValueError, "超出"):
            build_payload(self.scan(shots=4), {"domain": "comic_drama"}, detail_start=5)

    def test_mechanics_measurement_fills_missing_camera_and_transition(self):
        mechanics = {
            "status": "completed",
            "shots": [{
                "id": 1,
                "camera": {"label": "画面整体向右平移（疑似横摇或横移）", "confidence": 0.72},
                "transition_in": {"label": "开场（无前序转场）", "confidence": 1.0},
            }],
            "first_transition": {"time_sec": 5.0, "label": "硬切", "confidence": 0.9, "evidence": "measured_visual_transition"},
            "first_camera_movement": {"shot_id": 1, "time_sec": 0.5, "label": "画面整体向右平移（疑似横摇或横移）", "confidence": 0.72},
        }
        context = {
            "domain": "comic_drama",
            "available_assets": ["角色锚点"],
            "shots": [{"id": 1, "scene": "房间", "characters": ["角色"], "action": "走动", "shot_size": "中景", "first_frame": "左侧", "last_frame": "右侧"}],
        }
        payload = build_payload(self.scan(shots=6), context, mechanics=mechanics)
        shot = payload["shot_plan"][0]
        self.assertEqual(shot["camera_source"], "visual_measurement")
        self.assertIn("横移", shot["camera"])
        self.assertEqual(shot["camera_confidence"], 0.72)
        self.assertEqual(payload["analysis_anchors"]["first_transition"]["time_sec"], 5.0)

    def test_negative_prompt_fields_are_absent_and_policy_is_explicit(self):
        payload = build_payload(self.scan(), {"domain": "comic_drama"})
        shot = payload["shot_plan"][0]
        self.assertNotIn("negative_prompt_image", shot)
        self.assertNotIn("negative_prompt_video", shot)
        self.assertNotIn("negative_prompt", shot)
        self.assertIn("不生成负面提示词", payload["negative_prompt_policy"])
        self.assertIn("不生成负面提示词", render_markdown(payload))
        self.assertIn("不生成负面提示词", render_handoff(payload))

    def test_conflicting_long_shot_requires_review(self):
        context = {
            "domain": "comic_drama",
            "available_assets": ["角色锚点"],
            "shots": [{
                "id": 1,
                "scene": "前半在室内机库，末尾转到室外荒漠",
                "characters": ["角色甲", "角色乙"],
                "action": "人物背面全景转到两人并肩，末尾落到近景",
                "shot_size": "全景→中景→近景",
                "camera": "画面基本固定",
                "first_frame": "室内全景",
                "last_frame": "室外近景",
            }],
        }
        payload = build_payload(self.scan(shots=6), context)
        shot = payload["shot_plan"][0]
        self.assertEqual(shot["feasibility"]["status"], "review_required")
        self.assertEqual(shot["feasibility"]["prompt_status"], "needs_resplit")
        self.assertEqual(payload["batch"]["review_required_count"], 1)
        self.assertIn("需要先复核", render_markdown(payload))
        self.assertIn("提示词：暂不展开", render_markdown(payload))
        self.assertNotIn("image_prompt", payload["prompt_pack"]["items"][0])

    def test_handoff_packet_explains_downstream_routes(self):
        payload = build_payload(self.scan(shots=6), {"domain": "comic_drama", "available_assets": ["角色锚点"]})
        report = render_handoff(payload)
        self.assertIn("专业视频逆向拆解交接稿", report)
        self.assertIn("own_workflow", str(payload["handoff"]["downstream_options"]))
        self.assertIn("传统剪辑", report)
        self.assertIn("不要猜", report)

    def test_partial_observation_blocks_prompt_but_keeps_shot_row(self):
        context = {
            "domain": "comic_drama",
            "available_assets": ["角色锚点"],
            "shots": [{"id": 1, "scene": "房间", "action": "人物走动"}],
        }
        payload = build_payload(self.scan(shots=6), context)
        shot = payload["shot_plan"][0]
        self.assertEqual(shot["feasibility"]["prompt_status"], "needs_observation")
        self.assertEqual(payload["batch"]["awaiting_observation_count"], 5)
        self.assertNotIn("image_prompt", payload["prompt_pack"]["items"][0])
        self.assertIn("先补充本镜", render_markdown(payload))

    def test_host_and_measured_camera_conflict_requires_review(self):
        mechanics = {
            "status": "completed",
            "shots": [{"id": 1, "camera": {"label": "画面整体向右平移", "type": "horizontal", "confidence": 0.7}, "transition_in": {"label": "开场", "evidence": "structural"}}],
        }
        context = {
            "domain": "comic_drama",
            "available_assets": ["角色锚点"],
            "shots": [{
                "id": 1, "scene": "房间", "characters": ["角色"], "action": "走动", "shot_size": "中景",
                "camera": "画面基本固定", "transition": "开场", "first_frame": "左", "last_frame": "右",
            }],
        }
        payload = build_payload(self.scan(shots=6), context, mechanics=mechanics)
        codes = [item["code"] for item in payload["shot_plan"][0]["feasibility"]["warnings"]]
        self.assertIn("camera_source_conflict", codes)

    def test_next_batch_count_follows_detail_count(self):
        context = {
            "domain": "comic_drama",
            "available_assets": ["角色锚点"],
            "shots": [{
                "id": 1, "scene": "房间", "characters": ["角色"], "action": "走动", "shot_size": "中景",
                "camera": "固定", "transition": "开场", "first_frame": "左", "last_frame": "右",
            }],
        }
        payload = build_payload(self.scan(shots=22), context, detail_count=3)
        self.assertIn("下一批 3 个镜头", payload["next_options"][0]["label"])

    def test_timecode_evidence_is_exposed_in_report_and_handoff(self):
        context = {
            "domain": "comic_drama",
            "available_assets": ["角色锚点"],
            "shots": [{
                "id": shot_id, "scene": "房间", "characters": ["角色"], "action": "走动", "shot_size": "中景",
                "camera": "固定", "transition": "开场", "first_frame": "左", "last_frame": "右",
            } for shot_id in range(1, 6)],
        }
        evidence = {
            "status": "completed",
            "contact_sheet": {"path": "evidence_contact_sheet.jpg"},
            "shots": [{"id": shot_id, "frames": [{}, {}, {}]} for shot_id in range(1, 6)],
        }
        payload = build_payload(self.scan(shots=6), context, evidence=evidence, evidence_manifest_path=Path("evidence/evidence_manifest.json"))
        self.assertTrue(payload["draft"]["handoff_ready"])
        self.assertTrue(payload["batch"]["semantic_complete"])
        self.assertEqual(payload["batch"]["evidence_covered_shots"], 5)
        self.assertEqual(payload["evidence"]["timecode_frame_count"], 15)
        self.assertIn("已生成 15 张首/中/尾证据帧", render_markdown(payload))
        self.assertIn("时间码证据：provided", render_handoff(payload))

    def test_partial_timecode_evidence_is_not_handoff_ready(self):
        context = {
            "domain": "comic_drama",
            "available_assets": ["角色锚点"],
            "shots": [{
                "id": 1, "scene": "房间", "characters": ["角色"], "action": "走动", "shot_size": "中景",
                "camera": "固定", "transition": "开场", "first_frame": "左", "last_frame": "右",
            }],
        }
        evidence = {
            "status": "completed",
            "contact_sheet": {"path": "evidence_contact_sheet.jpg"},
            "shots": [{"id": 1, "frames": [{}, {}, {}]}],
        }
        payload = build_payload(self.scan(shots=6), context, evidence=evidence)
        self.assertFalse(payload["draft"]["handoff_ready"])
        self.assertEqual(payload["evidence"]["timecode_frames"], "partial")
        self.assertIn("只覆盖 1/5", render_markdown(payload))
        self.assertIn("不能作为完整交接包", render_markdown(payload))

    def test_next_action_never_implies_automatic_continuation(self):
        payload = build_payload(self.scan(shots=12), {"domain": "comic_drama", "available_assets": ["角色锚点"]})
        self.assertIn("不要根据上下文压缩", payload["next_action"])

    def test_context_schema_and_duplicate_ids(self):
        validate_context({"domain": "comic_drama", "shots": [{"id": 1, "scene": "房间"}]})
        with self.assertRaisesRegex(ValueError, "重复"):
            validate_context({"domain": "comic_drama", "shots": [{"id": 1}, {"id": 1}]})
        with self.assertRaisesRegex(ValueError, "不符合 Schema"):
            validate_context({"domain": "comic_drama", "shots": [{"id": "bad"}]})

    def test_rendered_reports_do_not_duplicate_the_visible_watermark(self):
        payload = build_payload(self.scan(), {"domain": "comic_drama"})
        self.assertNotIn("wmmn · 我密码呢", render_markdown(payload))
        self.assertNotIn("wmmn · 我密码呢", render_handoff(payload))

    def test_prompt_notice_is_present(self):
        payload = build_payload(self.scan(), {"domain": "comic_drama"})
        self.assertIn("仅用于分析原视频", payload["prompt_usage_notice"])


if __name__ == "__main__":
    unittest.main()
