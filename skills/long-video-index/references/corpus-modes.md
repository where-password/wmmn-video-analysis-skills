# Corpus Modes and Cost

## Do not default

The audit does not select a mode. Show the user the input size, machine profile, background occupancy, tradeoffs, and estimated cost before they choose. A higher mode is not a quality ranking.

## Cost layers

| Layer | Covered by the audit? | What it means |
| --- | --- | --- |
| Video acquisition and audio extraction | No | Depends on source access, network, storage, and tooling. |
| ASR and transcript cleanup | No | Usually much slower than indexing an existing transcript; depends on hardware and model. |
| Existing transcript to index | Yes | Parsing, SQLite writes, chunking, evidence output, and optional mention-index work. |
| Human validation | Partly estimated | B needs spot checks; C needs alias, false-positive, and result review. |

Acquisition and ASR time depends on source access, hardware, model choice, and cleanup needs. The audit does not provide a universal pipeline-time estimate for those stages.

## Background occupancy

The index is usually a single-process background task using about one logical CPU core. On an N-core machine, one busy core is approximately `100 / N` percent of the whole machine's CPU capacity. This is an estimate, not a reservation or guarantee. Disk I/O and memory use vary by transcript format, file count, and task phase. No GPU is required. It can run in the background but may still slow other heavy tasks.

## Mode A — AI-readable corpus

Create an episode/chapter/segment index that an AI can read directly.

Benefits:

- lowest machine and human cost;
- episode catalog, chapter blocks, timestamped segments, and real transcript chunks;
- SQLite and JSON/JSONL outputs;
- `query_collection.py --json` retrieves bounded context for an AI to read;
- a practical baseline when only the AI needs to read the corpus.

The catalog is navigation only. It is not evidence for an answer.

Costs and limits:

- the human-facing locate experience is basic;
- collection-level search may need an additional wrapper;
- transcript quality still limits what the AI can answer.

Do not reject A merely because it is listed first. When the user only needs AI-readable context, A is usually sufficient.

## Mode B — Evidence location

Add a user-facing locate result on top of A: episode, time range, exact quote, context, and evidence references.

Benefits:

- suitable when the user also wants to learn, search, or revisit the source;
- returns timestamped quotes and a stable evidence chain;
- supports handing a selected range to another process.

Costs and limits:

- spot checks are needed;
- exact-term search can miss synonyms and pronunciation variants;
- a hit proves wording appears, not that a claim is correct.

## Mode C — Mention index

This mode is implemented as exact-alias matching, not automatic entity discovery.

Precompute mentions of tools, people, technologies, terms, or other user-defined entities across episodes and timestamps. The user supplies an `entities.json` file with ids, names, types, and aliases.

Benefits:

- supports repeated cross-episode entity lookup;
- `query_mentions.py` returns episode, time range, exact quote, and evidence id;
- useful for a corpus that will be queried for a long time.

Costs and limits:

- the alias table must be prepared and reviewed;
- false positives and unlisted aliases remain possible;
- setup, review, and maintenance are much higher than A or B;
- no automatic NER or synonym discovery is included.

Use C only when repeated entity-level lookup is a real need. Do not present it as the default or as the “complete” choice.
