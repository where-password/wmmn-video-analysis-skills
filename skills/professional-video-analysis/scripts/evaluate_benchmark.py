#!/usr/bin/env python3
# wmmn / 我密码呢
"""Evaluate scan and mechanics predictions against human-labeled benchmark cases."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_cases_manifest(manifest: dict[str, Any]) -> None:
    try:
        import jsonschema
        from jsonschema import ValidationError
    except ImportError as exc:
        raise RuntimeError("缺少 jsonschema；请先安装 requirements.txt。") from exc
    schema_path = Path(__file__).resolve().parent.parent / "schemas" / "benchmark_cases.schema.json"
    schema = load_json(schema_path)
    try:
        jsonschema.validate(manifest, schema)
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path) or "<root>"
        raise ValueError(f"基准用例清单不符合 Schema，位置 {path}：{exc.message}") from exc


def resolve_path(value: str, base: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def predicted_cuts(scan: dict[str, Any]) -> list[float]:
    rows = sorted(scan.get("shot_rows") or [], key=lambda row: int(row.get("id", 0)))
    return [round(float(row["start"]), 3) for row in rows[1:] if row.get("start") is not None]


def match_cuts(predicted: list[float], truth: list[float], tolerance: float) -> dict[str, Any]:
    used: set[int] = set()
    matches = []
    for expected in sorted(truth):
        candidates = [
            (abs(candidate - expected), index)
            for index, candidate in enumerate(predicted)
            if index not in used and abs(candidate - expected) <= tolerance
        ]
        if candidates:
            error, index = min(candidates)
            used.add(index)
            matches.append({"truth": expected, "predicted": predicted[index], "error_sec": round(error, 3)})
    matched = len(matches)
    precision = matched / len(predicted) if predicted else (1.0 if not truth else 0.0)
    recall = matched / len(truth) if truth else (1.0 if not predicted else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "truth_count": len(truth),
        "predicted_count": len(predicted),
        "matched_count": matched,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "miss_rate": round(1 - recall, 4),
        "false_positive_rate": round(1 - precision, 4),
        "mean_abs_error_sec": round(statistics.mean(item["error_sec"] for item in matches), 3) if matches else None,
        "matches": matches,
    }


def prediction_maps(mechanics: dict[str, Any] | None) -> tuple[dict[int, str], dict[int, str]]:
    camera: dict[int, str] = {}
    transition: dict[int, str] = {}
    for shot in (mechanics or {}).get("shots") or []:
        try:
            shot_id = int(shot.get("id"))
        except (TypeError, ValueError):
            continue
        camera[shot_id] = str((shot.get("camera") or {}).get("type") or "unknown")
        transition[shot_id] = str((shot.get("transition_in") or {}).get("type") or "unknown")
    return camera, transition


def label_accuracy(truth_shots: list[dict[str, Any]], predicted: dict[int, str], key: str) -> dict[str, Any]:
    compared = []
    for shot in truth_shots:
        expected = shot.get(key)
        if expected is None:
            continue
        try:
            shot_id = int(shot.get("id"))
        except (TypeError, ValueError):
            continue
        actual = predicted.get(shot_id)
        compared.append((shot_id, str(expected), actual))
    correct = sum(1 for _, expected, actual in compared if actual == expected)
    return {
        "compared": len(compared),
        "correct": correct,
        "accuracy": round(correct / len(compared), 4) if compared else None,
        "mismatches": [
            {"shot_id": shot_id, "expected": expected, "predicted": actual}
            for shot_id, expected, actual in compared
            if actual != expected
        ],
    }


def evaluate_case(case: dict[str, Any], base: Path, tolerance: float) -> dict[str, Any]:
    scan = load_json(resolve_path(case["scan_json"], base))
    mechanics_path = case.get("mechanics_json")
    mechanics = load_json(resolve_path(mechanics_path, base)) if mechanics_path else None
    camera_pred, transition_pred = prediction_maps(mechanics)
    truth = case.get("ground_truth") or {}
    cuts = match_cuts(predicted_cuts(scan), [float(value) for value in truth.get("cuts") or []], tolerance)
    truth_shots = list(truth.get("shots") or [])
    return {
        "id": case.get("id"),
        "group_id": case.get("group_id") or case.get("id"),
        "variant": case.get("variant") or "base",
        "metadata": case.get("metadata") or {},
        "cuts": cuts,
        "camera": label_accuracy(truth_shots, camera_pred, "camera"),
        "transition": label_accuracy(truth_shots, transition_pred, "transition_in"),
    }


def evaluate_stability(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        groups.setdefault(str(result["group_id"]), []).append(result)
    stability = []
    for group_id, items in groups.items():
        if len(items) < 2:
            continue
        baseline = next((item for item in items if item["variant"] == "base"), items[0])
        variants = []
        for item in items:
            cut_delta = abs(item["cuts"]["predicted_count"] - baseline["cuts"]["predicted_count"])
            variants.append({
                "id": item["id"],
                "variant": item["variant"],
                "cut_count_delta": cut_delta,
                "cut_f1": item["cuts"]["f1"],
                "camera_accuracy": item["camera"]["accuracy"],
                "transition_accuracy": item["transition"]["accuracy"],
            })
        score_parts = []
        if all(item["cuts"]["predicted_count"] == baseline["cuts"]["predicted_count"] for item in items):
            score_parts.append(1.0)
        else:
            score_parts.append(max(0.0, 1.0 - statistics.mean(item["cut_count_delta"] for item in variants) / max(1, baseline["cuts"]["predicted_count"])))
        camera_values = [item["camera"]["accuracy"] for item in items if item["camera"]["accuracy"] is not None]
        transition_values = [item["transition"]["accuracy"] for item in items if item["transition"]["accuracy"] is not None]
        if camera_values:
            score_parts.append(statistics.mean(camera_values))
        if transition_values:
            score_parts.append(statistics.mean(transition_values))
        stability.append({
            "group_id": group_id,
            "variants": variants,
            "stability_score": round(statistics.mean(score_parts), 4),
        })
    return stability


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    def mean_metric(items: list[float | None]) -> float | None:
        values = [float(value) for value in items if value is not None]
        return round(statistics.mean(values), 4) if values else None

    return {
        "case_count": len(results),
        "cut_precision": mean_metric([item["cuts"]["precision"] for item in results]),
        "cut_recall": mean_metric([item["cuts"]["recall"] for item in results]),
        "cut_f1": mean_metric([item["cuts"]["f1"] for item in results]),
        "cut_miss_rate": mean_metric([item["cuts"]["miss_rate"] for item in results]),
        "cut_false_positive_rate": mean_metric([item["cuts"]["false_positive_rate"] for item in results]),
        "cut_mean_abs_error_sec": mean_metric([item["cuts"]["mean_abs_error_sec"] for item in results]),
        "camera_accuracy": mean_metric([item["camera"]["accuracy"] for item in results]),
        "transition_accuracy": mean_metric([item["transition"]["accuracy"] for item in results]),
    }


def render_markdown(report: dict[str, Any]) -> str:
    agg = report["aggregate"]
    lines = [
        "# 专业视频分析基准报告",
        "",
        f"- 状态：**{report['status']}**",
        f"- 用例数量：{agg['case_count']}",
        f"- 切点容差：±{report['tolerance_sec']} 秒",
        "",
        "## 汇总",
        "",
        "| 指标 | 结果 |",
        "| --- | ---: |",
        f"| 切点精确率 | {agg['cut_precision']} |",
        f"| 切点召回率 | {agg['cut_recall']} |",
        f"| 切点 F1 | {agg['cut_f1']} |",
        f"| 漏切率 | {agg['cut_miss_rate']} |",
        f"| 误切率 | {agg['cut_false_positive_rate']} |",
        f"| 切点平均误差 | {agg['cut_mean_abs_error_sec']} 秒 |",
        f"| 运镜准确率 | {agg['camera_accuracy']} |",
        f"| 转场准确率 | {agg['transition_accuracy']} |",
        "",
        "## 分组稳定性",
        "",
    ]
    if report["stability"]:
        for group in report["stability"]:
            lines.append(f"- `{group['group_id']}`：稳定性 {group['stability_score']}，变体 {len(group['variants'])} 个。")
    else:
        lines.append("- 暂无可比较的多分辨率/码率/画幅变体。")
    lines.extend(["", "## 用例", ""])
    for case in report["cases"]:
        lines.append(
            f"- `{case['id']}`：切点 F1 {case['cuts']['f1']}，"
            f"运镜 {case['camera']['accuracy']}，转场 {case['transition']['accuracy']}。"
        )
    lines.extend([
        "",
        "## 解释边界",
        "",
        "- 指标只反映所提供标注集，不代表所有视频类型的准确率。",
        "- 运镜与转场必须由人工标注真值；不能用同一自动结果自我验证。",
        "- 少于最小用例数时只能标记为 provisional，不能作为正式准确率声明。",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--tolerance", type=float, default=0.25)
    parser.add_argument("--min-cases", type=int, default=3)
    args = parser.parse_args()
    try:
        manifest = load_json(args.cases)
        validate_cases_manifest(manifest)
        base = args.cases.parent
        results = [evaluate_case(case, base, args.tolerance) for case in manifest.get("cases") or []]
        if not results:
            raise ValueError("基准用例为空。")
        report = {
            "schema_version": "1.0",
            "status": "validated" if len(results) >= args.min_cases else "provisional",
            "watermark": {"author": "我密码呢", "mark": "wmmn"},
            "tolerance_sec": args.tolerance,
            "minimum_cases": args.min_cases,
            "aggregate": aggregate(results),
            "stability": evaluate_stability(results),
            "cases": results,
            "limitations": [
                "结果只对应当前标注集。",
                "自动预测不能作为自己的真值。",
                "少于最小用例数时状态为 provisional。",
            ],
        }
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "benchmark_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.out / "benchmark_report.md").write_text(render_markdown(report), encoding="utf-8")
    except Exception as exc:
        failure = {"status": "blocked", "reason": "benchmark_failed", "detail": str(exc)}
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "benchmark_report.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"status": "completed", "out": str(args.out), "cases": len(report["cases"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
