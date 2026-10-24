# General Video Analysis Skill

一个面向 Agent 宿主的轻量视频结构分析 Skill。

它只回答一个很窄的问题：

> **这条视频在镜头结构上是什么类型，是否值得进入后续专业拆解？**

它不会判断视频为什么好看、为什么好笑、有没有网感，也不会生成叙事影评。

## What it does

- 读取视频元数据
- 检测镜头与切点
- 计算切镜密度和镜头时长中位数
- 生成 8 帧联系表
- 给出完整、简短的视频结构判断
- 如果是多镜头内容，推荐后续 `professional-video-analysis`
- 如果是超长视频，推荐 `long-video-index`
- 如果是单镜头固定内容，明确返回“不适用”

## What it does not do

- 不评价叙事、审美、幽默、个人风格或传播效果
- 不做 OCR、VLM 描述、运镜分类、转场分类或连续性审计
- 不构建长视频语料库
- 不自动读取 Cookie
- 不启动后台浏览器
- 不要求用户额外拖入本地 MP4

## Install

```bash
pip install -r requirements.txt
```

URL 获取能力是可选的：

```bash
pip install -r requirements-optional.txt
```

依赖必须提前安装。Skill 不应在分析过程中临时 `pip install`。

## Inputs

### 1. Local media or public URL

```bash
python scripts/scan.py --source "<LOCAL_VIDEO_OR_PUBLIC_URL>" --out "<OUTPUT_DIR>"
```

### 2. Host-provided media manifest

当宿主已经通过自己的视频查看、浏览器或 DevTools 能力取得媒体时，传入标准媒体句柄：

```bash
python scripts/scan.py --media-manifest "<MEDIA_HANDLE_JSON>" --out "<OUTPUT_DIR>"
```

媒体句柄契约见：

- `ACQUISITION_CONTRACT.md`
- `schemas/media_handle.schema.json`
- `examples/media_handle.example.json`

这使 Skill 不绑定具体模型。GPT、Claude、Codex 或本地 helper 只要能产出同一个 `media_path`，就能使用它。

## User-facing output

宿主必须把结构判断直接展示给用户，而不是只列文件。

示例：

```text
这是一条约 60 秒的高密度快剪/混剪视频，核心靠连续切镜和画面变化推进。

结构判断：
检测到约 58 个镜头、57 个切点，平均 0.8 秒一个镜头。
具体题材（整活、风景、音乐等）不能只靠镜头结构可靠确认。

适不适合专业拆解：
适合，推荐 professional-video-analysis。

不能保证：
不能判断为什么好看、为什么好笑、有没有网感，也不能复刻个人风格。
```

## Files written

```text
quick_scan.md
quick_scan.json
quick_contact_sheet.jpg
frames/
```

`quick_scan.json` 是机器接口；`quick_scan.md` 是用户可见卡片的主内容；联系表是视觉附件。

## Optional arguments

```bash
--window 0:30
--max-analysis-sec 120
--scene-threshold 0.35
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## Related skills

This is the entry point of a small skill ecosystem:

- **Professional Video Analysis** — planned; professional decomposition for comics, animation, teaching, and other rigid production structures.
- **Long Video Index** — planned; transcript-first index, topic location, and retrieval for tens or hundreds of hours.

See [NEXT_SKILLS.md](NEXT_SKILLS.md). The host agent owns routing; this package does not silently install or invoke another skill.

## Watermark and provenance

The visible attribution is **wmmn / 我密码呢**. It appears in the skill metadata, source headers, JSON artifacts, Markdown output, and contact-sheet image.

Open-source code can always be forked or modified. The goal is not impossible DRM; the goal is that attribution removal is obvious and unofficial derivatives are easy to identify. Release hashes and Git history provide additional provenance.

## Security and media policy

- 不读取或写入 Cookie。
- 不记录浏览器登录态。
- 不把媒体文件、缓存或个人路径放入公开包。
- 只分析宿主已经有权访问的媒体。
- 本仓库不包含第三方视频素材。

## License

MIT License. See [LICENSE](LICENSE).

Copyright (c) 2026 wmmn (where-password).

## Author

wmmn · 我密码呢

