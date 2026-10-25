---
name: general-video-analysis
description: Analyze what a video is actually about and return a concise content overview with a one-sentence judgment, a summary paragraph, content type, themes, and optional soft next-step suggestions. Use for general video questions, mixed or unusual video formats, and triage before a specialized professional or long-video workflow. Keep technical structure internal.
metadata:
  author: "我密码呢 (wmmn)"
  watermark: "wmmn / 我密码呢"
  license: "MIT"
  short-description: "Broad video content overview and soft routing"
---

# General Video Analysis

## Purpose

Answer the user's main question:

> What is this video about?

The output should be a concise, useful content overview, not a technical scan report and not a professional shot breakdown.

Broad does **not** mean listing everything visible. Broad means the Skill can handle narratives, knowledge explainers, interviews, vlogs, scenery, products, commentary, memes, silent footage, and unusual formats while still identifying the actual content.

## User-facing output

The user should see only:

- one-sentence content judgment;
- one content-summary paragraph;
- content type;
- content themes;
- related IP/works, characters, or people when evidence supports them;
- content tone;
- mocking/play targets when applicable;
- optional, softly worded professional directions;
- two short limitation notes;
- the wmmn watermark.

Do not show:

- duration, resolution, FPS, codec, or file size;
- shot count, cut count, cut density, or median shot length;
- analysis windows, shot rows, keyframes, or contact-sheet coordinates;
- object lists, character lists, visible-action lists, or key-segment tables;
- camera, transition, prompt, storyboard, or continuity analysis.

Technical structure is for internal routing and downstream analysis only.

## First successful use

`build_overview.py` defaults to `--first-run auto`. On the first successful overview for an installation, it appends `references/first-run-notice.md` to the end of `video_overview.md`, writes a small marker at `.state/first-run-v1.json`, and does not repeat the notice afterwards.

If the host cannot persist the marker, the overview still succeeds but reports `first_run_state_persisted: false`; the notice may appear again on the next run. Do not duplicate the notice manually when the generator already appended it.

The notice is limited to three short points: video source/usage responsibility, a brief disclaimer, and accuracy feedback via the community forum or Douyin. Do not add the novel or other promotion to generated outputs.

## Workflow

1. Acquire a readable media handle from the exact target video. Ask for the link copied from that video page, not a homepage, recommendation feed, search result, or screenshot. On Douyin, prefer opening the target from History or Favorites and using the in-video share link; avoid Featured, creator profile, and recommendation-feed URLs.
2. Run `scripts/scan.py` to create internal structure data and a contact sheet.
3. The **model** inspects the contact sheet, video, subtitles, transcript, or audio that the host can actually access. The user is not asked to hand-write scene, character, action, or shot fields.
4. The model writes `content_analysis.json` following `schemas/content_analysis.schema.json` and `references/content-overview-guide.md`.
5. Run `scripts/build_overview.py` to render `video_overview.md`.
6. Show the content of `video_overview.md` in the chat. Do not show `quick_scan.md` or raw JSON unless the user explicitly asks.

## Host meaning

In this Skill, **host** means the agent or model runtime and its media-access tools. It does not mean the end user.

The model owns observation and drafting. The user may clarify a genuinely ambiguous point, but should not be assigned the work of filling a structured observation file.

If the model cannot inspect enough visual or transcript evidence, return a limited content overview and state the missing evidence plainly. Do not invent the topic.

## Commands

Internal structure scan:

```bash
python scripts/scan.py --source "<LOCAL_VIDEO_OR_URL>" --out "<OUTPUT_DIR>"
```

Host-provided readable media:

```bash
python scripts/scan.py --media-manifest "<MEDIA_HANDLE_JSON>" --out "<OUTPUT_DIR>"
```

Render the user-facing overview after model observation:

```bash
python scripts/build_overview.py \
  --analysis-json "<OUTPUT_DIR>/content_analysis.json" \
  --out "<OUTPUT_DIR>"
```

## Content analysis contract

`content_analysis.json` is written by the model, not by the user. It contains:

- `one_sentence`: the complete one-line judgment;
- `summary`: the content paragraph;
- `content_type`: natural language type labels;
- `themes`: the actual topics or subject matter;
- `ip_context`: optional works, characters, people, domains, confidence, and evidence for recognizable IP or public figures;
- `basis`: `video`, `transcript`, `audio`, and/or `user_context`;
- `content_mode`: `original`, `remix`, `meme`, `adaptation`, or `unknown`;
- `content_stance`: `supportive`, `critical`, `mocking`, `neutral`, `mixed`, or `unknown`;
- `content_tone`: the actual tone labels, such as `调侃`, `恶搞`, `伤感`, or `中性记录`;
- `mocking_targets`: optional targets of teasing or parody;
- `tone_basis`: observable signals supporting a non-neutral stance;
- `routing.comic_aigc_led`: whether the content is comic/animation/AIGC and could benefit from the specialized production Skill;
- `routing.longform_knowledge`: whether transcript-backed long-form lookup could be useful.

The renderer derives soft specialist suggestions from `routing`; the model does not need to remember a separate recommendations field.

Do not put technical structure in this file.

## How to describe content

Describe what the video says, tells, demonstrates, or presents. Do not turn visible objects into the subject.

Examples:

- A dog sticker with human voice-over may be about relationships, not dogs.
- A person waving in a room is not inherently a meaningful action; the content comes from what the video says or shows overall.
- A silent scenery video can still have clear content: a landscape, travel mood, or ambient visual experience.
- A vlog can be summarized by the day, experience, or point of view it records.

Set `content_mode` separately from the surface genre:

- `original`: a self-contained original work;
- `remix`: familiar scenes, characters, plot, nationality, universe, cast, or visual system are replaced;
- `meme`: the main result is a joke, absurd contrast, reaction, or Internet-style bit;
- `adaptation`: a direct adaptation or re-edit;
- `unknown`: the source relationship cannot be established.

A cross-system remix can look like a serious genre piece. If familiar military scenes are replaced with American soldiers while keeping the original plot, describe it as a remix and state the actual entertainment effect. Do not infer growth, discipline, family legacy, or similar depth merely from the military setting.

Themes must reflect the video's actual content and viewing purpose. For a remix or meme, terms such as `整活`, `反差`, `影视二创`, and `恶搞` can be more accurate than genre-based moral themes. Surface story belongs in the summary; the theme should describe what the video is functionally doing.

Do not guess a source title unless it is recognizable from the evidence or supplied by the user. If the source relationship is unclear, use cautious wording and set `content_mode: unknown`.

For unusual or ambiguous footage, use a tentative but useful summary and state what is uncertain. Do not force it into a known genre.

## Recognize popular IP and public figures

Use recognizable canonical names when the evidence supports them. This includes anime, tokusatsu, novels, comics, film/TV, games, esports, entertainment, rap, internet creators, and virtual personas.

Identify at four levels:

- work/franchise;
- character;
- real person or virtual persona;
- broad domain.

Do not reduce a known IP to “several characters”, “an anime figure”, or “a celebrity”. Do not guess between similar costumes, recolored designs, AI-redrawn characters, or lookalike people from a single frame. If only the franchise is certain, name the franchise and leave the character list empty. If confidence is low, use cautious wording and mark it low.

## No unsupported value framing

Do not infer a positive or moral purpose from genre alone.

Examples of unsupported elevation:

- military footage does not automatically mean growth or discipline;
- an e-sports montage does not automatically mean support or encouragement;
- a fan remix does not automatically mean tribute;
- a joke video does not automatically carry a serious social message.

Use the actual stance and tone. If adapted lyrics, captions, editing contrast, or user context show teasing, describe it as teasing. If the evidence is insufficient, use `unknown` and cautious wording. Do not infer malice from teasing either.

## Professional directions

The model sets routing flags from content:

- `comic_aigc_led: true` for comic, animation, AIGC, or comic/AIGC-oriented remixes where professional production analysis could help. Do not set it for a general live-action MV, e-sports montage, vlog, or product video merely because it has editing;
- `longform_knowledge: true` for knowledge-heavy long content where transcript-backed lookup could help;
- both can be true.

The renderer creates soft suggestions automatically:

- comic/AIGC-led -> professional video analysis;
- long-form knowledge -> long video index;
- both -> both directions;
- neither -> no specialist suggestion.

Duration alone does not determine the route. A long comic series can still be production-led and not a long-video index request.

Never invoke another Skill automatically. The user decides whether to continue.

## Failure response

If media cannot be read, return a soft blocked message:

```text
这次暂时没有取得可读取的视频媒体，因此无法完成内容概览。
可以改为提供可读的本地媒体文件、宿主媒体句柄或公开链接后重试。
```

If media is readable but content evidence is thin, return a limited overview instead of a technical dump or invented summary.

## Attribution

wmmn · 我密码呢
