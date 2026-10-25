# Host Media Adapter Contract

The general video analysis skill is URL-first from the user's perspective.

**视频链接要求：** 请先打开你真正想分析的视频，再从该视频页面复制分享链接。抖音建议从历史记录、点赞或收藏进入目标视频后复制链接；不要把精选、主播主页、推荐流、搜索结果页或截图当作视频链接。

```text
用户给 URL
→ host uses its existing viewer/video-access capability
→ host supplies a readable media handle
→ skill scans the media
```

The host adapter owns acquisition. The skill does not ask the user to choose a browser, cookies, download strategy, or local export.

## Adapter output

Preferred:

```json
{
  "media_path": "media/video.mp4",
  "source_url": "https://example.com/video/123",
  "source_hash": "sha256:...",
  "duration_sec": 127.4,
  "has_audio": true,
  "limitations": []
}
```

The base version requires a readable `media_path`. A frames-only viewer output is not yet supported; the host must materialize the video/audio stream or return blocked.If the host cannot access media, the skill returns `blocked`. It must not invent frames or commentary.

## Host rules

- Do not ask the user to drag a local MP4 when the host viewer can already access the URL.
- Do not expose Cookie/browser-profile decisions to the user.
- Do not use a browser as a persistent background service.
- If the viewer only exposes visual playback and not the media stream, label the analysis as sampled/visual-only and reduce claims accordingly.
- Keep source hashes and cache paths private.


## Provider names

- `host_media_handle`: the host has a local readable media file
- `browser_devtools`: the host captured a media URL/file through browser network inspection
- `public_url`: the skill downloaded a public URL
- `local_file`: the user explicitly supplied a local path

Only `public_url` and `host_media_handle` are exercised by this base skill. `browser_devtools` is a host-side provider implementation; its output must match `schemas/media_handle.schema.json`.


