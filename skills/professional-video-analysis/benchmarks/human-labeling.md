# Human Labeling Protocol / 人工标注协议

This document defines how community members can contribute human-labeled AIGC/comic samples. It does not require the maintainer to label every sample.

## Current status

- The repository does not claim a formal accuracy score yet.
- Community cases are provisional until reviewed.
- Tool predictions are not accepted as ground truth.
- A credible baseline needs multiple independent human-labeled clips.

## Who can contribute

Anyone who has the right to use and analyze the submitted video can contribute. A sample may be shared as a link, a small authorized excerpt, or a derived contact sheet when redistributing the original video is not allowed.

## What to label

Required for a useful case:

- cut times;
- camera class per shot;
- incoming transition class per shot;
- source metadata: duration, aspect ratio, resolution, and source type.

Optional:

- shot size;
- representative start/middle/end frames;
- short notes explaining an uncertain label;
- whether the cut was a hard cut, dissolve candidate, fade, flash, or wipe candidate.

## Labeling rules

1. Watch the full clip before labeling.
2. Use frame stepping or a media player's precise time display for cut times.
3. Label without looking at this Skill's output first.
4. Do not copy predictions from the Skill into the answer file.
5. Record uncertainty instead of guessing.
6. Use one canonical camera/transition vocabulary per case.
7. Do not upload unauthorized full videos, private URLs, cookies, or account data.

## Suggested vocabulary

Camera:

- static;
- apparent zoom in;
- apparent zoom out;
- horizontal movement;
- vertical movement;
- handheld / unstable;
- unknown.

Transition:

- hard cut;
- dissolve candidate;
- fade through black;
- flash;
- wipe candidate;
- unknown.

## Submission format

Use `schemas/benchmark_cases.schema.json`. One case per issue is preferred. A partial case is still useful if the missing fields are clearly marked.

Include:

- case ID;
- authorization statement;
- video metadata;
- human labels;
- whether the sample can be published or only used privately for evaluation;
- a redacted reproduction command, if relevant.

## Review and claims

A community case is not a public benchmark result by itself. The maintainer may review it for schema validity, authorization, and label consistency. Accuracy claims should be made only from a reviewed set with enough cases and clearly stated tolerances.

See [community-call.md](community-call.md) for a ready-to-post contribution request.
