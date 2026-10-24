# WMMN Video Analysis Skills

> **wmmn · 我密码呢**

Host-invoked video analysis Skills for Codex, Claude Code, and compatible agent hosts.

This repository is a public beta. The engineering pipeline is testable, but real-world accuracy is still being validated with community-submitted, human-labeled samples. Do not treat current outputs as an authoritative creative critique or a guarantee of production quality.

## Skills

| Skill | Purpose | Version |
| --- | --- | --- |
| [`general-video-analysis`](skills/general-video-analysis) | Fast, low-cost structural scan and routing card | 0.1.1 |
| [`professional-video-analysis`](skills/professional-video-analysis) | Professional reverse-engineering draft, camera/transition measurements, time-coded evidence frames, and downstream handoff | 0.4.0 |

## Boundaries

- No media acquisition inside the Skills.
- No browser automation, cookie reading, or credential handling.
- No OCR/VLM performed by the Skill itself.
- No generic aesthetic, narrative, virality, or "why it went viral" judgment.
- No negative-prompt generation. Users must judge negative prompts in their actual model or workflow.
- No production asset chain. Character assets, generation, editing, and final QC belong to the user's downstream workflow.

## Install

Copy the desired skill directory into your host's Skills directory:

```text
skills/general-video-analysis
skills/professional-video-analysis
```

Install the professional dependencies when using mechanical measurements or evidence frames:

```bash
python -m pip install -r skills/professional-video-analysis/requirements.txt
```

## Typical workflow

```text
video URL or host media handle
  -> general-video-analysis
  -> quick_scan.json
  -> host semantic observations + context.json
  -> optional media_mechanics.py
  -> optional evidence_frames.py
  -> professional-video-analysis
  -> report + handoff + machine-readable JSON
```

The host owns media access. If it cannot expose a readable media handle, measurements and evidence frames remain unavailable rather than being invented.

## Community validation

Please report:

- compatibility and acquisition failures;
- incorrect shot boundaries;
- camera or transition classification errors;
- evidence-frame failures;
- human-labeled benchmark cases.

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before submitting video samples. Do not upload media you do not have the right to distribute.

## Attribution and watermark

The visible `wmmn · 我密码呢` watermark is intentional and appears in reports, manifests, scripts, and generated evidence-frame sheets.

## License

No license file has been selected yet. Public visibility does not by itself grant reuse rights. The maintainer must select a license before this repository can be described as OSI-approved open source.
