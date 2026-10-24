# Benchmark Protocol

This directory defines how to validate the professional analysis skill against human-labeled real videos.

The package intentionally does **not** ship a claimed accuracy score. A valid benchmark requires human annotations and multiple real clips. Automated predictions must never be reused as their own ground truth.

## Required coverage

- At least 20 real clips for a credible first benchmark.
- Multiple domains: comic drama, dialogue/口播, action/edit, teaching, gameplay.
- Multiple aspect ratios: 16:9, 9:16, 4:3, 21:9 where relevant.
- Multiple resolutions and compression levels.
- Human labels for cut times, camera class, and incoming transition class.

## Per-case workflow

1. Run `general-video-analysis` to produce `quick_scan.json`.
2. Run `media_mechanics.py` for the shots being evaluated.
3. Annotate cut times, camera classes, and transition classes manually.
4. Record paths and labels in a case manifest matching `schemas/benchmark_cases.schema.json`.
5. Run:

```bash
python scripts/evaluate_benchmark.py \
  --cases path/to/benchmark_cases.json \
  --out path/to/benchmark-output \
  --tolerance 0.25 \
  --min-cases 20
```

## Metrics

- cut precision, recall, F1;
- miss rate and false-positive rate;
- mean absolute cut-time error;
- camera-class accuracy;
- transition-class accuracy;
- cross-variant stability.

A report with fewer than `--min-cases` is marked `provisional` and must not be presented as a formal accuracy claim.
