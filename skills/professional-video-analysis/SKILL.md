---
name: professional-video-analysis
description: Turn a general video scan plus host-provided domain context into a professional feasibility and reproduction plan for comic drama, animation, teaching, and other production-led videos. Use after the general-video-analysis skill identifies a professional candidate. This skill produces structural plans and prompt-ready evidence, not generic film criticism.
metadata:
  author: "我密码呢 (wmmn)"
  watermark: "wmmn / 我密码呢"
  short-description: "Professional video decomposition and reproduction planning"
---

# Professional Video Analysis

> This skill is a professional planning and first-pass reverse-engineering layer. It consumes a general scan and an optional host media handle; it never downloads media or opens a browser.

## Position in the workflow

```text
general-video-analysis
  → quick_scan.json (shots, cuts, duration, applicability)
  → host supplies a local media handle and domain observations
  → optional media_mechanics.py (camera motion + transition signatures)
  → professional-video-analysis
  → professional_report.md + professional_handoff.md + professional_analysis.json
```

The host owns media access and semantic observations. This skill owns the professional planning contract.

## Host observation gate

Before a detailed batch, the host must look at the selected shots through whatever media capability it actually has: the host video viewer, a contact sheet, or frames extracted by another tool. This skill does not download media, open a browser, read cookies, or perform OCR/VLM.

When the host can provide a readable local media handle, run `scripts/media_mechanics.py` to measure visual camera motion and incoming transition signatures. These are measurements with confidence, not physical rig metadata. Without a media handle, preserve host observations and leave missing camera/transition fields unverified.

Write only what was observed into `context.json`:

- `scene`
- `characters`
- `action`
- `shot_size`
- `camera`
- `transition`
- `first_frame`
- `last_frame`
- optional host-authored prompts

If the host cannot observe the selected shots, stop at the structure-only preview and say which observations are missing. Never fill five rows with “待补充” and present that as an analysis.

## Inputs

Required:

- `--scan-json`: output from general-video-analysis
- `--out`: output directory
- `--context-json`: domain, target format, assets, tools, workflow constraints, and per-shot observations; validated against `schemas/context.schema.json`

Strongly recommended when a host media handle exists:

- `--mechanics-json`: output from `media_mechanics.py`
- `--evidence-json`: output from `evidence_frames.py`

Without `--context-json`, the script may emit a structure-only preview. It must not invent a detailed breakdown from timing alone.

Context example: `examples/context.example.json`.

## Commands

Measure camera motion and transitions when a host media handle exists:

```bash
python scripts/media_mechanics.py \
  --media-manifest path/to/media_handle.json \
  --scan-json path/to/quick_scan.json \
  --start-shot 1 \
  --end-shot 5 \
  --out path/to/mechanics.json
```

Generate time-coded evidence frames:

```bash
python scripts/evidence_frames.py \
  --media-manifest path/to/media_handle.json \
  --scan-json path/to/quick_scan.json \
  --start-shot 1 \
  --end-shot 5 \
  --out path/to/evidence-output
```

Build the report:

```bash
python scripts/build_analysis.py \
  --scan-json path/to/quick_scan.json \
  --context-json path/to/context.json \
  --mechanics-json path/to/mechanics.json \
  --evidence-json path/to/evidence-output/evidence_manifest.json \
  --out path/to/professional-output
```

## Outputs

- `professional_report.md`: user-facing plain-language first-pass draft
- `professional_handoff.md`: portable brief for a new chat, another model, an AI workflow, or a traditional editor
- `professional_analysis.json`: AI-readable plan, anchors, confidence and evidence
- evidence output: `evidence_manifest.json`, start/middle/end frames, and `evidence_contact_sheet.jpg`

Context and evidence manifests must pass their JSON Schemas. The report marks handoff ready only when both semantic observations and time-coded evidence frames exist.

The host must show the Markdown report directly to the user. Do not merely list files.

## What the user must see

The report starts with a complete judgment, then tells the user:

1. Which shot range this batch covers and roughly how many seconds that is.
2. Whether the structure can be reproduced.
3. What was actually observed for each of the first five shots.
4. Prompt drafts assembled only from observations, with a clear feasibility flag per shot.
5. The first transition and first detected camera movement as early anchors.
6. What the remaining shots look like as an estimated structural overview.
7. Which downstream route the draft can support.
8. What cannot be guaranteed.

The opening should read like this, with real values substituted:

```text
这条视频大约 143 秒，检测到约 33 个镜头。
本次详细拆镜头 1–5，大概覆盖 0–31 秒。
后续还有约 28 个镜头，先只给结构性分段，不一次性展开。

当前判断：部分可做，需要补充角色和场景资产。
```

## Professional validity

- `measured`: shot count, duration, cut times, visual camera-motion signatures, and transition signatures.
- `inferred`: reproduction plan, production sequence, likely workflow.
- `unverified`: on-screen text, semantics, identity consistency, or any field without host/measurement evidence.
- Camera analysis can distinguish static, horizontal/vertical visual movement, apparent zoom, and complex motion, but cannot reliably distinguish physical dolly, zoom, crane, or subject motion.
- Transition analysis can report hard cut, fade-through-black, flash, dissolve candidate, wipe candidate, or unknown with confidence.
- If `camera` or `transition` is unavailable, output `not_observed`; do not invent it.
- A structural plan is not a guarantee of creative or commercial success.

## Domain profiles

- `profiles/comic-drama.md`
- `profiles/teaching.md`

The domain pack changes the planning checklist, not the evidence rules.

## Related skills

- General entry: `general-video-analysis`.
- Long corpus/index tasks should route to `long-video-index`; this skill handles a bounded video or selected window.

## Progressive batch policy

Default batch: first 5 shots.

- The 5-shot batch is a cost and review unit, not a claim that every video has a five-shot structure.
- The report also exposes a smaller first unit: the opening through the first detected transition. Users may analyze only that unit instead.
- If a five-shot batch covers a long time, users may reduce `--detail-count` or choose a time range.
- Report the covered time range explicitly; five shots may cover a long duration.
- After the detailed batch, show the estimated remaining shot count and structural segments only.
- Do not output every remaining shot as a row of unknown fields.
- Set a title that matches the actual batch, for example `第 2 批 · 镜头 6–10`.
- Continue only after the user chooses:
  - A: analyze the next batch of 5 shots
  - B: specify a time range
  - C: specify a shot range
  - D: stop at the current overview
- Continue with `--detail-start N --detail-count 5`.

When a host supplies scene, character, action, shot-size, camera, transition, and first/last-frame observations but no prompt text, assemble a factual prompt from those fields. Do not add character identity, visual style, camera movement, or actions that the host did not observe.

Do not generate negative prompts. Different image/video models support different negative fields and use them differently; this skill must not guess them. Put one closing notice in the report and handoff saying that users should judge and adapt negative prompts in their actual model or workflow.

## Benchmark validation

Do not claim a formal accuracy percentage without human-labeled real videos. Use `benchmarks/README.md`, `schemas/benchmark_cases.schema.json`, and `scripts/evaluate_benchmark.py`. A run with fewer than the configured minimum cases is `provisional` only.

## Draft and handoff contract

The report is explicitly a first-pass reverse-engineering draft, not a final production plan. Generate a handoff brief that separates:

- observed facts;
- measured camera/transition values with confidence;
- inferred production steps;
- missing questions;
- prompts and per-shot feasibility warnings;
- three downstream routes: own AI workflow, new chat/another model, or traditional editing.

A new chat or another model must also receive the relevant reference frames or video. Do not imply that the text alone proves unobserved visual facts.

## Feasibility gate

Before a row is treated as one promptable shot, check for contradictions:

- fixed camera but shot-size changes;
- an indoor/outdoor or scene-stage change inside a short detected shot;
- a long detected shot with internal composition stages;
- missing scene, action, or shot-size observations needed for a prompt.

If a segmentation/motion conflict is found, mark `review_required` and `needs_resplit`, explain the conflict, and do not generate a prompt for that row until the boundary is rechecked. If prompt-critical observations are missing, use `needs_observation` and suppress the prompt. Do not paper over segmentation errors with more prose.

The generated prompt pack must include the reverse-analysis notice: it is for analyzing the reference video, not a guarantee of reproduction; users should replace assets and optimize prompts for their own work and target tools.
