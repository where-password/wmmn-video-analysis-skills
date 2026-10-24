# Changelog

## 0.4.1 - 2026-10-24

- Add the MIT License to the standalone skill package.
- Declare the license in the skill metadata and package manifest.
- Update the README license statement for MIT distribution.

## 0.4.0 - 2026-10-24

- Add formal `context.json` Schema validation and duplicate shot-id checks.
- Add time-coded start/middle/end evidence frame extraction with watermarks and SHA-256 hashes.
- Add evidence contact sheets and manifest Schema validation.
- Mark handoff ready only when both semantic observations and evidence frames exist.
- Add a human-labeled benchmark harness for cut, camera, transition, and cross-variant stability metrics.
- Add benchmark protocol, case Schema, example, and CI dependency installation.

## 0.3.2 - 2026-10-24

- Suppress prompt generation when scene, action, or shot-size observations are missing.
- Flag conflicts between host camera notes and measured camera motion.
- Make continuation labels follow the requested batch count.
- Label anchors as batch-relative in later batches.
- Move the negative-prompt policy to the final report notice.
- Validate blocked mechanics output and observation-gating fields against schemas.

## 0.3.1 - 2026-10-24

- Remove all generated negative prompts from reports, handoff files, prompt packs, and JSON.
- Add one closing policy notice telling users to judge negative prompts in their actual model or workflow.
- Add per-shot feasibility gates for camera/framing conflicts, scene changes inside a shot, and likely missed cuts.
- Stop presenting conflicted long shots as directly promptable single shots.
- Reduce repeated output and replace generic evidence-status lines with concrete feasibility status.

## 0.3.0 - 2026-10-24

- Add deterministic camera-motion measurement from a host-provided media handle.
- Add incoming-transition measurement: hard cut, fade-through-black, flash, dissolve candidate, wipe candidate, and unknown.
- Add first-transition and first-movement anchors plus a smaller opening-to-first-transition unit.
- Add shot-specific image and video negative prompts derived from observed risks.
- Add `professional_handoff.md` for new chats, other models, AI workflows, and traditional editors.
- Mark the report explicitly as a first-pass reverse-engineering draft.
- Add confidence, evidence source, and open questions to the machine-readable output.

## 0.2.1 - 2026-10-24

- Use the actual batch range in report titles and opening copy.
- Assemble factual prompt drafts from host observations instead of padding missing prompts.
- Distinguish observed, partially observed, and unverified shots.
- Stop at a structure-only preview when no visual observations are available.
- Add action/camera prompts and clearer per-shot evidence status.
- Validate the completed-output schema against the progressive example.

## 0.2.0 - 2026-10-24

- Progressive batch output.
- First five shots are detailed by default.
- Remaining shots are summarized in estimated structural segments.
- A/B/C/D continuation choices.
- General and tool-friendly prompt templates.
- Prompt usage notice added.

## 0.1.0 - 2026-10-24

- Initial professional analysis planning layer.
- Consumes general-video-analysis quick scans.
- Adds domain context and production profiles.
- Produces user-facing reports and machine-readable plans.
- Preserves unobserved camera/transition fields instead of inventing them.
