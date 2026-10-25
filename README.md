# WMMN Video Analysis Skills

[![tests](https://github.com/where-password/wmmn-video-analysis-skills/actions/workflows/tests.yml/badge.svg)](https://github.com/where-password/wmmn-video-analysis-skills/actions/workflows/tests.yml)
[![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Start with what the video actually says. Go deeper only when the content and the user's intent justify it.**

**先看视频讲了什么，再按内容和个人需求选择更专业的分析方向。**

wmmn (`我密码呢`) builds focused video-analysis Skills for Codex, Claude Code, and compatible agent hosts. The project is a public beta; evidence contracts and runtime behavior are still being validated with real videos.

## Before you start

- **Video link:** Use the desktop web URL of the exact target video. On Douyin, open the video from History, Likes, or Favorites and copy the in-video share link. On Bilibili, use the specific video page URL. Do not use a homepage, recommendation feed, search result, or screenshot as the source.
- **Feedback:** Questions and suggestions are welcome in the forum thread, GitHub Issues, or a Douyin DM to `我密码呢`. See [COMMUNITY.md](COMMUNITY.md) for the full feedback and privacy guide.
- **Compatibility:** WorkBuddy, Doubao Work, and other agent hosts have not yet been tested. You can try them; please report successful or failed runs on GitHub.
- **Copyright responsibility:** This project provides analysis tooling only and does not grant rights to source videos. Analyze only media you are authorized to access. Results are for personal study, research, and discussion; organizational or commercial use requires the user to verify copyright, licensing, and compliance. The author is not responsible for third-party use of videos or results.

**中文使用提醒：**

- 请提供电脑网页版的目标视频链接。抖音建议从历史记录、点赞或收藏进入目标视频后复制链接；B站请使用具体视频页链接。主页、推荐流、搜索结果和截图不能稳定确定视频。
- 有问题或建议，欢迎在论坛回帖、GitHub Issues 或抖音私信 `我密码呢` 反馈；完整说明见 [COMMUNITY.md](COMMUNITY.md)。
- WorkBuddy、豆包工作版等 Agent 尚未测试；可以先尝试，成功或失败都欢迎反馈到 GitHub。

## Usage and Copyright / 使用与版权声明

1. 分析结果仅供个人学习、研究和交流参考。
2. 公司、商业或其他组织使用前，用户需自行确认版权、授权和合规责任。
3. 作者仅提供视频分析工具，不提供视频内容授权；不承担因视频或分析结果使用产生的责任，本提示不构成法律意见。

See [DISCLAIMER.md](DISCLAIMER.md) for the full disclaimer. This is not legal advice.

> [!WARNING]
> **Long Video Index is a limited public beta.** It has not yet been tested across all transcript formats, ASR providers, corpus sizes, operating systems, and agent hosts. Please report successful and failed cases through the forum, GitHub Issues, or Douyin DM so the retrieval and compatibility behavior can be improved.
>
> **Long Video Index 仍是有限公开测试版。** 尚未覆盖所有逐字稿格式、ASR 来源、语料规模、操作系统和 Agent 宿主。欢迎通过论坛、GitHub Issues 或抖音私信 `我密码呢` 反馈成功与失败案例，帮助继续优化检索和兼容性。

## Skills

| Skill | Purpose | Status |
| --- | --- | --- |
| [general-video-analysis](skills/general-video-analysis) | Broad content overview: one-sentence judgment, summary paragraph, type, theme, structured IP/people recognition, tone, optional targets, and soft next steps | 0.2.13 working version |
| [professional-video-analysis](skills/professional-video-analysis) | Bounded production reverse-engineering, shot planning, evidence frames, prompts, and handoff | 0.4.5 working version |
| [long-video-index](skills/long-video-index) | Multi-episode transcript corpus, bounded evidence retrieval, timestamp lookup, and optional alias mention index | 0.3.6 public beta · limited testing |

The Skills are designed around separate jobs. The base Skill analyzes content. Professional analysis and long-video indexing are optional directions that users can choose independently.

## Start with the base Skill

**Video link requirement:** Open the exact video you want analyzed, then copy the link from that video page. On Douyin, prefer opening it from History or Favorites and copying the in-video share link; do not use Featured, creator profile, recommendation feed, search result, or screenshot URLs.

**视频链接要求：** 请先打开你真正想分析的视频，再从该视频页面复制分享链接。抖音建议从历史记录或收藏进入目标视频后复制链接；不要把精选、主播主页、推荐流、搜索结果页或截图当作视频链接。

~~~bash
python -m pip install -r skills/general-video-analysis/requirements.txt

python skills/general-video-analysis/scripts/scan.py \
  --source "<LOCAL_VIDEO_OR_HOST_URL>" \
  --out workspace/video-analysis
~~~

The scan creates internal structure data and a contact sheet. The agent then inspects the available video evidence and writes content_analysis.json. Render the user-facing result with:

~~~bash
python skills/general-video-analysis/scripts/build_overview.py \
  --analysis-json workspace/video-analysis/content_analysis.json \
  --out workspace/video-analysis
~~~

The user sees video_overview.md:

- one-sentence content judgment;
- one summary paragraph;
- content type;
- content themes;
- optional professional directions;
- two short notes.

Resolution, shot counts, cut density, contact sheets, and keyframe details stay internal.

## How the base Skill describes content

It describes what the video says, tells, demonstrates, or presents, not what objects happen to appear in its frames.

- A dog sticker with human voice-over may be about relationships, not dogs.
- A person sitting in a room and waving is not automatically a meaningful action.
- A silent scenery video can still have clear content: a landscape, travel mood, or ambient visual experience.
- A vlog can be summarized by the day, experience, or point of view it records.
- A cross-system remix can look like a serious genre piece on the surface. Its theme should reflect the actual remix or parody effect, not an inferred moral lesson.

Broad coverage means the Skill handles many video formats. It does not mean producing a long list of shallow visual details.

## Optional specialist directions

The base Skill sets two internal routing fields:

- **comic_aigc_led** only for comic, animation, AIGC, or comic/AIGC-oriented remix content; a general live-action MV, e-sports montage, vlog, or product video does not trigger this route merely because it has editing;
- **longform_knowledge** for transcript-backed knowledge-heavy long content.

Soft specialist suggestions are derived from those fields. Both may appear at once. If both are false, the overview ends without a specialist recommendation. Duration alone is not enough. A long comic series can still be a professional analysis request. The base Skill does not invoke another Skill automatically.

## Internal structure contract

The base scan still preserves:

- media metadata;
- shot boundaries and timing;
- cut density;
- contact sheet and sampled frames;
- per-shot rows for downstream professional analysis.

These fields exist for machine use and routing context. They are not part of the user-facing content overview.

## Evidence and boundaries

- The model inspects the media evidence; the user is not asked to hand-write observable fields.
- Unread content is not invented.
- Creative intent, style quality, mistakes versus deliberate style, audience response, and personal creativity are not treated as measured facts.
- No media acquisition inside the Skill.
- No browser automation or cookie access.
- No automatic specialist invocation.
- No technical dump unless the user explicitly asks for it.

## Validation

The repository workflow runs the public Skill tests on Windows and Ubuntu with Python 3.10 and 3.12. Current release baseline: **105 tests**.

- General Skill: 26 tests for content-first overview, structured IP/people recognition, stance/tone grounding, narrow routing, examples, and first-run watermark guidance.
- Professional Skill: 46 tests for schemas, progressive batching, evidence coverage, mechanics, first-run watermark behavior, and handoff gates.
- Long-video index: 33 tests for corpus indexing, evidence retrieval, ASR aliases, first-run watermark behavior, and cost audit.

No broad accuracy score is claimed. Retrieval quality should be judged from reproducible cases rather than a generic claim. Further human-labeled validation is community-driven; see the [benchmark protocol](skills/professional-video-analysis/benchmarks/README.md), [human labeling guide](skills/professional-video-analysis/benchmarks/human-labeling.md), and [community call](skills/professional-video-analysis/benchmarks/community-call.md).

## Repository layout

~~~text
skills/
  general-video-analysis/
  long-video-index/
  professional-video-analysis/
.github/
  workflows/tests.yml
  ISSUE_TEMPLATE/
~~~

## Community validation

The most useful feedback is a concrete video case, not a feature count:

- a content summary that mistakes a visual object for the theme;
- a silent, scenery, vlog, or unusual video that is summarized poorly;
- a professional direction suggested for the wrong reason;
- a cut, camera, or transition case with human labels;
- a report that overstates its evidence.

Remove cookies, tokens, private URLs, local paths, and unauthorized media before submitting. Read [CONTRIBUTING.md](CONTRIBUTING.md).

## Visible watermark policy

Each Skill shows `wmmn · 我密码呢` once in its first successful user-facing output on an installation. Later reports and query results do not repeat it. Machine-readable attribution remains in manifests, JSON, and evidence metadata.

## Feedback forum

The full long-video feedback statement is in [COMMUNITY.md](COMMUNITY.md). The short first-run notice points there so routine analysis output stays compact.

论坛完整反馈说明见 [COMMUNITY.md](COMMUNITY.md)，首次输出只显示简短提醒。

## 作者其他作品

### 《东京，我的男主浓度严重超标》

仅发布于刺猬猫平台。喜欢恋爱喜剧的朋友可以支持一下；不喜欢也欢迎直接吐槽。

作者抖音：`我密码呢`

## Attribution and license

Visible wmmn · 我密码呢 attribution is intentional and appears in reports, manifests, scripts, and evidence artifacts.

MIT License. See [LICENSE](LICENSE).

Copyright (c) 2026 wmmn (where-password).

Author Douyin: `我密码呢`. Questions and feedback can be sent by DM; reproducible technical reports are also welcome in GitHub Issues.

作者抖音：`我密码呢`。有问题可以私信反馈，也欢迎在 GitHub Issues 留下可复现信息。
