# Long Video Index

> [!WARNING]
> This Skill is a limited public beta. It has not yet been tested across all transcript formats, ASR providers, corpus sizes, operating systems, and agent hosts. Please report successful and failed cases through the forum, GitHub Issues, or Douyin DM `我密码呢`.
>
> **Long Video Index 仍是有限公开测试版。** 尚未覆盖所有逐字稿格式、ASR 来源、语料规模、操作系统和 Agent 宿主。欢迎反馈成功与失败案例。

一个只做长视频索引、定位和证据链的 Skill。

它消费**已有的带时间码逐字稿**，回答：

> 某个关键词或原话出现在长视频的哪些时间段？证据是什么？

它不转写、不下载视频、不拆镜头，也不做专业创作分析。

## Why this exists

两小时的课程、访谈、直播或系列视频不适合直接逐镜深拆。先建立逐字稿时间索引，才能低成本回答“这段在讲什么、这句话在哪、该从哪里继续看”。

这个 Skill 的价值是**可定位**和**可追溯**，不是自动写影评。

## Outputs

```text
long_video_index.json    # index summary + coverage + sections
long_video_index.sqlite  # segments, chunks, sections
evidence.jsonl           # quote-level evidence ledger
index_outline.md         # time map for the user
```

A collection build writes:

```text
collection.json          # navigation catalog, not the answer source
collection.sqlite        # episodes, sections, chunks, segments
evidence.jsonl           # quote-level evidence ledger
collection_outline.md    # episode/time map
```

A locate run can additionally write `locate_result.json` and `locate_result.md`.

## 成本审计

在建立索引前先运行：

```bash
python scripts/audit_input.py \
  --transcripts path/to/transcripts \
  --out workspace/corpus-audit
```

它会输出来源规模、逐字稿段数、CPU/内存/磁盘、预计后台占用、运行时间，以及 A/B/C 三档的收益与代价。不会默认替你选择模式。

当前脚本已经提供多集语料建库、跨集证据检索和可选的别名提及索引。目录只负责导航；真正给 AI 使用的是 `collection.sqlite` 中的逐字稿块、上下文、集数、时间码和证据。C 档只匹配用户提供的实体别名，不自动发现实体。

索引是单进程后台任务，通常主要使用约 1 个 CPU 逻辑核心。机器核心越多，占整机 CPU 的比例越低；不要求 GPU，但磁盘读写和内存占用会随输入规模变化。可以后台运行，但不承诺完全不影响同时进行的其他重任务。

时间范围要分清：

- 审计表中的秒级/分钟级时间，只覆盖“已有带时间码逐字稿 -> 索引”；
- 从原始视频开始还要另算视频获取、音频提取、ASR 和转写纠错；

三档不是越高越好：

| 档位 | 主要收益 | 主要代价 |
| --- | --- | --- |
| A · AI 可读取的多集语料库 | 提供真实逐字稿块、上下文、集数和时间码，让 AI 在缩小后的范围内阅读原文 | 用户自己直接查时体验偏技术，同义词不会自动补齐 |
| B · 用户证据定位 | 使用同一内容库，输出第几集、几分钟、原话和证据 | 需要抽查命中与证据，仍可能漏掉同义词 |
| C · 跨集实体提及索引 | 按用户别名表反复查工具、人物、技术等跨集出现位置 | 别名准备、误匹配校验和维护成本最高 |

详情见 [references/corpus-modes.md](references/corpus-modes.md)。

## Quick start

Build a multi-episode AI-readable collection:

```bash
python scripts/build_collection.py \
  --transcripts path/to/transcripts \
  --collection-title "Course title" \
  --out workspace/course-collection
```

Retrieve real transcript content for an AI answer:

```bash
python scripts/query_collection.py \
  --collection workspace/course-collection \
  --query "literal terms" \
  --aliases examples/entities.example.json \
  --episode 12 \
  --start 300 \
  --end 900 \
  --json
```

`--aliases` is optional. It expands canonical query terms into configured ASR variants such as `BurpSuite -> BobSuite/PopSuite`. It does not invent aliases automatically.

`collection.json` is navigation only. Episode titles may affect ranking, but query results mark `title_is_evidence: false`; only transcript citations count as evidence. When every query group appears in an episode title, the query also checks 180-second transcript windows so terms split across adjacent retrieval chunks can still be found. The result includes `context_text`, episode metadata, timestamped citations, quote hashes, and a grounding contract. A no-match result does not prove the topic is absent.

Build one canonical JSON transcript:

```bash
python scripts/build_index.py \
  --transcript examples/transcript.example.json \
  --chapters examples/chapters.example.json \
  --source-title "Example course" \
  --out workspace/example-index
```

Build from SRT or VTT by changing `--transcript`; the parser detects the format from the suffix.

Locate literal keywords:

```bash
python scripts/locate.py \
  --index workspace/example-index \
  --query "证据 时间码" \
  --limit 3
```

## Optional mention index

Mode C is exact-alias, deterministic, and opt-in:

```bash
python scripts/build_mentions.py \
  --collection workspace/course-collection \
  --entities examples/entities.example.json \
  --out workspace/course-mentions

python scripts/query_mentions.py \
  --index workspace/course-mentions \
  --entity "sqlmap" \
  --json
```

Entity ids and aliases are user-supplied. Duplicate aliases across entities are rejected. Results can contain false positives; a mention does not prove attitude or correctness.

## Input requirements

- Timestamped JSON, SRT, or VTT.
- Canonical JSON uses `segments` with `start`, `end`, and `text`.
- Optional `speaker`, `confidence`, `language`, and `duration_sec` are preserved where supported.
- Chapters are optional and must be non-overlapping.

There is no ASR inside this Skill. If the host has no transcript, acquire or generate one in the host's transcription layer first.

## Evidence chain

Each located quote carries:

- episode id, ordinal, and title for collection results;
- source-absolute range;
- `evidence_id` and `segment_id`;
- exact quote;
- quote SHA-256;
- parent index or collection ID and transcript SHA-256.

Search results are literal. A hit means relevant wording appears there; it does not prove the claim is true or that the video endorses it. Before returning a result, query steps verify the summary/database metadata, retrieval-chunk hash, and cited quote hash; a mismatch blocks the lookup and asks for a rebuild.

## Boundary

This Skill does not:

- download media or create transcripts;
- discover entities without a user-provided alias list;
- run OCR/VLM or shot analysis;
- summarize the whole video automatically;
- generate production or editing plans;
- mix in comic/AIGC or production-breakdown conclusions.

This Skill stops at retrieval and evidence. It does not automatically call or mix another analysis Skill.

## Feedback

The first successful user-facing audit/locate/query output includes the one-time `wmmn · 我密码呢` watermark and a short feedback notice. Later outputs do not repeat either. The full feedback guide is in [COMMUNITY.md](../../COMMUNITY.md) and should be linked as the forum pinned post or discussion guide.

Do not include unauthorized videos, full transcripts, audio, cookies, API keys, private paths, or personal information in a report.

## Tests

```bash
python -m unittest discover -s tests -v
```

Standard library only.

## License

MIT License. See [LICENSE](LICENSE).

Copyright (c) 2026 wmmn (where-password).
