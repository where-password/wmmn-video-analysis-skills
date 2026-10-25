#!/usr/bin/env python3
# wmmn / 我密码呢
"""Build a progressive professional analysis from a general scan and host context."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any


NEGATIVE_PROMPT_POLICY = "本 Skill 不生成负面提示词。不同生成模型是否需要负面提示、支持哪些字段以及具体表述差异很大，请由用户实际使用的模型或工作流自行判断和甄别。"


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def validate_context(context: dict[str, Any]) -> None:
    try:
        import jsonschema
        from jsonschema import ValidationError
    except ImportError as exc:
        raise RuntimeError("缺少 jsonschema；请先安装 requirements.txt 后再校验 context.json。") from exc
    schema_path = Path(__file__).resolve().parent.parent / "schemas" / "context.schema.json"
    schema = load_json(schema_path)
    try:
        jsonschema.validate(context, schema)
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path) or "<root>"
        raise ValueError(f"context.json 不符合 Schema，位置 {path}：{exc.message}") from exc
    ids = [int(shot["id"]) for shot in context.get("shots", [])]
    duplicates = sorted({shot_id for shot_id in ids if ids.count(shot_id) > 1})
    if duplicates:
        raise ValueError(f"context.json 的镜头 id 重复：{duplicates}")


def validate_evidence_manifest(evidence: dict[str, Any]) -> None:
    try:
        import jsonschema
        from jsonschema import ValidationError
    except ImportError as exc:
        raise RuntimeError("缺少 jsonschema；请先安装 requirements.txt 后再校验证据帧清单。") from exc
    schema_path = Path(__file__).resolve().parent.parent / "schemas" / "evidence_manifest.schema.json"
    schema = load_json(schema_path)
    try:
        jsonschema.validate(evidence, schema)
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path) or "<root>"
        raise ValueError(f"证据帧清单不符合 Schema，位置 {path}：{exc.message}") from exc


def normalize_content_context(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data:
        return None
    routing = data.get("routing")
    if not isinstance(routing, dict):
        raise ValueError("content_analysis.json 缺少 routing")
    comic_aigc_led = routing.get("comic_aigc_led")
    longform_knowledge = routing.get("longform_knowledge")
    if not isinstance(comic_aigc_led, bool) or not isinstance(longform_knowledge, bool):
        raise ValueError("content_analysis.json 的 routing 字段需要是布尔值")
    ip_context = data.get("ip_context")
    if not isinstance(ip_context, dict):
        ip_context = {}
    def strings(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []
    return {
        "one_sentence": str(data.get("one_sentence") or "").strip(),
        "content_type": strings(data.get("content_type")),
        "themes": strings(data.get("themes")),
        "content_tone": strings(data.get("content_tone")),
        "content_mode": str(data.get("content_mode") or "unknown"),
        "comic_aigc_led": comic_aigc_led,
        "longform_knowledge": longform_knowledge,
        "ip_context": {
            "works": strings(ip_context.get("works")),
            "characters": strings(ip_context.get("characters")),
            "people": strings(ip_context.get("people")),
            "domains": strings(ip_context.get("domains")),
            "confidence": str(ip_context.get("confidence") or "unknown"),
        },
    }


def validate_content_route(content_context: dict[str, Any] | None, context: dict[str, Any], allow_mismatch: bool = False) -> None:
    if not content_context:
        return
    domain = str(context.get("domain") or "unknown")
    if domain == "comic_drama" and not content_context.get("comic_aigc_led") and not allow_mismatch:
        raise ValueError(
            "基础层内容分析没有把这条视频标记为 comic_aigc_led=true。"
            "请让用户确认是否仍要按漫剧专业模式分析；确认后可显式传入 --allow-content-mismatch。"
        )


def build_verdict(scan: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    domain = str(context.get("domain") or "unknown")
    applicability = scan.get("applicability") or {}
    structure = scan.get("structure") or {}
    shots = int(structure.get("shots") or 0)
    status = applicability.get("status")
    assets = list(context.get("available_assets") or [])
    asset_recommendation = []
    if domain == "comic_drama" and not assets:
        asset_recommendation = ["角色参考", "场景参考", "道具参考"]
    can_reuse = [
        "镜头数量与切点节奏",
        "每个镜头的时长与先后顺序",
        "联系表提供的视觉抽样",
    ]
    cannot_guarantee = [
        "幽默、网感、个人风格和传播效果",
        "没有领域上下文时的内容正确性",
        "未经宿主观察确认的运镜、转场和画面语义",
    ]
    if status != "professional_candidate" or shots < 2:
        return {
            "status": "insufficient_evidence",
            "headline": "这条视频的镜头结构可能不足以支持专业复刻判断，建议先补充人工观察。",
            "scope": "structural_only",
            "can_reuse": can_reuse,
            "cannot_guarantee": cannot_guarantee,
        }
    if domain == "teaching":
        return {
            "status": "partially_feasible",
            "headline": "大概可以复刻讲解结构和信息组织，但知识点是否正确还需要字幕或课程上下文确认。",
            "scope": "structure_and_lesson_plan",
            "can_reuse": can_reuse + ["章节节奏", "讲解段落拆分方式"],
            "cannot_guarantee": cannot_guarantee + ["教学内容的正确性和完整性"],
        }
    return {
        "status": "structurally_feasible",
        "headline": "从镜头结构看可以进入拆解；如果计划复刻，建议准备角色、场景和道具参考，资产情况不作为分析门槛。",
        "scope": "structure_and_production_plan",
        "can_reuse": can_reuse + (["分镜节奏与首尾帧设计"] if domain == "comic_drama" else []),
        "cannot_guarantee": cannot_guarantee,
        "asset_recommendation": asset_recommendation,
    }


def shot_observations(context: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for item in context.get("shots") or []:
        try:
            result[int(item.get("id"))] = item
        except (TypeError, ValueError):
            continue
    return result


def value_or_missing(value: Any) -> Any:
    if value is None or value == "" or value == []:
        return "not_observed"
    return value


def join_observed(*parts: tuple[str, Any]) -> str:
    values = [
        f"{label}{display(value, fallback='')}"
        for label, value in parts
        if value not in (None, "", [], "not_observed", "unverified")
    ]
    return "；".join(values)


def assemble_prompts(fields: dict[str, Any]) -> dict[str, Any]:
    """Assemble prompts only from supplied observations; never invent visual facts."""
    image_prompt = fields.get("image_prompt")
    if image_prompt == "not_observed":
        image_prompt = join_observed(
            ("场景：", fields.get("scene")),
            ("人物：", fields.get("characters")),
            ("动作：", fields.get("action")),
            ("景别：", fields.get("shot_size")),
            ("运镜：", fields.get("camera")),
            ("首帧：", fields.get("first_frame")),
            ("尾帧：", fields.get("last_frame")),
        ) or "not_observed"

    tool_prompt = fields.get("tool_prompt")
    if tool_prompt == "not_observed":
        tool_prompt = join_observed(
            ("", fields.get("scene")),
            ("人物：", fields.get("characters")),
            ("动作：", fields.get("action")),
            ("景别：", fields.get("shot_size")),
            ("运镜：", fields.get("camera")),
        ) or "not_observed"

    motion_prompt = fields.get("motion_prompt")
    if motion_prompt == "not_observed":
        motion_prompt = join_observed(
            ("动作：", fields.get("action")),
            ("镜头：", fields.get("camera")),
            ("从首帧 ", fields.get("first_frame")),
            ("到尾帧 ", fields.get("last_frame")),
        ) or "not_observed"

    return {
        "image_prompt": image_prompt,
        "tool_prompt": tool_prompt,
        "motion_prompt": motion_prompt,
        "prompt_source": (
            "host"
            if any(fields.get(key) != "not_observed" for key in ("image_prompt", "tool_prompt", "motion_prompt"))
            else "assembled_from_observations"
            if image_prompt != "not_observed"
            else "unavailable"
        ),
    }


def is_unverified_text(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return not text or text in {"not_observed", "unverified"} or "待补充" in text or "未确认" in text or "not observed" in text


def detect_shot_conflicts(shot: dict[str, Any]) -> dict[str, Any]:
    """Flag segmentation/measurement conflicts before treating a row as one promptable shot."""
    scene = display(shot.get("scene"), fallback="")
    action = display(shot.get("action"), fallback="")
    shot_size = display(shot.get("shot_size"), fallback="")
    camera = display(shot.get("camera"), fallback="")
    measured_camera = display(shot.get("measured_camera_label"), fallback="")
    measured_type = str(shot.get("measured_camera_type") or "")
    try:
        duration = float(shot.get("duration_sec") or 0)
    except (TypeError, ValueError):
        duration = 0.0

    warnings: list[dict[str, str]] = []
    framing_change = "→" in shot_size or any(token in shot_size for token in ("转", "变为"))
    scene_change = any(token in scene for token in ("前半", "后半", "末尾", "转到", "变为"))
    staged_action = any(token in action for token in ("转到", "末尾", "然后", "随后", "接着"))

    if shot.get("camera_source") == "host_observation" and measured_camera:
        host_static = "固定" in camera
        measured_moving = measured_type not in {"", "static", "insufficient_frames"}
        if host_static == measured_moving:
            warnings.append({
                "code": "camera_source_conflict",
                "message": "宿主运镜判断与画面运动测量不一致；请复核后再使用运镜描述。",
            })
    if framing_change and "固定" in camera:
        warnings.append({
            "code": "camera_framing_conflict",
            "message": "运镜测为基本固定，但景别发生明显变化；可能漏切、变焦或镜头内调度。",
        })
    if scene_change:
        warnings.append({
            "code": "scene_change_inside_shot",
            "message": "单个检测镜头内出现场景阶段变化；可能把多个镜头合并成了一个。",
        })
    if duration >= 8 and (framing_change or staged_action):
        warnings.append({
            "code": "possible_missed_cut_or_subshot",
            "message": "镜头较长且内部包含阶段变化；复核前不要当作一个可直接生成的单镜。",
        })

    unique = []
    seen = set()
    for warning in warnings:
        if warning["code"] not in seen:
            seen.add(warning["code"])
            unique.append(warning)
    return {
        "status": "review_required" if unique else "draft_ready",
        "prompt_status": "needs_resplit" if unique else "draft_ready",
        "warnings": unique,
    }


def mechanics_by_shot(mechanics: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    result = {}
    for item in (mechanics or {}).get("shots") or []:
        try:
            result[int(item.get("id"))] = item
        except (TypeError, ValueError):
            continue
    return result


def build_shot_plan(
    scan: dict[str, Any],
    context: dict[str, Any],
    mechanics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows = list(scan.get("shot_rows") or [])
    if not rows:
        raise ValueError("quick_scan.json 缺少 shot_rows；请使用 general-video-analysis 0.1.1 或更新版本重新扫描。")
    observed = shot_observations(context)
    measured = mechanics_by_shot(mechanics)
    domain = str(context.get("domain") or "unknown")
    plan = []
    for index, row in enumerate(rows):
        shot_id = int(row.get("id", index + 1))
        item = observed.get(shot_id, {})
        mech = measured.get(shot_id, {})
        camera = value_or_missing(item.get("camera"))
        transition = value_or_missing(item.get("transition"))
        camera_source = "host_observation" if not is_unverified_text(camera) else "unavailable"
        transition_source = "host_observation" if not is_unverified_text(transition) else "unavailable"
        camera_confidence = item.get("camera_confidence")
        transition_confidence = item.get("transition_confidence")

        mech_camera = mech.get("camera") or {}
        measured_camera_label = mech_camera.get("label")
        measured_camera_type = mech_camera.get("type")
        measured_camera_confidence = mech_camera.get("confidence")
        if is_unverified_text(camera) and mech_camera.get("label"):
            camera = mech_camera["label"]
            camera_source = "visual_measurement"
            camera_confidence = mech_camera.get("confidence")
        mech_transition = mech.get("transition_in") or {}
        if is_unverified_text(transition) and mech_transition.get("label"):
            transition = mech_transition["label"]
            transition_source = "structural" if mech_transition.get("evidence") == "structural" else "visual_measurement"
            transition_confidence = mech_transition.get("confidence")
        if shot_id == 1 and is_unverified_text(transition):
            transition = "开场（无前序转场）"
            transition_source = "structural"
            transition_confidence = 1.0

        fields = {
            "scene": value_or_missing(item.get("scene")),
            "characters": value_or_missing(item.get("characters")),
            "action": value_or_missing(item.get("action")),
            "shot_size": value_or_missing(item.get("shot_size")),
            "camera": camera,
            "transition": transition,
            "first_frame": value_or_missing(item.get("first_frame")),
            "last_frame": value_or_missing(item.get("last_frame")),
            "image_prompt": value_or_missing(item.get("image_prompt")),
            "tool_prompt": value_or_missing(item.get("tool_prompt")),
            "motion_prompt": value_or_missing(item.get("motion_prompt")),
        }
        core_fields = ("scene", "characters", "action", "shot_size", "camera", "transition", "first_frame", "last_frame")
        semantic_fields = ("scene", "characters", "action", "shot_size", "camera", "first_frame", "last_frame")
        observed_core = [key for key in core_fields if not is_unverified_text(fields[key])]
        observed_semantic = [key for key in semantic_fields if not is_unverified_text(fields[key])]
        missing_core = [key for key in core_fields if key not in observed_core]
        prompts = assemble_prompts(fields)
        feasibility = detect_shot_conflicts({
            **fields,
            "duration_sec": row.get("duration"),
            "camera_source": camera_source,
            "measured_camera_label": measured_camera_label,
            "measured_camera_type": measured_camera_type,
        })
        if len(observed_semantic) == len(semantic_fields):
            status = "observed"
        elif observed_semantic:
            status = "partially_observed"
        else:
            status = "unverified"
        required_for_prompt = ("scene", "action", "shot_size")
        missing_for_prompt = [key for key in required_for_prompt if is_unverified_text(fields[key])]
        if missing_for_prompt:
            feasibility["warnings"].append({
                "code": "prompt_observation_missing",
                "message": "缺少生成提示词所需的画面、动作或景别观察，暂不生成提示词。",
            })
            if feasibility.get("prompt_status") != "needs_resplit":
                feasibility["prompt_status"] = "needs_observation"
        plan.append({
            "id": shot_id,
            "start_sec": row.get("start"),
            "end_sec": row.get("end"),
            "duration_sec": row.get("duration"),
            **fields,
            **prompts,
            "feasibility": feasibility,
            "camera_source": camera_source,
            "camera_confidence": camera_confidence,
            "camera_measurement_label": measured_camera_label,
            "camera_measurement_type": measured_camera_type,
            "camera_measurement_confidence": measured_camera_confidence,
            "transition_source": transition_source,
            "transition_confidence": transition_confidence,
            "observed_fields": observed_core,
            "missing_fields": missing_core,
            "status": status,
        })
    return plan


def build_remaining_segments(shots: list[dict[str, Any]], size: int = 10) -> list[dict[str, Any]]:
    segments = []
    for offset in range(0, len(shots), max(1, size)):
        group = shots[offset:offset + max(1, size)]
        if not group:
            continue
        durations = [float(item["duration_sec"]) for item in group if item.get("duration_sec") is not None]
        median_duration = round(statistics.median(durations), 3) if durations else None
        if median_duration is None:
            rhythm = "待确认"
        elif median_duration < 1.0:
            rhythm = "大概偏快，短切较多"
        elif median_duration < 3.0:
            rhythm = "大概中等，切镜较快"
        else:
            rhythm = "大概偏稳，镜头较长"
        segments.append({
            "shot_range": f"{group[0]['id']}-{group[-1]['id']}",
            "shot_count": len(group),
            "start_sec": group[0].get("start_sec"),
            "end_sec": group[-1].get("end_sec"),
            "estimated_duration_sec": round(float(group[-1].get("end_sec") or 0) - float(group[0].get("start_sec") or 0), 3),
            "median_shot_sec": median_duration,
            "rhythm_hint": rhythm,
            "status": "estimated_structure",
        })
    return segments


def build_prompt_pack(domain: str, shots: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for shot in shots:
        feasibility = shot.get("feasibility") or {}
        if feasibility.get("prompt_status") in {"needs_resplit", "needs_observation"}:
            messages = "；".join(item["message"] for item in feasibility.get("warnings", []))
            items.append({
                "shot_id": shot["id"],
                "prompt_status": feasibility["prompt_status"],
                "blocked_reason": messages,
                "camera": shot.get("camera"),
                "transition": shot.get("transition"),
                "feasibility": feasibility,
            })
            continue
        generic = shot.get("image_prompt")
        if generic == "not_observed":
            generic = "待补充：场景、人物、动作、景别、构图、光线；请按参考帧填写，不要凭空补角色。"
        tool_prompt = shot.get("tool_prompt")
        if tool_prompt == "not_observed":
            tool_prompt = "待补充：把本镜场景、人物动作、景别和光线压成一段适合目标工具的短提示词。"
        items.append({
            "shot_id": shot["id"],
            "prompt_status": "draft_ready",
            "image_prompt": generic,
            "tool_prompt": tool_prompt,
            "motion_prompt": shot.get("motion_prompt"),
            "camera": shot.get("camera"),
            "camera_confidence": shot.get("camera_confidence"),
            "transition": shot.get("transition"),
            "transition_confidence": shot.get("transition_confidence"),
            "feasibility": feasibility,
            "status": shot["status"],
        })
    result = {
        "domain": domain,
        "items": items,
        "notice": "以下提示词是基于参考视频的逆向拆解草案，仅用于分析原视频的镜头构成。用于自己的作品时，请替换为自有角色、场景和品牌资产，并根据目标工具合理优化；不保证复刻原片。",
        "tool_notes": {
            "image_generation": "按目标图片模型的语法重排画面锚点、动作起点、景别、构图和光线。",
            "video_generation": "按目标视频模型的时长和运动约束重排动作起止、镜头运动和连续性要求。",
            "traditional_editing": "直接使用时间线、切点、景别、运镜和素材需求。",
        },
    }
    if domain == "comic_drama":
        result["image_prompt_template"] = "角色锚点 + 场景 + 本镜动作起点 + 景别 + 构图 + 光线；不把字幕和水印烤进画面。"
        result["motion_prompt_template"] = "开拍即动作：起点姿态 → 中间动作 → 落点；镜头运动必须与宿主观察一致。"
    elif domain == "teaching":
        result["lesson_plan_template"] = "章节 → 概念 → 例子 → 操作步骤 → 练习/总结；每条保留来源时间戳。"
    return result


def build_production_plan(domain: str) -> list[dict[str, str]]:
    common = [
        {"step": "锁定参考结构", "action": "按通用扫描的镜头表建立时间线、时长和切点清单。", "owner": "host"},
        {"step": "准备素材", "action": "准备角色、场景、道具或屏幕素材；没有素材时只输出结构方案。", "owner": "human"},
        {"step": "设计镜头方案", "action": "为每个镜头补全景别、运镜、动作、转场和首尾帧；未观察到的字段不能用猜测填充。", "owner": "host"},
        {"step": "制作关键帧", "action": "按镜头方案生成并逐张验收；角色资产必须绑定身份锚点。", "owner": "host"},
        {"step": "生成与剪辑", "action": "按镜头时长和转场方案生成视频，再做配音、字幕、音效和剪辑。", "owner": "host"},
        {"step": "质量复核", "action": "检查角色一致性、轴线、动作衔接、首尾帧、字幕安全和最终时长。", "owner": "host"},
    ]
    if domain == "comic_drama":
        common.insert(1, {"step": "角色身份锁", "action": "先确认角色主锚点、服装、场景和道具的唯一权威版本，再开始镜头生成。", "owner": "human"})
    elif domain == "teaching":
        common.insert(1, {"step": "知识结构", "action": "先从字幕或课程上下文整理章节、概念、例子和练习，不把镜头节奏当作教学正确性。", "owner": "host"})
    return common


def build_analysis_anchors(all_shots: list[dict[str, Any]], mechanics: dict[str, Any] | None) -> dict[str, Any]:
    first_transition = (mechanics or {}).get("first_transition")
    first_movement = (mechanics or {}).get("first_camera_movement")
    if not first_transition and len(all_shots) > 1:
        first_transition = {
            "time_sec": all_shots[0].get("end_sec"),
            "type": "cut_detected_unknown",
            "label": "检测到首个切点，转场类型未测",
            "confidence": 0.25,
            "evidence": "structural",
        }
    minimal_unit = None
    if first_transition and first_transition.get("time_sec") is not None:
        minimal_unit = {
            "start_sec": 0.0,
            "end_sec": first_transition["time_sec"],
            "label": "先看开场到首个转场的最小分析单元",
        }
    return {
        "first_transition": first_transition,
        "first_camera_movement": first_movement,
        "minimal_first_unit": minimal_unit,
    }


def build_handoff(selected: list[dict[str, Any]], anchors: dict[str, Any], content_context: dict[str, Any] | None = None) -> dict[str, Any]:
    field_labels = {
        "scene": "画面场景",
        "characters": "人物",
        "action": "动作",
        "shot_size": "景别",
        "camera": "运镜",
        "transition": "转场",
        "first_frame": "首帧",
        "last_frame": "尾帧",
    }
    missing_counts: dict[str, int] = {}
    for shot in selected:
        for field in shot.get("missing_fields") or []:
            missing_counts[field] = missing_counts.get(field, 0) + 1
    open_questions = [
        {"field": field, "label": label, "shot_count": missing_counts[field]}
        for field, label in field_labels.items()
        if missing_counts.get(field)
    ]
    review_required_shots = [
        {"shot_id": shot["id"], "warnings": shot.get("feasibility", {}).get("warnings", [])}
        for shot in selected
        if shot.get("feasibility", {}).get("status") == "review_required"
    ]
    return {
        "draft_status": "first_pass_reverse_engineering",
        "purpose": "供用户自己的 AI 工作流、新对话/其他模型或传统剪辑继续深化。",
        "content_context": content_context,
        "analysis_anchors": anchors,
        "open_questions": open_questions,
        "review_required_shots": review_required_shots,
        "downstream_options": [
            {
                "id": "own_workflow",
                "label": "接自己的 AI 工作流",
                "use": "使用逐镜画面提示词、视频提示词、首尾帧、运镜和转场；先处理标记为需复核的镜头。",
            },
            {
                "id": "llm_continuation",
                "label": "交给新对话或其他模型继续",
                "use": "同时提供 professional_handoff.md、professional_analysis.json 和对应参考帧/视频。",
            },
            {
                "id": "traditional_editor",
                "label": "交给传统剪辑",
                "use": "使用时间线、切点、时长、景别、素材需求和参考片。",
            },
        ],
    }


def build_decision_card(
    verdict: dict[str, Any],
    batch: dict[str, Any],
    anchors: dict[str, Any],
    selected: list[dict[str, Any]],
    remaining: list[dict[str, Any]],
    review_required_count: int,
    awaiting_observation_count: int,
    semantic_complete: bool,
    evidence_status: str,
    next_action: str,
    content_context: dict[str, Any] | None,
) -> dict[str, Any]:
    if batch.get("detail_mode") == "structure_only":
        action_status = "needs_observation"
    elif review_required_count:
        action_status = "review_first"
    elif awaiting_observation_count:
        action_status = "needs_observation"
    else:
        action_status = "ready"

    priority_shots = [
        shot["id"]
        for shot in selected
        if shot.get("status") == "observed"
        and (shot.get("feasibility") or {}).get("prompt_status") == "draft_ready"
    ][:3]
    if not priority_shots:
        priority_shots = [shot["id"] for shot in selected[:3]]

    review_ids = [
        shot["id"]
        for shot in selected
        if (shot.get("feasibility") or {}).get("status") == "review_required"
    ]
    risks = []
    if review_ids:
        risks.append(f"镜头 {', '.join(str(shot_id) for shot_id in review_ids)} 需要先复核切分或运镜冲突")
    if awaiting_observation_count:
        risks.append(f"{awaiting_observation_count} 个镜头缺少提示词所需观察")
    if not risks:
        risks.append("当前批次未发现必须暂停的结构性风险")

    minimal_unit = anchors.get("minimal_first_unit")
    if minimal_unit:
        minimum_reproducible_unit = {
            "start_sec": minimal_unit.get("start_sec"),
            "end_sec": minimal_unit.get("end_sec"),
            "label": minimal_unit.get("label"),
        }
    elif selected:
        minimum_reproducible_unit = {
            "start_sec": selected[0]["start_sec"],
            "end_sec": selected[-1]["end_sec"],
            "label": "当前批次的首个可拆单元",
        }
    else:
        minimum_reproducible_unit = None

    return {
        "status": action_status,
        "headline": verdict.get("headline"),
        "content_summary": (content_context or {}).get("one_sentence") if content_context else None,
        "scope": {
            "batch_start": batch.get("batch_start"),
            "batch_end": batch.get("batch_end"),
            "covered_start_sec": batch.get("covered_start_sec"),
            "covered_end_sec": batch.get("covered_end_sec"),
            "remaining_shots": len(remaining),
        },
        "minimum_reproducible_unit": minimum_reproducible_unit,
        "priority_shots": priority_shots,
        "risks": risks,
        "evidence": {
            "semantic_complete": semantic_complete,
            "timecode_frames": evidence_status,
        },
        "asset_preparation": verdict.get("asset_recommendation") or [],
        "next_action": next_action,
    }


def artifact_display_path(path: Path | None) -> str | None:
    if path is None:
        return None
    return path.name if path.is_absolute() else path.as_posix()


def build_payload(
    scan: dict[str, Any],
    context: dict[str, Any],
    detail_start: int = 1,
    detail_count: int = 5,
    mechanics: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    evidence_manifest_path: Path | None = None,
    content_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    domain = str(context.get("domain") or "unknown")
    all_shots = build_shot_plan(scan, context, mechanics)
    requested_index = max(0, detail_start - 1)
    if requested_index >= len(all_shots):
        raise ValueError(f"detail_start={detail_start} 超出检测到的 {len(all_shots)} 个镜头。")
    start_index = requested_index
    selected = all_shots[start_index:start_index + max(1, detail_count)]
    remaining = all_shots[start_index + len(selected):]
    previous_count = len(all_shots[:start_index]) if selected else len(all_shots)
    selected_ids = {int(shot["id"]) for shot in selected}
    evidence_shot_ids = {
        int(item["id"])
        for item in (evidence or {}).get("shots", [])
        if str(item.get("id", "")).isdigit()
    }
    evidence_covered_ids = selected_ids & evidence_shot_ids
    evidence_complete = bool(evidence) and bool(selected_ids) and evidence_covered_ids == selected_ids
    evidence_status = "provided" if evidence_complete else "partial" if evidence else "absent"
    verdict = build_verdict(scan, context)
    semantic_ready_count = sum(1 for shot in selected if shot["status"] != "unverified")
    review_required_count = sum(1 for shot in selected if shot.get("feasibility", {}).get("status") == "review_required")
    awaiting_observation_count = sum(
        1 for shot in selected
        if shot.get("feasibility", {}).get("prompt_status") == "needs_observation"
    )
    semantic_complete = bool(selected) and all(
        shot.get("status") == "observed" and shot.get("feasibility", {}).get("prompt_status") == "draft_ready"
        for shot in selected
    )
    evidence_frame_count = sum(
        len(item.get("frames") or [])
        for item in (evidence or {}).get("shots", [])
        if str(item.get("id", "")).isdigit() and int(item["id"]) in selected_ids
    )
    if review_required_count:
        verdict["headline"] = (
            f"结构大概能拆，但本批有 {review_required_count} 个镜头存在切分或运镜冲突；"
            "需要先复核，不能直接当作单一生成镜头。"
        )
    batch = {
        "batch_index": start_index // max(1, detail_count) + 1,
        "batch_start": selected[0]["id"] if selected else None,
        "batch_end": selected[-1]["id"] if selected else None,
        "batch_shot_count": len(selected),
        "total_shots_detected": len(all_shots),
        "previous_shots_est": previous_count,
        "remaining_shots_est": len(remaining),
        "semantic_ready_shots": semantic_ready_count,
        "semantic_coverage": round(semantic_ready_count / len(selected), 3) if selected else 0,
        "review_required_count": review_required_count,
        "awaiting_observation_count": awaiting_observation_count,
        "evidence_covered_shots": len(evidence_covered_ids),
        "evidence_coverage": round(len(evidence_covered_ids) / len(selected), 3) if selected else 0,
        "timecode_evidence_complete": evidence_complete,
        "semantic_complete": semantic_complete,
        "detail_mode": "semantic" if semantic_ready_count else "structure_only",
        "covered_start_sec": selected[0]["start_sec"] if selected else None,
        "covered_end_sec": selected[-1]["end_sec"] if selected else None,
        "estimated": True,
    }
    next_options = []
    if remaining:
        next_count = max(1, detail_count)
        next_last = remaining[min(next_count - 1, len(remaining) - 1)]["id"]
        next_options = [
            {"id": "A", "label": f"继续拆下一批 {next_count} 个镜头（约镜头 {remaining[0]['id']}-{next_last}）", "action": "continue", "detail_start": remaining[0]["id"], "detail_count": next_count},
            {"id": "B", "label": "指定一个时间段继续拆", "action": "time_range"},
            {"id": "C", "label": "指定一个镜头范围继续拆", "action": "shot_range"},
            {"id": "D", "label": "先不继续，只保留全片结构概览", "action": "stop"},
        ]
    else:
        next_options = [{"id": "D", "label": "本批已经到结尾", "action": "stop"}]
    prompt_pack = build_prompt_pack(domain, selected)
    anchors = build_analysis_anchors(all_shots, mechanics)
    if batch["detail_mode"] == "structure_only" and remaining:
        next_options = [
            {"id": "A", "label": "先补齐本批画面观察，再生成逐镜方案", "action": "observe_current_batch", "detail_start": batch["batch_start"], "detail_count": detail_count},
            {"id": "B", "label": "改拆指定时间段", "action": "time_range"},
            {"id": "C", "label": "改拆指定镜头范围", "action": "shot_range"},
            {"id": "D", "label": "先停止，只保留当前结构概览", "action": "stop"},
        ]
    next_action = (
        (
            "请先让宿主观察本批镜头并补充 context.json，再生成逐镜提示词。"
            if batch["detail_mode"] == "structure_only"
            else "本批有镜头需要先复核切分和运镜冲突，再决定是否继续。"
            if review_required_count
            else f"本批有 {awaiting_observation_count} 个镜头缺少提示词所需观察；补齐后再生成。"
            if awaiting_observation_count
            else "请让用户明确选择 A/B/C/D，再决定是否继续拆解。" if remaining else "本批已经到视频结尾。"
        )
        + (" 不要根据上下文压缩、沉默或前一轮授权自动续拆。" if remaining else "")
    )
    decision_card = build_decision_card(
        verdict, batch, anchors, selected, remaining,
        review_required_count, awaiting_observation_count,
        semantic_complete, evidence_status, next_action, content_context,
    )

    return {
        "schema_version": "1.0",
        "status": "completed",
        "watermark": {"author": "我密码呢", "mark": "wmmn"},
        "domain": domain,
        "source": {
            "goal": context.get("goal"),
            "scan_schema_version": scan.get("schema_version"),
            "duration_sec": (scan.get("media") or {}).get("duration_sec"),
            "width": (scan.get("media") or {}).get("width"),
            "height": (scan.get("media") or {}).get("height"),
            "fps": (scan.get("media") or {}).get("fps"),
            "content_context": content_context,
        },
        "draft": {
            "stage": "first_pass",
            "label": "逆推草稿",
            "handoff_ready": semantic_complete and evidence_complete and review_required_count == 0,
            "handoff_ready_reason": (
                "本批语义观察、复核状态和时间码证据帧均完整"
                if semantic_complete and evidence_complete and review_required_count == 0
                else "存在需要先复核的切分或运镜冲突"
                if review_required_count
                else "缺少本批全部镜头的语义观察"
                if not semantic_complete
                else "缺少覆盖本批全部镜头的时间码证据帧"
                if not evidence_complete
                else "交接条件未满足"
            ),
            "note": "这是可供下一模型或工具继续深化的第一版拆解，不是最终成片方案。",
        },
        "batch": batch,
        "analysis_anchors": anchors,
        "verdict": verdict,
        "shot_plan": selected,
        "remaining_segments": build_remaining_segments(remaining),
        "production_plan": build_production_plan(domain),
        "prompt_pack": prompt_pack,
        "prompt_usage_notice": prompt_pack["notice"],
        "negative_prompt_policy": NEGATIVE_PROMPT_POLICY,
        "next_options": next_options,
        "handoff": build_handoff(selected, anchors, content_context),
        "evidence": {
            "general_scan": "quick_scan.json",
            "context": "host-provided" if context else "absent",
            "mechanics": "measured" if mechanics and mechanics.get("status") == "completed" else "absent",
            "timecode_frames": evidence_status,
            "timecode_evidence_complete": evidence_complete,
            "timecode_evidence_coverage": round(len(evidence_covered_ids) / len(selected), 3) if selected else 0,
            "timecode_shots_covered": len(evidence_covered_ids),
            "timecode_shots_expected": len(selected),
            "timecode_frame_count": evidence_frame_count,
            "evidence_contact_sheet": (evidence or {}).get("contact_sheet", {}).get("path"),
            "evidence_manifest": artifact_display_path(evidence_manifest_path),
            "observed_fields": sorted((context.get("observations") or {}).keys()),
            "content_analysis": "provided" if content_context else "absent",
        },
        "limitations": [
            "This is a structural and production-planning analysis, not an authoritative creative critique.",
            "Camera and transition measurements are visual estimates with confidence; they are not physical rig metadata.",
            "Semantic observations, OCR, and identity consistency must come from the host or another validated analyzer.",
            "A plan does not guarantee asset consistency, humor, net sense, or audience response.",
        ],
        "next_action": next_action,
        "decision_card": decision_card,
    }


def display(value: Any, fallback: str = "待补充") -> str:
    if value is None or value == "" or value == [] or value == "not_observed" or value == "unverified":
        return fallback
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return str(value)


def confidence_label(value: Any, source: Any) -> str:
    if source == "visual_measurement" and isinstance(value, (int, float)):
        return f"（画面实测，置信度 {float(value):.2f}）"
    if source == "host_observation":
        return "（宿主观察）"
    if source == "structural":
        return "（结构事实）"
    return ""


def render_markdown(payload: dict[str, Any]) -> str:
    verdict = payload["verdict"]
    batch = payload["batch"]
    source = payload.get("source") or {}
    status_labels = {
        "structurally_feasible": "可以做（结构层面）",
        "partially_feasible": "部分可做，需要补充素材或上下文",
        "insufficient_evidence": "证据不足，暂不判断",
    }
    batch_start = batch.get("batch_start")
    batch_end = batch.get("batch_end")
    if batch_start is None:
        batch_label = "结构概览"
    else:
        batch_label = f"第 {batch.get('batch_index', 1)} 批 · 镜头 {batch_start}–{batch_end}"
    lines = [
        f"# 专业视频逆向拆解草案 · {batch_label}",
        "",
        "> 这是第一版逆推草稿，不是最终成片方案。观察到的事实、测量值和待确认项是分开的，可交给下一模型、自己的工作流或传统剪辑继续深化。",
        "",
    ]
    decision_card = payload.get("decision_card") or {}
    if decision_card:
        card_status_labels = {
            "ready": "可以继续",
            "review_first": "先复核再继续",
            "needs_observation": "先补充画面观察",
        }
        scope = decision_card.get("scope") or {}
        minimum_unit = decision_card.get("minimum_reproducible_unit") or {}
        lines.extend(["## 制作决策卡", ""])
        lines.append(f"- 当前判断：{decision_card.get('headline') or verdict.get('headline')}")
        lines.append(f"- 当前状态：{card_status_labels.get(decision_card.get('status'), decision_card.get('status'))}")
        if scope:
            lines.append(
                f"- 本批范围：镜头 {scope.get('batch_start')}–{scope.get('batch_end')}，"
                f"约 {scope.get('covered_start_sec')}–{scope.get('covered_end_sec')} 秒"
            )
        if minimum_unit:
            lines.append(
                f"- 最小可复刻单元：约 {minimum_unit.get('start_sec')}–{minimum_unit.get('end_sec')} 秒"
            )
        if decision_card.get("priority_shots"):
            lines.append(f"- 建议优先看：镜头 {', '.join(str(item) for item in decision_card['priority_shots'])}")
        for risk in decision_card.get("risks") or []:
            lines.append(f"- 当前风险：{risk}")
        if decision_card.get("asset_preparation"):
            lines.append(f"- 复刻准备：{'、'.join(decision_card['asset_preparation'])}")
        lines.append(f"- 建议下一步：{decision_card.get('next_action')}")
        lines.append("")
    if source.get("goal"):
        lines.extend([f"目标：{source['goal']}", ""])
    content_context = source.get("content_context") or {}
    if content_context:
        lines.extend(["## 内容上下文", ""])
        if content_context.get("one_sentence"):
            lines.append(f"- 内容判断：{content_context['one_sentence']}")
        if content_context.get("content_type"):
            lines.append(f"- 内容类型：{' · '.join(content_context['content_type'])}")
        ip_context = content_context.get("ip_context") or {}
        if ip_context.get("works"):
            lines.append(f"- 作品/IP：{'、'.join(ip_context['works'])}")
        if ip_context.get("characters"):
            lines.append(f"- 角色：{'、'.join(ip_context['characters'])}")
        if ip_context.get("people"):
            lines.append(f"- 人物：{'、'.join(ip_context['people'])}")
        if content_context.get("content_tone"):
            lines.append(f"- 内容基调：{'、'.join(content_context['content_tone'])}")
        lines.append("")
    lines.append(f"这条视频大约 {source.get('duration_sec')} 秒，检测到约 {batch['total_shots_detected']} 个镜头。")
    if batch_start is not None:
        verb = "计划拆" if batch.get("detail_mode") == "structure_only" else "详细拆"
        lines.append(
            f"本次{verb}镜头 {batch_start}–{batch_end}（共 {batch['batch_shot_count']} 个），"
            f"大概覆盖 {batch['covered_start_sec']}–{batch['covered_end_sec']} 秒。"
        )
        if batch.get("previous_shots_est"):
            lines.append(f"此前已有约 {batch['previous_shots_est']} 个镜头进入过前序批次。")
        if batch.get("remaining_shots_est"):
            lines.append(f"后续还有约 {batch['remaining_shots_est']} 个镜头，先只给结构性分段，不一次性展开。")
        else:
            lines.append("本批大概覆盖到视频结尾。")
    anchors = payload.get("analysis_anchors") or {}
    anchor_prefix = "本批首个" if batch.get("batch_index", 1) > 1 else "首个"
    lines.extend(["", "## 首批锚点", ""])
    first_transition = anchors.get("first_transition")
    if first_transition:
        lines.append(
            f"- {anchor_prefix}转场：约 {first_transition.get('time_sec')} 秒，"
            f"{first_transition.get('label')}{confidence_label(first_transition.get('confidence'), first_transition.get('evidence'))}。"
        )
    else:
        lines.append("- 首个转场：未检测到可确认的镜头边界。")
    first_movement = anchors.get("first_camera_movement")
    if first_movement:
        lines.append(
            f"- {anchor_prefix}明显运镜：镜头 {first_movement.get('shot_id')}，约 {first_movement.get('time_sec')} 秒，"
            f"{first_movement.get('label')}{confidence_label(first_movement.get('confidence'), 'visual_measurement')}。"
        )
    else:
        lines.append("- 首次明显运镜：未测到高置信度运动，或本批没有运镜。")
    minimal_unit = anchors.get("minimal_first_unit")
    if minimal_unit:
        lines.append(
            f"- 想先缩小范围：可以先只看约 {minimal_unit.get('start_sec')}–{minimal_unit.get('end_sec')} 秒，"
            "即开场到首个转场的最小单元。"
        )
    evidence = payload.get("evidence") or {}
    lines.extend(["", "## 时间码证据", ""])
    if evidence.get("timecode_frames") == "provided":
        frame_count = evidence.get("timecode_frame_count") or 0
        lines.append(f"- 已生成 {frame_count} 张首/中/尾证据帧，均带水印和时间码。")
        manifest_path = evidence.get("evidence_manifest")
        if manifest_path:
            lines.append(f"- 证据清单：`{manifest_path}`")
            contact_name = evidence.get("evidence_contact_sheet")
            if contact_name:
                lines.append(f"- 证据联系表：`{contact_name}`")
    elif evidence.get("timecode_frames") == "partial":
        covered = evidence.get("timecode_shots_covered") or 0
        expected = evidence.get("timecode_shots_expected") or 0
        lines.append(f"- 时间码证据只覆盖 {covered}/{expected} 个本批镜头；当前草稿不能作为完整交接包。")
    else:
        lines.append("- 本轮未提供时间码证据包；文字结论仍可阅读，但跨模型交接的追溯性不完整。")
    lines.extend(["", verdict["headline"], "", "## 能不能做", ""])
    lines.append(f"当前判断：**{status_labels.get(verdict['status'], verdict['status'])}**。")
    lines.append("能复用的部分：")
    lines.extend(f"- {item}" for item in verdict["can_reuse"])
    asset_advice = verdict.get("asset_recommendation") or []
    if asset_advice:
        lines.extend(["", "复刻前建议准备：", *[f"- {item}" for item in asset_advice]])

    if batch.get("detail_mode") == "structure_only":
        lines.extend([
            "",
            "## 这批还缺画面观察",
            "",
            "当前只拿到镜头边界和时长，没有拿到本批镜头的画面、人物动作、景别或运镜观察。",
            "为避免把“未观察”包装成专业拆解，这里不编造逐镜内容，也不生成空提示词。",
            "",
            "生成逐镜方案前，需要宿主先查看本批原片或联系表，并把观察到的事实写入 `context.json`。",
        ])
    else:
        review_shots = [
            shot for shot in payload["shot_plan"]
            if (shot.get("feasibility") or {}).get("status") == "review_required"
        ]
        if review_shots:
            lines.extend(["", "## 需要先复核", ""])
            for shot in review_shots:
                messages = "；".join(item["message"].rstrip("。") for item in (shot.get("feasibility") or {}).get("warnings", []))
                lines.append(f"- 镜头 {shot['id']}：{messages}。")
        lines.extend(["", "## 本批详细拆解", ""])
        for shot in payload["shot_plan"]:
            feasibility = shot.get("feasibility") or {}
            if feasibility.get("prompt_status") == "needs_resplit":
                feasibility_text = "需先复核切分/运镜，暂不生成单镜提示词"
            elif feasibility.get("prompt_status") == "needs_observation":
                feasibility_text = "缺少画面、动作或景别观察，暂不生成单镜提示词"
            else:
                feasibility_text = "可作为单镜草案，仍需按目标工具改写"
            observation_lines = [
                f"### 镜头 {shot['id']} · {shot['start_sec']}–{shot['end_sec']} 秒（约 {shot['duration_sec']} 秒）",
                "",
                f"- 画面：{display(shot.get('scene'))}",
                f"- 人物/动作：{display(shot.get('characters'))} / {display(shot.get('action'))}",
                f"- 景别：{display(shot.get('shot_size'))}",
                f"- 运镜：{display(shot.get('camera'))}{confidence_label(shot.get('camera_confidence'), shot.get('camera_source'))}",
                f"- 转场：{display(shot.get('transition'))}{confidence_label(shot.get('transition_confidence'), shot.get('transition_source'))}",
                f"- 首尾帧：{display(shot.get('first_frame'))} → {display(shot.get('last_frame'))}",
            ]
            if feasibility.get("prompt_status") == "needs_resplit":
                observation_lines.extend([
                    "- 提示词：暂不展开。先复核镜头边界或拆出内部子镜，再生成提示词。",
                    f"- 可行性：{feasibility_text}",
                    "",
                ])
            elif feasibility.get("prompt_status") == "needs_observation":
                observation_lines.extend([
                    "- 提示词：暂不展开。先补充本镜的画面、动作和景别观察。",
                    f"- 可行性：{feasibility_text}",
                    "",
                ])
            else:
                observation_lines.extend([
                    f"- 画面提示草案：{display(shot.get('image_prompt'))}",
                    f"- 目标工具简版草案：{display(shot.get('tool_prompt'))}",
                    f"- 动作/运镜草案：{display(shot.get('motion_prompt'))}",
                    f"- 可行性：{feasibility_text}",
                    "",
                ])
            lines.extend(observation_lines)

    lines.extend(["", "## 后续结构概览", ""])
    lines.append("这里只按镜头数量和时长估节奏，不代表已经看懂后续画面内容。")
    for segment in payload["remaining_segments"]:
        lines.append(
            f"- 镜头 {segment['shot_range']}：约 {segment['start_sec']}–{segment['end_sec']} 秒，"
            f"约 {segment['shot_count']} 个镜头，{segment['rhythm_hint']}。"
        )
    if not payload["remaining_segments"]:
        lines.append("- 本批之后没有更多可概览的镜头。")
    lines.extend(["", "## 怎么继续", ""])
    for option in payload["next_options"]:
        lines.append(f"- {option['id']}. {option['label']}")
    handoff = payload.get("handoff") or {}
    lines.extend(["", "## 这份草稿怎么继续用", ""])
    for route in handoff.get("downstream_options") or []:
        lines.append(f"- **{route['label']}**：{route['use']}")
    lines.append("- 交付给其他模型时，请连同 `professional_handoff.md`、`professional_analysis.json` 和对应参考帧/视频一起提供。")
    lines.extend(["", "## 提示词使用说明", "", payload["prompt_usage_notice"], "", "## 不能保证", ""])
    lines.extend(f"- {item}" for item in verdict["cannot_guarantee"])
    lines.extend(["", payload.get("negative_prompt_policy", ""), "", "---", "> wmmn · 我密码呢"])
    return "\n".join(lines) + "\n"

def render_handoff(payload: dict[str, Any]) -> str:
    batch = payload["batch"]
    anchors = payload.get("analysis_anchors") or {}
    handoff = payload.get("handoff") or {}
    lines = [
        "# 专业视频逆向拆解交接稿",
        "",
        "> 这是交给新对话、其他大模型、自己的工作流或剪辑人员的结构化草稿。不要补写未观察到的画面、运镜和转场。",
        "",
        "## 本次范围",
        "",
        f"- 镜头范围：{batch.get('batch_start')}–{batch.get('batch_end')}",
        f"- 时间范围：约 {batch.get('covered_start_sec')}–{batch.get('covered_end_sec')} 秒",
        f"- 全片镜头数：约 {batch.get('total_shots_detected')} 个",
        f"- 草稿阶段：{handoff.get('draft_status', 'first_pass_reverse_engineering')}",
        f"- 时间码证据：{(payload.get('evidence') or {}).get('timecode_frames', 'absent')}",
        "",
    ]
    content_context = (payload.get("source") or {}).get("content_context") or {}
    if content_context:
        lines.extend(["## 内容上下文", ""])
        if content_context.get("one_sentence"):
            lines.append(f"- 内容判断：{content_context['one_sentence']}")
        if content_context.get("content_type"):
            lines.append(f"- 内容类型：{' · '.join(content_context['content_type'])}")
        lines.append("")
    lines.extend([
        "## 首批锚点",
        "",
    ])
    first_transition = anchors.get("first_transition")
    first_movement = anchors.get("first_camera_movement")
    anchor_prefix = "本批首个" if batch.get("batch_index", 1) > 1 else "首个"
    lines.append(
        f"- {anchor_prefix}转场：约 {first_transition.get('time_sec')} 秒，{first_transition.get('label')}"
        if first_transition
        else "- 首个转场：未确认"
    )
    lines.append(
        f"- {anchor_prefix}明显运镜：镜头 {first_movement.get('shot_id')}，约 {first_movement.get('time_sec')} 秒，{first_movement.get('label')}"
        if first_movement
        else "- 首次明显运镜：未测到高置信度运动"
    )
    lines.extend(["", "## 逐镜观察与提示词", ""])
    for shot in payload["shot_plan"]:
        feasibility = shot.get("feasibility") or {}
        shot_lines = [
            f"### 镜头 {shot['id']} · {shot['start_sec']}–{shot['end_sec']} 秒",
            "",
            f"- 画面：{display(shot.get('scene'))}",
            f"- 人物/动作：{display(shot.get('characters'))} / {display(shot.get('action'))}",
            f"- 景别：{display(shot.get('shot_size'))}",
            f"- 运镜：{display(shot.get('camera'))}{confidence_label(shot.get('camera_confidence'), shot.get('camera_source'))}",
            f"- 转场：{display(shot.get('transition'))}{confidence_label(shot.get('transition_confidence'), shot.get('transition_source'))}",
            f"- 首尾帧：{display(shot.get('first_frame'))} → {display(shot.get('last_frame'))}",
        ]
        if feasibility.get("prompt_status") == "needs_resplit":
            shot_lines.extend([
                "- 提示词：暂不展开。先复核镜头边界或拆出内部子镜。",
                f"- 可行性：{feasibility.get('status')}",
                "",
            ])
        elif feasibility.get("prompt_status") == "needs_observation":
            shot_lines.extend([
                "- 提示词：暂不展开。先补充本镜的画面、动作和景别观察。",
                f"- 可行性：{feasibility.get('status')}",
                "",
            ])
        else:
            shot_lines.extend([
                f"- 画面提示草案：{display(shot.get('image_prompt'))}",
                f"- 视频简版草案：{display(shot.get('tool_prompt'))}",
                f"- 动作/运镜草案：{display(shot.get('motion_prompt'))}",
                f"- 可行性：{feasibility.get('status', 'draft_ready')}",
                "",
            ])
        lines.extend(shot_lines)
    open_questions = handoff.get("open_questions") or []
    lines.extend(["## 未解决问题", ""])
    if open_questions:
        for item in open_questions:
            lines.append(f"- {item['label']}：{item['shot_count']} 个镜头仍缺观察，不要猜。")
    else:
        lines.append("- 当前批次的主要字段已经补齐。")
    review_required = handoff.get("review_required_shots") or []
    if review_required:
        lines.extend(["", "## 需要先复核的镜头", ""])
        for item in review_required:
            messages = "；".join(warning["message"].rstrip("。") for warning in item.get("warnings", []))
            lines.append(f"- 镜头 {item['shot_id']}：{messages}。")
    lines.extend(["", "## 下游使用方式", ""])
    for route in handoff.get("downstream_options") or []:
        lines.append(f"- **{route['label']}**：{route['use']}")
    lines.extend([
        "",
        "## 交接要求",
        "",
        "- 把 `professional_analysis.json` 作为机器可读主数据。",
        "- 把本文件作为给其他模型的上下文说明。",
        "- 附上对应时间段的参考帧或视频；只有文字时不得补造画面。",
        "- 提示词仅用于逆向分析和改创草案，自用需替换资产并针对目标工具优化。",
        f"- {payload.get('negative_prompt_policy', NEGATIVE_PROMPT_POLICY)}",
        "",
        "---",
        "> wmmn · 我密码呢",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-json", required=True, type=Path)
    parser.add_argument("--context-json", type=Path, default=None)
    parser.add_argument("--content-analysis-json", type=Path, default=None, help="Content overview from general-video-analysis")
    parser.add_argument("--allow-content-mismatch", action="store_true", help="Allow professional analysis when base routing says comic_aigc_led=false")
    parser.add_argument("--mechanics-json", type=Path, default=None, help="Output from media_mechanics.py")
    parser.add_argument("--evidence-json", type=Path, default=None, help="Output from evidence_frames.py")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--detail-start", type=int, default=1, help="First shot number to detail")
    parser.add_argument("--detail-count", type=int, default=5, help="Number of shots to detail")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    try:
        scan = load_json(args.scan_json)
        context = load_json(args.context_json)
        if args.context_json is not None:
            validate_context(context)
        content_context = normalize_content_context(load_json(args.content_analysis_json))
        validate_content_route(content_context, context, args.allow_content_mismatch)
        mechanics = load_json(args.mechanics_json)
        evidence = load_json(args.evidence_json)
        if args.evidence_json is not None:
            validate_evidence_manifest(evidence)
        payload = build_payload(
            scan,
            context,
            args.detail_start,
            args.detail_count,
            mechanics,
            evidence,
            args.evidence_json,
            content_context,
        )
        (args.out / "professional_analysis.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.out / "professional_report.md").write_text(render_markdown(payload), encoding="utf-8")
        (args.out / "professional_handoff.md").write_text(render_handoff(payload), encoding="utf-8")
    except Exception as exc:
        failure = {"status": "blocked", "reason": "analysis_failed", "detail": str(exc)}
        (args.out / "professional_analysis.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"status": "completed", "out": str(args.out), "verdict": payload["verdict"]["status"]}, ensure_ascii=False))
    print()
    print(render_markdown(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

