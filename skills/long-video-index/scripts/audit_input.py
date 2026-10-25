#!/usr/bin/env python3
# wmmn / 我密码呢
"""Audit transcript inputs and estimate long-video corpus costs before building."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from feedback_notice import append_notice, take_first_run_notice
from transcript_io import load_transcript

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def collect_files(path: Path) -> list[Path]:
    path = path.resolve()
    if path.is_file():
        return [path] if path.suffix.lower() in {".json", ".srt", ".vtt"} else []
    if not path.is_dir():
        return []
    candidates = sorted(
        p for p in path.rglob("*")
        if p.is_file() and p.suffix.lower() in {".json", ".srt", ".vtt"}
    )
    # A transcript folder commonly contains JSON, SRT and TXT for the same episode.
    # Keep one preferred representation per episode stem (JSON > VTT > SRT).
    preferred = {".json": 3, ".vtt": 2, ".srt": 1}
    unique: dict[str, Path] = {}
    for item in candidates:
        key = item.with_suffix("").resolve().as_posix()
        previous = unique.get(key)
        if previous is None or preferred[item.suffix.lower()] > preferred[previous.suffix.lower()]:
            unique[key] = item
    return sorted(unique.values())


def human_seconds(value: float) -> str:
    seconds = max(0.0, float(value))
    if seconds < 60:
        return f"{seconds:.1f} 秒"
    if seconds < 3600:
        return f"{seconds / 60:.1f} 分钟"
    return f"{seconds / 3600:.1f} 小时"


def human_range(low: float, high: float) -> str:
    return f"{human_seconds(low)}–{human_seconds(high)}"


def read_memory_info() -> tuple[float | None, float | None]:
    """Read total/available RAM without requiring psutil."""
    if os.name == "nt":
        try:
            import ctypes

            class MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatusEx()
            status.dwLength = ctypes.sizeof(MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return (
                    round(status.ullTotalPhys / 1024**3, 2),
                    round(status.ullAvailPhys / 1024**3, 2),
                )
        except Exception:
            pass

    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        try:
            values: dict[str, int] = {}
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                key, raw = line.split(":", 1)
                values[key] = int(raw.strip().split()[0]) * 1024
            total = values.get("MemTotal")
            available = values.get("MemAvailable")
            return (
                round(total / 1024**3, 2) if total else None,
                round(available / 1024**3, 2) if available else None,
            )
        except Exception:
            pass

    try:
        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        return round(total / 1024**3, 2), None
    except Exception:
        return None, None


def system_info(out: Path) -> dict[str, Any]:
    disk = shutil.disk_usage(out)
    cpu_count = os.cpu_count() or 1
    ram_total_gb, ram_available_gb = read_memory_info()
    cpu_share = round(100.0 / cpu_count, 1)
    info = {
        "os": platform.platform(),
        "python": platform.python_version(),
        "cpu_model": platform.processor() or platform.uname().processor or "未能读取",
        "cpu_count": cpu_count,
        "disk_free_gb": round(disk.free / 1024**3, 2),
        "ram_total_gb": ram_total_gb,
        "ram_available_gb": ram_available_gb,
        "background_runtime": {
            "background_capable": True,
            "estimated_index_cpu_cores": 1,
            "estimated_machine_cpu_share_percent": cpu_share,
            "gpu_required": False,
            "note": (
                f"当前识别到 {cpu_count} 个 CPU 逻辑核心。索引以单进程后台任务为主，"
                f"通常主要使用约 1 个核心，理论上约相当于整机 {cpu_share}%；"
                "实际占用会随逐字稿格式、磁盘和任务阶段变化，不天然占满全部核心。"
            ),
        },
    }
    return info


def benchmark_insert(sample_segments: list[dict[str, Any]]) -> float:
    if not sample_segments:
        return 0.0
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE sample_segments(id INTEGER PRIMARY KEY, start_sec REAL, end_sec REAL, text TEXT)"
        )
        started = time.perf_counter()
        connection.executemany(
            "INSERT INTO sample_segments(start_sec, end_sec, text) VALUES (?, ?, ?)",
            [(row["start"], row["end"], row["text"]) for row in sample_segments],
        )
        connection.commit()
        return time.perf_counter() - started
    finally:
        connection.close()


def audit_transcripts(files: list[Path], sample_count: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    parse_total = 0.0
    for path in files:
        started = time.perf_counter()
        try:
            transcript = load_transcript(path)
            elapsed = time.perf_counter() - started
            parse_total += elapsed
            rows.append({
                "file": path.name,
                "bytes": path.stat().st_size,
                "duration_sec": float(transcript["duration_sec"]),
                "segments": transcript["segments"],
                "parse_sec": elapsed,
                "warnings": transcript.get("duration_warnings", []),
            })
        except Exception as exc:
            errors.append({"file": path.name, "error": str(exc)})
    if not rows:
        raise ValueError("没有可解析的逐字稿；请提供 JSON、SRT 或 VTT")
    # Use an evenly spread sample so large collections do not only benchmark the first files.
    indexes = sorted({round(i * (len(rows) - 1) / max(1, min(sample_count, len(rows)) - 1)) for i in range(min(sample_count, len(rows)))})
    sample_segments = [segment for i in indexes for segment in rows[i]["segments"]]
    sample_insert_sec = benchmark_insert(sample_segments)
    total_segments = sum(len(row["segments"]) for row in rows)
    total_chars = sum(len(segment["text"]) for row in rows for segment in row["segments"])
    total_duration = sum(row["duration_sec"] for row in rows)
    total_bytes = sum(row["bytes"] for row in rows)
    total_mb = total_bytes / 1024**2
    sample_segments_count = max(1, len(sample_segments))
    extrapolated_write = sample_insert_sec * total_segments / sample_segments_count
    # Index parsing plus SQLite writes; the range allows for chunk/section work and slower disks.
    # A conservative floor based on the observed index build rate.
    core_estimate = max(parse_total + extrapolated_write * 1.8, total_segments / 50000)
    estimates = {
        "tier_a": (core_estimate * 0.8, core_estimate * 2.0),
        "tier_b": (core_estimate * 1.0, core_estimate * 2.6),
        "tier_c": (core_estimate * 1.8, core_estimate * 5.0),
    }
    # Collection and single-index outputs duplicate readable text across SQLite,
    # JSONL evidence, and catalog/summary files. Use conservative ratios with
    # an upper margin; C depends heavily on alias/entity count.
    db_mb = max(1.0, total_mb * 3.5, total_segments * 0.00035)
    evidence_mb = max(1.0, total_mb * 5.0)
    tier_a_mb = db_mb + evidence_mb + max(1.0, total_mb * 0.2)
    disk = {
        "tier_a_mb": round(tier_a_mb, 1),
        "tier_b_mb": round(tier_a_mb, 1),
        "tier_c_mb": round(tier_a_mb * 1.1, 1),
    }
    corpus_size = "small" if total_duration < 10 * 3600 else "medium" if total_duration < 50 * 3600 else "large" if total_duration < 200 * 3600 else "very_large"
    return {
        "files_scanned": len(files),
        "episodes_parsed": len(rows),
        "errors": errors,
        "duration_warnings": [warning for row in rows for warning in row.get("warnings", [])],
        "input": {
            "duration_sec": round(total_duration, 3),
            "duration_hours": round(total_duration / 3600, 2),
            "segments": total_segments,
            "characters": total_chars,
            "transcript_mb": round(total_mb, 2),
            "corpus_size": corpus_size,
        },
        "sample": {
            "files_used": len(indexes),
            "segments": sample_segments_count,
            "parse_total_sec": round(parse_total, 3),
            "insert_benchmark_sec": round(sample_insert_sec, 6),
        },
        "estimates_sec": {key: [round(value[0], 3), round(value[1], 3)] for key, value in estimates.items()},
        "disk_estimate_mb": disk,
    }


def mode_options(report: dict[str, Any], system: dict[str, Any]) -> list[dict[str, Any]]:
    estimates = report["estimates_sec"]
    disk = report["disk_estimate_mb"]
    background = system["background_runtime"]
    runtime = {
        "time_scope": "已有带时间码逐字稿后的解析与索引阶段",
        "background_run": background["background_capable"],
        "estimated_cpu_cores": background["estimated_index_cpu_cores"],
        "estimated_machine_cpu_share_percent": background["estimated_machine_cpu_share_percent"],
        "gpu_required": background["gpu_required"],
    }
    return [
        {
            "id": "A",
            "name": "AI 可读取的语料索引",
            "machine_time": human_range(*estimates["tier_a"]),
            "human_time": "0–15 分钟（抽查文件与目录）",
            "disk": f"约 {disk['tier_a_mb']} MB",
            "cpu": f"单进程，约 1 核；当前约整机 {runtime['estimated_machine_cpu_share_percent']}%",
            "memory": "低到中等；无需 GPU",
            "human_effort": "低；通常不需要人工校验",
            "best_for": "把多集课程/访谈整理成可检索的逐字稿数据库，让 AI 在有限上下文中读取和回答。",
            "implementation": "build_collection.py 建立多集语料库，query_collection.py 提供 AI 可读的真实内容检索。",
            "benefit": "低成本缩小检索范围，返回真实内容块、集数、时间码和证据。",
            "limitations": "依赖逐字稿质量；用户自己直接查时体验偏技术；同义词不会自动补齐。",
            **runtime,
        },
        {
            "id": "B",
            "name": "证据定位",
            "machine_time": human_range(*estimates["tier_b"]),
            "human_time": "30 分钟–2 小时（抽查命中与证据）",
            "disk": f"约 {disk['tier_b_mb']} MB",
            "cpu": f"单进程，约 1 核；当前约整机 {runtime['estimated_machine_cpu_share_percent']}%",
            "memory": "低到中等；无需 GPU",
            "human_effort": "中等；需要检查命中片段和证据链",
            "best_for": "用户自己也要按主题、原话和片段学习或查资料。",
            "implementation": "query_collection.py 输出跨集时间范围、原话和证据；默认 Markdown 面向用户。",
            "benefit": "多了用户可读的时间范围、原话和证据引用；适合个人学习。",
            "limitations": "依赖逐字稿质量；命中不等于结论；同义词可能漏检。",
            **runtime,
        },
        {
            "id": "C",
            "name": "跨集实体提及索引",
            "machine_time": human_range(*estimates["tier_c"]),
            "human_time": "数小时–数天（别名、误匹配和结果校验）",
            "disk": f"约 {disk['tier_c_mb']} MB",
            "cpu": f"单进程，约 1 核；如启用实体抽取可能更耗时；基础索引约占整机 {runtime['estimated_machine_cpu_share_percent']}%",
            "memory": "中等；需要额外索引空间",
            "human_effort": "高；别名、误匹配和结果需要校验",
            "best_for": "需要反复查某个工具、人物、技术或术语出现在哪些集和哪些时间点。",
            "implementation": "build_mentions.py 和 query_mentions.py 使用用户提供的实体别名表；不自动发现实体。",
            "benefit": "按用户提供的实体别名，快速定位跨集出现位置、时间范围和原话。",
            "limitations": "别名过宽会误匹配，漏配别名会漏检；结果需要抽查，构建和维护成本最高。",
            **runtime,
        },
    ]


def render_markdown(report: dict[str, Any]) -> str:
    inp = report["input"]
    system = report["system"]
    modes = report["modes"]
    lines = [
        "# 长视频索引成本审计",
        "",
        "> 这是预检报告，不会直接建立索引。请先确认用途，再选择 A/B/C。",
        "",
        "当前脚本已提供多集建库、跨集证据定位和可选别名提及索引。C 档只做用户配置别名的确定性匹配，不自动发现实体。",
        "",
        "## 输入概况",
        "",
        f"- 可解析集数/文件数：{report['episodes_parsed']} / {report['files_scanned']}",
        f"- 总时长：{inp['duration_hours']} 小时（{human_seconds(inp['duration_sec'])}）",
        f"- 逐字稿段数：{inp['segments']}",
        f"- 字符数：{inp['characters']}",
        f"- 逐字稿大小：{inp['transcript_mb']} MB",
        f"- 规模判断：{inp['corpus_size']}",
        f"- 解析失败：{len(report['errors'])}",
        f"- 时长参数警告：{len(report.get('duration_warnings', []))}",
        "",
        "## 机器概况",
        "",
        f"- 系统：{system['os']}",
        f"- Python：{system['python']}",
        f"- CPU：{system['cpu_model']}（{system['cpu_count']} 个逻辑核心）",
        f"- 内存：{system['ram_total_gb'] if system['ram_total_gb'] is not None else '未能读取'} GB"
        + (f"（当前约 {system['ram_available_gb']} GB 可用）" if system.get("ram_available_gb") is not None else ""),
        f"- 输出盘可用空间：{system['disk_free_gb']} GB",
        "",
        "## 后台运行与机器占用",
        "",
        f"- 索引以单进程后台任务为主，通常主要使用约 1 个 CPU 逻辑核心；当前机器约有 {system['background_runtime']['estimated_machine_cpu_share_percent']}% 的整机 CPU 理论占比。",
        "- 可以后台运行，但不是承诺完全不影响电脑；磁盘读写和内存占用会随输入规模变化，其他重任务同时运行时仍可能变慢。",
        "- 不需要 GPU。",
        "",
        "## 先看清时间范围",
        "",
        "- 下面的表只估算“已有逐字稿 -> 索引”的阶段，不是从零处理视频的总时间。",
        "- 如果还没有逐字稿，视频获取、音频提取、ASR 和转写纠错需要另算；这些阶段通常远慢于纯索引。",
        "- 从原始视频开始的完整流程参考写在报告末尾，不能拿来和纯索引时间混用。",
        "",
        "## 三档怎么选",
        "",
        "档位不是越高越好。先看用途，再看成本：",
        "",
        "| 档位 | 适合 | 得到什么 | 主要代价 |",
        "| --- | --- | --- | --- |",
    ]
    for mode in modes:
        lines.append(f"| {mode['id']} · {mode['name']} | {mode['best_for']} | {mode['benefit']} | {mode['limitations']} |")
    lines.extend([
        "",
        "## 三档时间与空间估算",
        "",
        "| 档位 | 机器运行估算 | 人工估算 | 磁盘估算 |",
        "| --- | ---: | ---: | ---: |",
    ])
    for mode in modes:
        lines.append(f"| {mode['id']} · {mode['name']} | {mode['machine_time']} | {mode['human_time']} | {mode['disk']} |")
    lines.extend([
        "",
        "## 估算边界",
        "",
        "- 机器时间是当前电脑的初步估算，不是承诺；CPU、磁盘、内存、逐字稿格式和文件数量都会影响结果。",
        "- C 档磁盘会随实体与别名数量增长；主要成本通常仍是别名准备、误匹配校验和维护。",
        "",
        "## 请选择",
        "",
        "这里没有默认推荐。请根据用途选择，也可以在安装环境中让用户看过本报告后再决定：",
        "",
        "- A：只需要给 AI 读取和检索；成本最低。",
        "- B：自己也要按主题、原话和片段定位；成本中等。",
        "- C：需要跨集查工具/人物/技术提及；成本最高，必须接受校验和维护。",
        "",
    ])
    return "\n".join(lines)


def write_text_atomic(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcripts", required=True, type=Path, help="One transcript file or a directory")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sample-files", type=int, default=3)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--first-run", choices=["auto", "always", "never"], default="auto", help="Control the one-time watermark notice")
    parser.add_argument("--first-run-state", type=Path, default=None, help="Override the first-run marker path")
    args = parser.parse_args()
    files = collect_files(args.transcripts)
    if not files:
        print(json.dumps({"status": "blocked", "reason": "no_transcripts", "detail": "No JSON/SRT/VTT transcript found."}, ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        report = audit_transcripts(files, max(1, args.sample_files))
    except Exception as exc:
        print(json.dumps({"status": "blocked", "reason": "audit_failed", "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "audit_report.json"
    markdown_path = out / "audit_report.md"
    if not args.overwrite and (report_path.exists() or markdown_path.exists()):
        print(json.dumps({"status": "blocked", "reason": "output_exists", "detail": "Pass --overwrite to replace audit_report.md/json."}, ensure_ascii=False), file=sys.stderr)
        return 2
    system = system_info(out)
    payload = {
        "schema_version": "1.2",
        "status": "completed",
        "watermark": {"author": "我密码呢", "mark": "wmmn"},
        "scope": "existing_transcripts_only",
        "system": system,
        "modes": mode_options(report, system),
        "no_default_mode": True,
        **report,
    }
    notice = take_first_run_notice(args.first_run, args.first_run_state)
    if notice["shown"]:
        payload["feedback_notice"] = notice
    report_markdown = append_notice(render_markdown(payload), notice)
    write_text_atomic(report_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    write_text_atomic(markdown_path, report_markdown)
    print(json.dumps({
        "status": "completed",
        "out": str(out),
        "episodes": report["episodes_parsed"],
        "duration_hours": report["input"]["duration_hours"],
        "modes": [mode["id"] for mode in payload["modes"]],
        "default_mode": None,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except (OSError, sqlite3.Error) as exc:
        failure = {
            "status": "blocked",
            "reason": "output_write_failed",
            "detail": str(exc),
            "next_action": "Choose a writable output directory and retry.",
        }
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
