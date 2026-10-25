#!/usr/bin/env python3
# wmmn / 我密码呢
"""Render the user-facing video content overview from model-authored analysis."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RECOMMENDATION_TEXT = {
    "professional-video-analysis": (
        "如果你还想进一步拆解制作方式、分镜、节奏或提示词，"
        "可以考虑使用 `professional-video-analysis`。"
    ),
    "long-video-index": (
        "如果你还需要定位原话、章节或具体片段，"
        "也可以使用 `long-video-index`。"
    ),
}
ALLOWED_SKILLS = set(RECOMMENDATION_TEXT)
BASIS_LABELS = {
    "video": "画面",
    "transcript": "逐字稿",
    "audio": "音频",
    "user_context": "用户提供的信息",
}


def text_list(value: Any, field: str, required: bool = False) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    elif value is None:
        items = []
    else:
        raise ValueError(f"{field} 需要是字符串或字符串数组")
    result = [str(item).strip() for item in items if str(item).strip()]
    if required and not result:
        raise ValueError(f"{field} 至少需要一项")
    return result


def validate_content(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("content_analysis.json 需要是一个对象")
    one_sentence = str(data.get("one_sentence") or "").strip()
    summary = str(data.get("summary") or "").strip()
    if not one_sentence:
        raise ValueError("content_analysis.json 缺少 one_sentence")
    if not summary:
        raise ValueError("content_analysis.json 缺少 summary")
    content_type = text_list(data.get("content_type"), "content_type", required=True)
    themes = text_list(data.get("themes"), "themes")
    ip_raw = data.get("ip_context") or {}
    if not isinstance(ip_raw, dict):
        raise ValueError("ip_context 需要是一个对象")
    ip_context = {
        "works": text_list(ip_raw.get("works"), "ip_context.works"),
        "characters": text_list(ip_raw.get("characters"), "ip_context.characters"),
        "people": text_list(ip_raw.get("people"), "ip_context.people"),
        "domains": text_list(ip_raw.get("domains"), "ip_context.domains"),
        "confidence": str(ip_raw.get("confidence") or "unknown").strip(),
        "evidence": text_list(ip_raw.get("evidence"), "ip_context.evidence"),
    }
    if ip_context["confidence"] not in {"high", "medium", "low", "unknown"}:
        raise ValueError("ip_context.confidence 需要是 high、medium、low 或 unknown")
    content_mode = str(data.get("content_mode") or "").strip()
    if content_mode not in {"original", "remix", "meme", "adaptation", "unknown"}:
        raise ValueError("content_mode 需要是 original、remix、meme、adaptation 或 unknown")
    content_stance = str(data.get("content_stance") or "").strip()
    if content_stance not in {"supportive", "critical", "mocking", "neutral", "mixed", "unknown"}:
        raise ValueError("content_stance 需要是 supportive、critical、mocking、neutral、mixed 或 unknown")
    content_tone = text_list(data.get("content_tone"), "content_tone", required=True)
    mocking_targets = text_list(data.get("mocking_targets"), "mocking_targets")
    tone_basis = text_list(data.get("tone_basis"), "tone_basis")
    if content_stance not in {"neutral", "unknown"} and not tone_basis:
        raise ValueError("非中性内容需要提供 tone_basis，说明基调来自哪些可观察线索")
    routing = data.get("routing")
    if not isinstance(routing, dict):
        raise ValueError("content_analysis.json 缺少 routing")
    comic_aigc_led = routing.get("comic_aigc_led")
    longform_knowledge = routing.get("longform_knowledge")
    if not isinstance(comic_aigc_led, bool) or not isinstance(longform_knowledge, bool):
        raise ValueError("routing.comic_aigc_led 和 routing.longform_knowledge 需要是布尔值")
    basis = text_list(data.get("basis"), "basis") or ["video"]
    unknown_basis = [item for item in basis if item not in BASIS_LABELS]
    if unknown_basis:
        raise ValueError(f"basis 包含未知来源：{unknown_basis}")
    recommendations = []
    if comic_aigc_led:
        recommendations.append({"skill": "professional-video-analysis"})
    if longform_knowledge:
        recommendations.append({"skill": "long-video-index"})
    return {
        "one_sentence": one_sentence,
        "summary": summary,
        "content_type": content_type,
        "themes": themes,
        "ip_context": ip_context,
        "content_mode": content_mode,
        "content_stance": content_stance,
        "content_tone": content_tone,
        "mocking_targets": mocking_targets,
        "tone_basis": tone_basis,
        "routing": {
            "comic_aigc_led": comic_aigc_led,
            "longform_knowledge": longform_knowledge,
        },
        "basis": basis,
        "recommendations": recommendations,
    }


def basis_sentence(basis: list[str]) -> str:
    labels = [BASIS_LABELS[item] for item in basis if item in BASIS_LABELS]
    if not labels:
        labels = ["画面"]
    if len(labels) == 1:
        source = labels[0]
    else:
        source = "、".join(labels)
    return f"内容概览基于本次实际读取到的{source}，可能没有覆盖整条视频的全部细节。"


def render_overview(content: dict[str, Any]) -> str:
    recommendations = content["recommendations"]
    if recommendations:
        continue_lines = [
            RECOMMENDATION_TEXT[item["skill"]] for item in recommendations
        ]
        if len(recommendations) > 1:
            continue_lines.append("两个方向可以按需选择，也可以同时使用。")
    else:
        continue_lines = [
            "这份概览可以先用于了解视频内容；如果后续需要更细的制作拆解或片段定位，可以结合具体需求再选择专业 Skill。"
        ]
    themes = "、".join(content["themes"]) if content["themes"] else "暂无法确认"
    lines = [
        "# 视频内容概览",
        "",
        "## 一句话总结",
        "",
        content["one_sentence"],
        "",
        "## 内容总结",
        "",
        content["summary"],
        "",
        "## 内容类型",
        "",
        " · ".join(content["content_type"]),
        "",
        "## 内容主题",
        "",
        themes,
        "",
    ]
    ip_context = content["ip_context"]
    if ip_context["works"] or ip_context["characters"] or ip_context["people"]:
        lines.extend(["## 相关 IP / 人物", ""])
        if ip_context["works"]:
            lines.append(f"- 作品/IP：{'、'.join(ip_context['works'])}")
        if ip_context["characters"]:
            lines.append(f"- 角色：{'、'.join(ip_context['characters'])}")
        if ip_context["people"]:
            lines.append(f"- 人物：{'、'.join(ip_context['people'])}")
        if ip_context["domains"]:
            lines.append(f"- 领域：{'、'.join(ip_context['domains'])}")
        lines.append("")
    lines.extend([
        "## 内容基调",
        "",
        "、".join(content["content_tone"]),
        "",
    ])
    if content["mocking_targets"]:
        lines.extend([
            "## 调侃对象",
            "",
            "、".join(content["mocking_targets"]),
            "",
        ])
    lines.extend([
        "## 可以怎么继续",
        "",
        *continue_lines,
        "",
        "## 说明",
        "",
        f"- {basis_sentence(content['basis'])}",
        "- 本分析聚焦视频内容本身，创作意图、风格优劣和传播效果可以结合具体问题再讨论。",
        "",
    ])
    return "\n".join(lines)


def first_run_state_path(explicit: Path | None = None) -> Path:
    override = os.environ.get("WMMN_FIRST_RUN_STATE")
    if explicit is not None:
        return explicit.resolve()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent.parent / ".state" / "first-run-v1.json"


def read_first_run_notice() -> str:
    path = Path(__file__).resolve().parent.parent / "references" / "first-run-notice.md"
    return path.read_text(encoding="utf-8").strip()


def apply_first_run_notice(text: str, state_path: Path, mode: str = "auto") -> tuple[str, bool, bool]:
    if mode == "never":
        return text, False, True
    if mode == "auto" and state_path.exists():
        return text, False, True
    notice = read_first_run_notice()
    combined = text.rstrip() + "\n\n---\n\n" + notice + "\n"
    persisted = True
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps({"shown_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError:
        persisted = False
    return combined, True, persisted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-json", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--first-run", choices=["auto", "always", "never"], default="auto", help="Append the first-run notice once per installation")
    parser.add_argument("--first-run-state", type=Path, default=None, help="Override the first-run marker path")
    args = parser.parse_args()
    try:
        data = json.loads(args.analysis_json.read_text(encoding="utf-8-sig"))
        content = validate_content(data)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({
            "status": "blocked",
            "reason": "invalid_content_analysis",
            "detail": str(exc),
            "next_action": "Let the model inspect the video evidence and write content_analysis.json before rendering.",
        }, ensure_ascii=False), file=sys.stderr)
        return 2
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    destination = out / "video_overview.md"
    if destination.exists() and not args.overwrite:
        print(json.dumps({
            "status": "blocked",
            "reason": "output_exists",
            "detail": "video_overview.md already exists; pass --overwrite to replace it.",
        }, ensure_ascii=False), file=sys.stderr)
        return 2
    rendered = render_overview(content)
    state_path = first_run_state_path(args.first_run_state)
    rendered, notice_shown, state_persisted = apply_first_run_notice(rendered, state_path, args.first_run)
    destination.write_text(rendered, encoding="utf-8")
    print(json.dumps({
        "status": "completed",
        "out": str(out),
        "artifact": "video_overview.md",
        "first_run_notice": notice_shown,
        "first_run_state_persisted": state_persisted,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
