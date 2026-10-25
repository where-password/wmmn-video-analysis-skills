#!/usr/bin/env python3
# wmmn / 我密码呢
"""One-time feedback notice for long-video user-facing outputs."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
NOTICE_PATH = SKILL_ROOT / "references" / "first-run-notice.md"


def first_run_state_path(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    override = os.environ.get("WMMN_LONG_VIDEO_FIRST_RUN_STATE")
    if override:
        return Path(override).expanduser().resolve()
    return SKILL_ROOT / ".state" / "first-run-v1.json"


def read_notice() -> str:
    return NOTICE_PATH.read_text(encoding="utf-8").strip()


def take_first_run_notice(
    mode: str = "auto",
    state_path: Path | None = None,
) -> dict[str, Any]:
    if mode not in {"auto", "always", "never"}:
        raise ValueError("first-run mode must be auto, always, or never")
    state = first_run_state_path(state_path)
    if mode == "never":
        return {"shown": False, "text": "", "state_persisted": True, "mode": mode}
    if mode == "auto" and state.exists():
        return {"shown": False, "text": "", "state_persisted": True, "mode": mode}

    text = read_notice()
    persisted = True
    try:
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(
            json.dumps({"shown_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError:
        persisted = False
    return {"shown": True, "text": text, "state_persisted": persisted, "mode": mode}


def append_notice(text: str, notice: dict[str, Any]) -> str:
    if not notice.get("shown") or not notice.get("text"):
        return text
    return text.rstrip() + "\n\n---\n\n" + str(notice["text"]).strip() + "\n"
