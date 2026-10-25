# General Video Analysis

一个面向普通视频用户的泛用内容分析 Skill。

它只回答一个核心问题：

> **这条视频讲了什么？**

输出是：

- 一句话内容判断
- 一段内容总结
- 内容类型
- 内容主题
- 相关 IP / 人物（可确认时）
- 内容基调
- 调侃/玩梗对象（适用时）
- 可选的专业方向建议
- 两条简短说明

不向用户展示分辨率、镜头数、切点、关键帧或技术分析表。

## 使用与版权声明

1. 分析结果仅供个人学习、研究和交流参考。
2. 公司、商业或其他组织使用前，用户需自行确认版权、授权和合规责任。
3. 作者仅提供视频分析工具，不提供视频内容授权；不承担因视频或分析结果使用产生的责任，本提示不构成法律意见。

完整说明见 [DISCLAIMER.md](DISCLAIMER.md)。

## 安装后第一次使用

第一次成功生成内容概览时，`build_overview.py` 会自动把 `references/first-run-notice.md` 追加到输出末尾，并在 `.state/first-run-v1.json` 写入一次性标记。后续输出不再重复。

首次输出包含一次性的 `wmmn · 我密码呢` 水印和三行简短提醒：视频来源与使用边界、简短免责声明、准确性反馈渠道。后续正常概览不再显示水印，也不再重复提醒。完整说明见 [DISCLAIMER.md](DISCLAIMER.md)。如果宿主无法写入状态文件，提示可能再次出现。

## 适用范围

它可以处理：

- 剧情、动画、漫剧式内容
- 知识讲解、教程
- 访谈、对话、口播
- 日常 vlog、旅行记录
- 风景、氛围、无声视频
- 产品展示、评测、观点评论
- 段子、贴图口播、混合形式
- 其他不容易归类的视频

广泛性来自对内容的理解，不是把画面里的物体全部列出来。

## 核心原则

### 写内容，不写物体

- 有狗贴图、但人声在讲异地恋，主题是异地恋沟通，不是狗。
- 有人坐在镜头前挥手，动作本身不构成主题；要看视频说了什么。
- 风景视频即使没人说话，也可以有明确内容：自然景观、旅行氛围或视觉体验。

### 不替视频上价值

- 军事题材不等于成长、纪律或传承
- 电竞出征不等于应援或打气
- 粉丝混剪不等于致敬
- 整活视频不等于有严肃社会表达

内容主题写客观内容，内容基调写视频实际的调侃、恶搞、温情、严肃或中性状态。没有证据时保持谨慎，不补“支持、致敬、成长、正能量”等价值判断。

### 识别流行 IP 和公众人物

能确认时，使用大家认识的标准名称，而不是“几位奥特曼”“某个动漫人物”“某个网红”这种泛称。覆盖范围包括：

- 动漫、特摄、漫画、小说、电影、电视剧、游戏
- 电竞、体育、娱乐圈、说唱、网红、虚拟主播
- 作品/IP、角色、真人或虚拟人物、所属领域

只根据标题、标签、字幕、用户说明、标志性服装或明确画面证据确认。相似皮套、换色角色、AI 重绘或相似人脸不能硬猜。只确认作品时写作品，不补角色；低置信度时使用“疑似”并标记 low。

### 技术结构只做内部参考

scan.py 仍会生成内部结构数据和联系表，供模型判断和后续专业 Skill 使用；这些内容不展示给用户。

### 模型观察，不让用户填表

这里的“宿主”指运行 Skill 的模型或 Agent 环境，不是最终用户。

模型负责查看可访问的画面、字幕、逐字稿或音频，并写出 content_analysis.json。用户只需要在真正模糊的地方补充信息，不应该被要求手写场景、人物、动作等字段。

## 使用流程

**视频链接要求：** 请先打开你真正想分析的视频，再从该视频页面复制分享链接。抖音建议从历史记录或收藏进入目标视频后复制链接；不要把精选、主播主页、推荐流、搜索结果页或截图当作视频链接。

### 1. 内部扫描

~~~bash
python scripts/scan.py \
  --source "<LOCAL_VIDEO_OR_URL>" \
  --out "<OUTPUT_DIR>"
~~~

输出：

~~~text
quick_scan.json          # 内部结构数据
quick_scan.md            # 内部结构摘要，不展示给用户
quick_contact_sheet.jpg  # 模型观察用联系表
frames/                  # 抽样帧
~~~

### 2. 模型查看并写内容分析

模型查看联系表、视频、字幕或逐字稿，然后按下面的契约写：

~~~text
schemas/content_analysis.schema.json
examples/content_analysis.example.json
references/content-overview-guide.md
~~~

### 3. 生成用户可见概览

~~~bash
python scripts/build_overview.py \
  --analysis-json "<OUTPUT_DIR>/content_analysis.json" \
  --out "<OUTPUT_DIR>"
~~~

生成：

~~~text
video_overview.md
~~~

在对话中直接展示这份 Markdown，不展示原始 JSON 或内部结构文件。

## 内容分析契约

~~~json
{
  "schema_version": "1.0",
  "one_sentence": "一句话内容判断",
  "summary": "一段内容总结",
  "content_type": ["电竞恶搞 MV", "赛事音乐混剪", "粉丝二创"],
  "themes": ["LPL 2026 国际赛表现", "粉丝整活", "赛事二创"],
  "ip_context": {
    "works": ["LPL", "《八千里路明月照》"],
    "characters": [],
    "people": [],
    "domains": ["电子竞技", "赛事音乐混剪", "粉丝二创"],
    "confidence": "high",
    "evidence": ["用户提供的标题与赛事背景", "画面中的 LPL 赛事与选手"]
  },
  "content_mode": "meme",
  "content_stance": "mocking",
  "content_tone": ["调侃", "恶搞", "赛事吐槽"],
  "mocking_targets": ["LPL 四支队伍的国际赛表现"],
  "tone_basis": ["改编歌词以吐槽成绩为主", "失利画面与捧杯画面形成反差"],
  "routing": {
    "comic_aigc_led": false,
    "longform_knowledge": false
  },
  "basis": ["video", "user_context"]
}
~~~

content_stance 用于内部约束立场，content_tone 和 mocking_targets 用于用户可见的基调说明。非中性内容必须提供 tone_basis。

专业建议由 routing 自动生成：comic_aigc_led 对应漫剧分析，longform_knowledge 对应长视频索引，两项可以同时为真，也可以都为空。

## 专业方向建议

模型只判断两个内部路由字段：

- comic_aigc_led：仅当内容属于漫剧、动画、AIGC 或同类换皮整活，适合进入漫剧专业分析；普通真人 MV、电竞混剪、vlog、产品视频不因“有剪辑”而触发；
- longform_knowledge：内容属于知识型长内容，可通过逐字稿索引定位。

渲染器自动生成柔和建议：

- comic_aigc_led：提示 professional-video-analysis；
- longform_knowledge：提示 long-video-index；
- 两者都有：两个方向都提示；
- 都没有：不强行推荐。

时长不是唯一依据。长系列漫剧如果目标是学习制作，仍然属于漫剧分析方向。Skill 不自动调用另一个 Skill。

## 边界

- 不向用户输出技术规格和镜头统计。
- 不把画面中的对象直接当作视频主题。
- 不判断创作意图、风格优劣、是否失误、传播效果或个人创意价值。
- 不把“没有明确专业方向”表述成“你不需要专业分析”。
- 不编造未读到的内容。
- 不要求用户手填模型可以自行观察的字段。

## 示例

- examples/content_analysis.example.json
- examples/video_overview.example.md

## Tests

~~~bash
python -m unittest discover -s tests -v
~~~

## 作者其他作品

### 《东京，我的男主浓度严重超标》

仅发布于刺猬猫平台。喜欢恋爱喜剧的朋友可以支持一下；不喜欢也欢迎直接吐槽。

作者抖音：我密码呢

## License

MIT License. See [LICENSE](LICENSE).

Copyright (c) 2026 wmmn (where-password).
