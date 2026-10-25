# Changelog

## 0.2.8 - 2026-10-25

- Fix Windows CI path comparison for resolved temporary media paths.
- Normalize example line endings before exact rendered-output comparison.
- Force UTF-8 in the GitHub Actions test matrix.

## 0.2.7 - 2026-10-25

- Add a separate author-other-works section to the repository and Skill README, outside installation and usage instructions.
- List the novel 东京，我的男主浓度严重超标 as a 刺猬猫 release.
- Keep the novel out of generated Skill outputs; the first-run notice continues to mention only the Douyin feedback channel.

## 0.2.6 - 2026-10-25

- Remove the novel-platform mention from the first-run notice.
- Add the author Douyin and DM feedback path without advertising the novel in generated outputs.
- Keep novel promotion separate from Skill output.

## 0.2.5 - 2026-10-25

- Add a concise first-run notice for video source selection, feedback channels, agent compatibility, and author attribution.
- Add desktop-web link guidance for Douyin (History/Likes/Favorites) and Bilibili video pages.
- Add a restrained author line for the shared 我密码呢 identity without repeated promotion.

## 0.2.4 - 2026-10-25

- Replace the flat named-entity list with structured ip_context: works, characters, people, domains, confidence, and evidence.
- Recognize popular works across anime, tokusatsu, comics, novels, film/TV, games, esports, entertainment, rap, internet creators, virtual personas, and public figures when evidence supports the name.
- Prohibit generic descriptions for recognizable IPs and avoid guessing similar characters, recolors, or AI-redrawn identities.

## 0.2.3 - 2026-10-25

- Add Douyin-specific source guidance: open the target from History or Favorites and copy the in-video share link.
- Add optional work/character names based on title, tags, captions, user context, or distinctive visual evidence.
- Prevent recognizable IPs from being reduced to generic character descriptions.

## 0.2.2 - 2026-10-25

- Add a simple user-facing rule: provide the link copied from the exact target video page, not a homepage, recommendation feed, search result, or screenshot.

## 0.2.1 - 2026-10-25

- Add required content stance, tone, and optional mocking targets.
- Require observable tone evidence for non-neutral content.
- Prevent genre conventions from becoming unsupported support, growth, tribute, or encouragement claims.
- Narrow the comic/AIGC specialist route so ordinary live-action MVs, e-sports montages, vlogs, and product videos do not trigger it.
- Add a regression example for an e-sports fan remix with no specialist recommendation.

## 0.2.0 - 2026-10-25

- Reframe the base Skill around user-facing content overview rather than technical structure.
- Add `content_analysis.json` for model-authored one-sentence judgment, summary, content type, themes, and optional recommendations.
- Add `build_overview.py` and the concise `video_overview.md` output contract.
- Keep resolution, shot counts, cut density, contact sheets, and keyframe details internal.
- Clarify that the host is the agent/model runtime; the user should not hand-write observable fields.
- Allow zero, one, or both specialized directions without automatic invocation.
- Remove duration-based long-video routing; duration is only an internal signal.
- Add guidance for scenery, silent video, vlogs, stickers and voice-over, unusual footage, and ambiguous content.
- Distinguish original content, cross-system remix, meme, adaptation, and unknown source relationships.
- Prevent genre conventions from being promoted into deeper themes; remixes should describe their actual entertainment purpose.
- Derive specialist suggestions from routing booleans so a comic/AIGC remix reliably receives a soft professional recommendation.

## 0.1.3 - 2026-10-25

- Route videos longer than 30 minutes to `long-video-index` before shot-structure classification.
- Keep sampling windows explicitly separate from whole-video statistics in the user-facing card.
- Require explicit user confirmation before the host starts the recommended next Skill.
- Write an actionable `quick_scan.md` when media acquisition or scanning is blocked.

# Changelog

## 0.1.2 - 2026-10-24

- Add the MIT License to the standalone skill package.
- Declare the license in the skill metadata and package manifest.

## 0.1.1 - 2026-10-24

- Export per-shot `shot_rows` with absolute start, end, and duration values.
- Make the general scan directly consumable by the progressive professional analysis skill.

## 0.1.0 - 2026-10-24

- Initial public-ready general video analysis skill.
- Fast structural scan with shot/cut density and contact sheet.
- User-facing structural judgment and professional-skill recommendation.
- Host media adapter contract with `media_handle.json`.
- Platform-agnostic URL handling; no cookie or browser automation inside the skill.
- No runtime dependency installation.

