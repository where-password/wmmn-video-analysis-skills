---
name: long-video-index
description: Audit, build, and query a long-video transcript corpus with bounded retrieval, timestamped citations, and optional exact-alias entity mentions. Use for lectures, interviews, courses, series, streams, and videos over 30 minutes when the task is transcript corpus cost audit, multi-episode indexing, AI-readable corpus retrieval, or candidate-range evidence. Do not use for media acquisition, transcription, shot analysis, or professional production breakdowns.
metadata:
  author: "我密码呢 (wmmn)"
  watermark: "wmmn / 我密码呢"
  license: "MIT"
  short-description: "Multi-episode transcript corpus, evidence retrieval, and range handoff"
---

# Long Video Index

## What it does

Consume existing timestamped transcripts and produce:

- a multi-episode SQLite corpus containing real transcript chunks;
- a navigation catalog for episodes and time sections;
- bounded AI-readable retrieval with episode, context, and time range;
- user-facing literal keyword location with source-absolute timestamps;
- exact quote, source hash, and evidence IDs;
- an optional exact-alias entity mention index.

It is an indexing and locating layer, not an analysis layer.

## What it does not do

- No media download, browser access, cookie handling, or URL acquisition.
- No ASR or subtitle generation.
- No shot detection, camera/transition measurement, or keyframe extraction.
- No professional storyboard, editing, or reproduction plan.
- No narrative, aesthetic, virality, or content-quality judgment.
- No semantic search by synonym or pronoun resolution. Queries are literal keywords.
- No claim that a missing search hit proves the video never discusses the topic.
- No automatic entity discovery in mode C; only configured aliases are indexed.

## When to use

Use when:

- the video is longer than roughly 30 minutes, or the input is a series/collection;
- the host already has JSON, SRT, or VTT transcripts with timestamps;
- the user needs the model to retrieve bounded source content instead of reading the whole corpus;
- the user asks where a topic, phrase, claim, or term appears;
- the user wants a runtime, disk, or background-occupancy estimate before indexing;
- a candidate range must be located and cited as evidence for a separate user-chosen task.

Do not use when:

- the input has no timestamped transcript; route to the host's transcription/ASR adapter first;
- the user wants complete shot-by-shot professional reverse engineering;
- the user expects a general summary without reading the source segments.

## Input contract

Canonical JSON:

```json
{
  "language": "zh",
  "duration_sec": 7320,
  "segments": [
    {"id": "seg-000001", "start": 0.0, "end": 8.4, "speaker": "A", "text": "..."}
  ]
}
```

SRT and VTT are accepted when every cue has a timestamp. Plain text without timestamps is not valid input. Optional chapters use `{"chapters": [{"title": "...", "start": 0, "end": 600}]}`.

Transcript gaps and ASR errors remain visible in the coverage summary. Do not fill or silently rewrite them.

## Cost audit before choosing a mode

Run the audit first:

```bash
python scripts/audit_input.py \
  --transcripts path/to/transcripts \
  --out path/to/audit
```

Show `audit_report.md` to the user before they choose a mode. The report presents:

- input duration, episode/file count, segment count, and transcript size;
- CPU/GPU/RAM/disk context and the estimated machine-wide CPU share of one background index process;
- A/B/C benefits, limitations, machine time, human effort, and disk estimates;
- the boundary between “existing transcript to index” and video acquisition/ASR.

Do not choose A/B/C on the user's behalf and do not describe C as “more advanced”. The modes are:

- A: AI-readable corpus index — lowest cost; usually enough when only the AI needs to read the corpus.
- B: evidence location — adds user-facing time ranges, quotes, and evidence references; suitable for personal study.
- C: cross-episode mention index — optional high-cost mode for repeated tool/person/technique lookup.

The index is usually a single-process background task using about one logical CPU core. Say that it does not inherently consume every core and does not require a GPU, while disk and memory use still depend on the machine and input. See `references/corpus-modes.md`.

Current implementation provides four working layers:

- `build_collection.py`: multi-episode transcript database, evidence ledger, and navigation catalog;
- `query_collection.py`: AI-readable retrieval or user-facing location over actual transcript chunks;
- `build_index.py` and `locate.py`: the original single-transcript workflow;
- `build_mentions.py` and `query_mentions.py`: optional mode C exact-alias mention index.

The catalog is navigation only. Do not answer from episode titles. For A, query the collection and give the model real transcript context. For B, present episode, time range, exact quote, and evidence. For C, use the user's entity/alias file; never pretend that unlisted entities were automatically discovered.

A rebuild is staged before replacing known files. Failed overwrites must preserve the previous output. Query steps verify the full database metadata plus chunk and quote hashes; if any check fails, stop and ask for a rebuild.

## Build a multi-episode collection

```bash
python scripts/build_collection.py \
  --transcripts path/to/transcripts \
  --collection-title "Course title" \
  --out path/to/collection
```

This writes:

```text
collection.json           # navigation catalog, not the answer source
collection.sqlite         # episodes, sections, chunks, segments, evidence
evidence.jsonl            # flat quote-level evidence ledger
collection_outline.md     # human-readable episode map
```

Retrieve actual content for an AI answer:

```bash
python scripts/query_collection.py \
  --collection path/to/collection \
  --query "literal terms" \
  --aliases path/to/entities.json \
  --episode 12 \
  --start 300 \
  --end 900 \
  --json
```

`--aliases` is optional and only uses caller-provided entity aliases. It can expand ASR spelling variants, but it never invents aliases. If every query group appears in an episode title, collection search also checks 180-second transcript windows across adjacent chunks. Titles still serve only as ranking/candidate seeds, never as citations.

The result includes `context_text`, episode metadata, timestamped citations, quote hashes, and a grounding contract. The model should read that content before answering. A no-match result does not prove the topic is absent.

## Build one transcript index

```bash
python scripts/build_index.py \
  --transcript path/to/transcript.json \
  --chapters path/to/chapters.json \
  --source-title "Course title" \
  --out path/to/index
```

The command writes:

```text
long_video_index.json
long_video_index.sqlite
evidence.jsonl
index_outline.md
```

Show `index_outline.md` or a concise version of it to the user when the index is built. Do not present the time-bucket map as a semantic summary.

## Locate evidence

```bash
python scripts/locate.py \
  --index path/to/index \
  --query "关键词 关键词" \
  --start 1800 \
  --end 5400 \
  --limit 5 \
  --out path/to/locate-result
```

Use two to five concrete literal terms rather than a full question. The tool requires every term to occur in the same retrieval chunk and returns exact quotes from matching segments.

Present results in this order:

1. time range;
2. exact timestamped quote;
3. evidence ID and quote hash;
4. limitations.

Do not add a conclusion that the quote does not directly support. If the result is `no_matches`, say that literal matching found nothing and mention transcript coverage or keyword limitations.

## Optional mention index

Mode C is alias-driven, deterministic, and opt-in:

```bash
python scripts/build_mentions.py \
  --collection path/to/collection \
  --entities path/to/entities.json \
  --out path/to/mentions
```

Then query episode/time evidence:

```bash
python scripts/query_mentions.py \
  --index path/to/mentions \
  --entity "sqlmap" \
  --json
```

Entity lists must be provided by the user. Duplicate cross-entity aliases are rejected. Alias matches may contain false positives, and a mention does not prove attitude or correctness.

## Evidence contract

Every hit points back to:

- `index_id` or `collection_id`;
- episode id, ordinal, and title for collection results;
- transcript SHA-256;
- segment and evidence IDs;
- source-absolute start/end seconds;
- verbatim quote;
- quote SHA-256.

`evidence.jsonl` is the flat audit ledger. A citation without a quote and timestamp is incomplete.

## Scope boundary

This Skill stops at transcript retrieval, episode/time location, and evidence. Do not turn a hit into AIGC/comic breakdown, shot analysis, production advice, or content-quality judgment. Do not automatically call or mix another analysis Skill.

## Failure response

When transcript input or index lookup is blocked, return structured JSON with:

```json
{
  "status": "blocked",
  "reason": "invalid_transcript",
  "detail": "actionable reason",
  "next_action": "provide a timestamped JSON/SRT/VTT transcript"
}
```

Do not fabricate timestamps, quotes, or topic coverage.

## Feedback notice

On the first successful user-facing audit, locate, or query in an installation, append the short notice from `references/first-run-notice.md` once and record `.state/first-run-v1.json`. That notice contains the one-time `wmmn · 我密码呢` watermark. Later outputs do not repeat the watermark or feedback notice.

The short notice points to the full forum/community guide in the repository root `COMMUNITY.md`. Do not include unauthorized media, full transcripts, credentials, private paths, or personal data in feedback.

## Attribution

wmmn · 我密码呢
