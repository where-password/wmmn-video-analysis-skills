# Changelog

## 0.3.6 - 2026-10-26

- State clearly in the repository and first-run notice that Long Video Index is a limited public beta.
- Request successful and failed test reports across transcript formats, ASR providers, corpus sizes, operating systems, and agent hosts.
- Protect the Douyin nickname with inline code so browser auto-translation does not alter it.

## 0.3.5 - 2026-10-26

- Show the visible `wmmn · 我密码呢` watermark only in the first successful user-facing audit, locate, or query output.
- Remove repeated watermark footers from outlines, audit reports, location results, collection queries, and mention queries.
- Keep machine-readable attribution and evidence hashes unchanged.

## 0.3.4 - 2026-10-25

- Remove local course and benchmark metadata from the public cost audit.
- Keep the audit functional: input size, machine profile, background occupancy, A/B/C tradeoffs, time, and disk estimates only.
- Move the audit schema to 1.2 and remove the private reference profile field.

## 0.3.3 - 2026-10-25

- Add a one-time short feedback notice to the first user-facing locate/query output.
- Add the full forum/community feedback guide and privacy checklist.
- Collect feedback through the forum, Douyin DM, or reproducible GitHub Issues.
- Keep local benchmark metadata out of the public cost audit.

## 0.3.2 - 2026-10-25

- Add optional `--aliases` query expansion for caller-provided ASR variants.
- Add a 180-second segment-window fallback for title-seeded episodes when query terms span adjacent retrieval chunks.
- Expose `term_groups`, alias hash, `retrieval_method`, and `window_id` in collection query results.
- Mark title matching as ranking-only metadata; citations remain the sole evidence.
- Add regression coverage for alias expansion and cross-chunk retrieval.

## 0.3.1 - 2026-10-25

- Add episode-title matching as a ranking-only signal in collection queries.
- Mark `title_is_evidence: false` in result ranking metadata so titles never become citations.
- Improve top-1 episode ranking in retrieval regression tests without changing evidence requirements.

## 0.3.0 - 2026-10-25

- Add `build_collection.py` for multi-episode transcript corpora with episode, section, chunk, segment, and evidence tables.
- Add `query_collection.py` for bounded AI-readable retrieval and user-facing cross-episode location over real transcript chunks.
- Keep `collection.json` as navigation only; query results carry actual context, episode metadata, timestamps, and quote hashes.
- Add optional `build_mentions.py` and `query_mentions.py` for exact-alias entity mentions without automatic NER.
- Add collection and mention schemas plus an entity alias example.
- Update cost-audit implementation status and documentation for the three working modes.

## 0.2.2 - 2026-10-25

- Stage index rebuilds and replace known outputs only after a successful build, so a failed `--overwrite` preserves the previous index.
- Filter located citations to the requested time window and clip the returned hit range.
- Verify the full database index metadata, retrieval-chunk hashes, and cited quote hashes before returning evidence.
- Compute speech coverage from merged time intervals so overlapping cues are not double-counted, including leading and trailing gaps.
- Stream the evidence ledger and handle SQLite/output write failures with structured errors.
- State that A/B/C are deployment-cost modes and that cross-episode batch wrapping and C entity extraction are not built into the current scripts.

## 0.2.1 - 2026-10-25

- Read total and available RAM with the standard library on Windows and Linux, without requiring psutil.
- Report the CPU model, logical core count, estimated machine-wide CPU share, background run suitability, and GPU requirement.
- Fix the Markdown cost table column order and split mode tradeoffs from time/space estimates.
- Separate “existing transcript to index” estimates from acquisition and ASR stages.

## 0.2.0 - 2026-10-25

- Add a preflight audit that estimates machine time, disk, CPU/RAM class, and human effort before indexing.
- Present three usage modes without a default: AI-readable corpus, evidence location, and optional cross-episode mention index.
- Add duration-shortage warnings and de-duplicate JSON/SRT/VTT representations of the same episode.
- Keep transcript indexing cost separate from acquisition and ASR.

## 0.1.0 - 2026-10-25

- Initial public-ready long-video index Skill.
- Accept timestamped JSON, SRT, and VTT transcripts.
- Build a SQLite segment/chunk index with deterministic chunk IDs and time sections.
- Emit a flat evidence ledger with transcript, quote, and quote hashes.
- Locate literal multi-term matches and return timestamped exact quotes.
- Reject locate runs when the index summary and SQLite metadata do not match.
- Support optional chapter maps and source-absolute time filters.
- Keep ASR, media acquisition, shot analysis, and professional breakdowns out of scope.
