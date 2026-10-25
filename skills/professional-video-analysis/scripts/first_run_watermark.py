#!/usr/bin/env python3
# wmmn / 我密码呢
"""One-time visible watermark for professional report output."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

WATERMARK = "wmmn · 我密码呢"
SKILL_ROOT = Path(__file__).resolve().parent.parent


def first_run_state_path(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    override = os.environ.get("WMMN_PROFESSIONAL_FIRST_RUN_STATE")
    if override:
        return Path(override).expanduser().resolve()
    return SKILL_ROOT / ".state" / "first-run-v1.json"


def apply_first_run_watermark(
    text: str,
    state_path: Path | None = None,
    mode: str = "auto",
) -> tuple[str, bool, bool]:
    if mode not in {"auto", "always", "never"}:
        raise ValueError("first-run mode must be auto, always, or never")
    state = first_run_state_path(state_path)
    if mode == "never":
        return text, False, True
    if mode == "auto" and state.exists():
        return text, False, True
    combined = text.rstrip() + "\n\n---\n\n" + WATERMARK + "\n"
    persisted = True
    try:
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(
            json.dumps({"shown_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError:
        persisted = False
    return combined, True, persisted
