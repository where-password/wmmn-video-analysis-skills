# Contributing

## Before submitting

- Use the latest release.
- Remove personal paths, cookies, tokens, private URLs, and account identifiers from logs.
- Do not submit media you do not own or have permission to redistribute.
- Do not present automated predictions as ground truth.

## Useful reports

A useful bug report includes:

- Skill name and version;
- host/agent environment;
- source type: local file, host media handle, or public URL;
- general scan status;
- mechanics status;
- evidence-frame status;
- redacted error message;
- expected result and actual result;
- proof that the submitted media is authorized, if media is attached.

## Long-video reports

For long-video-index, include:

- transcript format and encoding;
- whether the transcript came from human subtitles or ASR;
- a redacted excerpt around the missed timestamp;
- the original query and expected timestamp;
- whether locate.py returned no_matches or a wrong quote.

Do not upload a full private transcript unless you have the right to share it. A small synthetic reproduction is preferred.

## Community benchmark submissions

Community cases are exploratory until reviewed.

A benchmark case should include:

- `quick_scan.json`;
- `mechanics.json` when camera/transition accuracy is evaluated;
- human-labeled cut times;
- human-labeled camera classes;
- human-labeled transition classes;
- video metadata such as resolution, aspect ratio, and compression;
- an authorization statement.

Never reuse an automated prediction as its own ground truth.

## Privacy

Do not open issues containing:

- passwords or access tokens;
- Cookie databases;
- private media URLs;
- full local filesystem paths;
- personal contact information;
- private workflow or client data.
