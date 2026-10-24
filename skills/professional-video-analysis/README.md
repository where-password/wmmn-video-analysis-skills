# Professional Video Analysis Skill

A host-invoked professional planning layer for comics, animation, teaching, and other production-led video.

It consumes the output of `general-video-analysis`, adds domain context, and produces:

- a plain-language feasibility and reproduction report
- a machine-readable shot plan
- a production sequence
- prompt skeletons with per-shot feasibility warnings
- measured camera-motion and transition signatures with confidence
- a portable handoff brief for another model, workflow, or traditional editor
- explicit limits

## Use

When the host can expose a readable media handle, measure camera motion and transitions first:

```bash
python scripts/media_mechanics.py \
  --media-manifest path/to/media_handle.json \
  --scan-json path/to/quick_scan.json \
  --start-shot 1 \
  --end-shot 5 \
  --out path/to/mechanics.json
```

Generate time-coded start/middle/end evidence frames:

```bash
python scripts/evidence_frames.py \
  --media-manifest path/to/media_handle.json \
  --scan-json path/to/quick_scan.json \
  --start-shot 1 \
  --end-shot 5 \
  --out path/to/evidence-output
```

Then build the professional report:

```bash
python scripts/build_analysis.py \
  --scan-json path/to/quick_scan.json \
  --context-json path/to/context.json \
  --mechanics-json path/to/mechanics.json \
  --evidence-json path/to/evidence-output/evidence_manifest.json \
  --out path/to/output
```

## Outputs

- `professional_report.md`
- `professional_handoff.md`
- `professional_analysis.json`
- `evidence_manifest.json` and time-coded evidence frames (separate evidence output)

## Dependencies

The report builder uses the Python standard library. Camera/transition measurement uses:

```bash
pip install -r requirements.txt
```

It also needs `ffmpeg`; `imageio-ffmpeg` supplies a bundled fallback.

## Boundary

This skill does not download or open a browser. It can analyze a readable media handle supplied by the host. It does not read cookies, perform OCR/VLM, or invent semantic facts. Camera and transition values come from deterministic visual measurement or host observation, with confidence and evidence recorded.

Before a detailed batch, the host must inspect the selected shots and populate `context.json`. Without observations, the report stops at a structure-only preview instead of producing five empty “待补充” shots.

## Attribution

wmmn · 我密码呢

## User-facing output

The report starts with a complete judgment, then shows feasibility, reproduction steps, per-shot plan, required assets, and limits.

See `examples/professional_report.example.md`.

## AI-readable output

`professional_analysis.json` contains:

- `verdict`: feasibility status and limits
- `shot_plan`: source-absolute timestamps and per-shot plan fields
- `production_plan`: ordered production steps and owner
- `prompt_pack`: prompt skeletons or missing-input requirements
- `evidence` and `limitations`: traceability and uncertainty

## Progressive output

The default report details the first 5 shots, states the approximate time range those shots cover, and gives only estimated structural segments for the remainder. It ends with A/B/C/D choices so the user controls the next cost. Continue with `--detail-start N --detail-count 5`.

Reports use the actual batch range in the title. Camera motion and transitions are measured from the host media handle when available; apparent zoom is not mislabeled as physical dolly. Prompts are assembled only from observed fields.

The report flags segmentation contradictions such as a fixed-camera shot whose shot size changes, or one detected shot that crosses indoor/outdoor stages. It also suppresses prompts for rows missing scene, action, or shot-size observations, or where host camera notes conflict with measured motion.

`context.json` and the evidence manifest are validated against JSON Schemas. Time-coded evidence frames make analyzed shots traceable without requiring production assets. Formal accuracy claims require a human-labeled benchmark; see `benchmarks/README.md`.

This skill does not generate negative prompts. The report ends with one notice that users should judge and adapt negative prompts in their actual model or workflow. `professional_handoff.md` packages the draft for a new chat, another model, an AI workflow, or traditional editing.

## License

MIT License. See [LICENSE](LICENSE).

Copyright (c) 2026 wmmn (where-password).
