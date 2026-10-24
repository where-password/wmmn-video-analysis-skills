---
name: general-video-analysis
description: Quickly scan any video into a short structural card. Use when a user drops one or more videos without a precise professional request, or when a host needs a cheap applicability check before routing to a professional or long-video skill. This skill does not perform professional critique or content-value judgments.
metadata:
  author: "我密码呢 (wmmn)"
  watermark: "wmmn / 我密码呢"
  license: "MIT"
  short-description: "Fast video structure scan and applicability router"
---

# General Video Analysis

## What it does

Given a video, return a **short structural card**:

- duration, resolution, FPS
- detected shots and cuts
- cut density
- median shot length
- a sampled contact sheet
- applicability status
- a recommendation for a more specialized skill when justified

It is a triage and routing service, not a professional analysis engine.

## What it does not do

- No narrative, aesthetic, humor, retention, or "why it went viral" judgment.
- No OCR, VLM, camera-motion classification, or continuity audit.
- No corpus building for tens or hundreds of hours.
- No generic pros/cons or "how to improve" advice.
- No claim that a sampled window describes a whole long video.

## When to use

Use when:

- the user drops a video without a precise request;
- the host needs a cheap applicability check;
- the host needs to decide whether to route to a professional or long-video skill.

Do not use when:

- the user already requested a specific professional breakdown;
- the video is a long series that needs a transcript-first index;
- the user expects an authoritative creative critique.

## Host media adapter

The user should only need to provide a URL. The host must use its existing video-viewer or media-access capability to turn that URL into a readable media handle, then call this skill. The skill does not ask the user to choose cookies, browsers, or local export paths.

See `ACQUISITION_CONTRACT.md`. If the host cannot produce a readable media file, return `blocked`; do not fabricate structure or commentary.
## Command

```bash
python scripts/scan.py --source "<LOCAL_VIDEO_OR_URL>" --out "<OUTPUT_DIR>"
```

Useful options:

```bash
--window 0:30
--max-analysis-sec 120
```

URL handling is intentionally simple:

- URLs are passed through unchanged; this skill contains no platform-specific normalization.
- The host/yt-dlp acquisition layer handles platform-specific URL quirks. This skill does not contain platform-specific normalization.
- The skill attempts public URL access only.
- It does not inspect cookies, launch a browser, or retry through browser profiles.
- If the URL is not directly accessible, return `blocked`; the host may supply a local media handle instead.
- A local video may be passed directly when the host has one.

## Outputs and user presentation

```text
quick_scan.md
quick_scan.json
quick_contact_sheet.jpg
frames/
```

After a successful run, **show the content of `quick_scan.md` directly in the chat and embed `quick_contact_sheet.jpg`**. Do not merely list file paths. The user-facing answer is the Markdown card plus the image; the JSON is for the host.

## Runtime policy

- Dependencies must be installed before the run; do not `pip install` during analysis.
- The fast scan should sample 8 frames and run one scene-detection pass.
- Default target for a local 1-2 minute 720p video: roughly 10-60 seconds, excluding host-side media acquisition.

`quick_scan.json` includes:

- `status`
- `media`
- `structure`
- `shot_rows`: per-shot absolute `start`, `end`, and `duration` values for downstream professional analysis
- `applicability`
- `artifacts`
- `limitations`

## User-facing format

The chat response must start with a complete one-line judgment, not metadata:

```text
这是一条约 60 秒的高密度快剪/混剪视频，核心靠连续切镜和画面变化推进。

结构判断：约 58 个镜头、57 个切点，平均 0.8 秒一个镜头。
具体题材（整活、风景、音乐等）不能只靠镜头结构可靠确认。

适不适合专业拆解：适合。
如果要继续：建议使用 professional-video-analysis，拆镜头、节奏和复刻结构。
不能保证：不判断网感、幽默、个人风格或传播效果。
```

Do not lead with duration, resolution, FPS, file links, or raw JSON. Put technical values in the basis line only.

## Applicability statuses

- `not_applicable_for_professional_analysis`: single shot/static video; explain why and give the short structure.
- `general_only`: some structure, but not enough evidence for a professional route.
- `professional_candidate`: multiple shots or meaningful cut density; recommend `professional-video-analysis` only as a possible next step.
- `long_video_candidate`: video is over 30 minutes; recommend a transcript-first long-video index instead of deep shot analysis.

For `professional_candidate`, the recommendation must say:

- the professional skill covers rigid production structure only;
- it cannot reproduce humor, net sense, personality, or guarantee audience response.

## Hard boundaries

- A short scan is not a full-video analysis.
- A sampled window is labeled `sampled: true`.
- A structural signal does not prove creative intent.
- If media cannot be accessed, return `blocked` with the reason; do not invent frames or commentary. Built-in browser playback does not guarantee that the media stream is accessible to the skill.
- The host owns user dialogue, final routing, generation, and delivery.

## Dependencies

Core:

```bash
pip install -r requirements.txt
```

Optional URL acquisition:

```bash
pip install yt-dlp
```

System media tools: `ffmpeg` is recommended; `imageio-ffmpeg` can provide it on Python.



## Media manifest input

When a browser or viewer has already acquired the media, pass its host manifest:

```bash
python scripts/scan.py --media-manifest "<MEDIA_HANDLE_JSON>" --out "<OUTPUT_DIR>"
```

The manifest contract is in `schemas/media_handle.schema.json`, with an example at `examples/media_handle.example.json`. Browser/DevTools extraction is a host-side provider; it is not implemented inside this analysis skill.




## Related skills

This general skill is the entry point. When the video has measurable professional structure, recommend the host route it to `professional-video-analysis`. When it is a long corpus/index task, recommend `long-video-index`. Both are planned and are not silently installed or invoked by this package.
