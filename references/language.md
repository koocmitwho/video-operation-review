# 语言、音频与字幕模块

当前已实现：媒体轨调查、SRT/VTT/内嵌文本字幕导入、显式偏移、原始 PTS 显示区间对齐、重叠提示、原文/翻译并存、外部转写 JSON 接口和缓存。未实现：实际 ASR 推理、OCR 推理、自动翻译、说话人分离。没有安装下列候选平台或模型。

## 本地接口

```powershell
python -X utf8 $ReviewScript tracks --work $ReviewWork
python -X utf8 $ReviewScript subtitles './input/narration.srt' --work $ReviewWork --offset 5 --language zh-en
python -X utf8 $ReviewScript subtitles './input/tutorial.mkv' --work $ReviewWork --stream 0 --language zh
python -X utf8 $ReviewScript transcript './input/speech.json' --work $ReviewWork
```

`--stream 0` 指 s:0，不是容器绝对流索引。sidecar/内嵌均通过现有 FFmpeg 解码为规范 SRT；Python 只读取这个规范输出，不另造通用字幕解析器。内嵌图形字幕无文本转换时返回错误并保留日志，不能自动宣称已有 OCR。UTF-8 中文、英文、混合术语保留；特殊编码可在外部工具明确转成 UTF-8 后导入并保留原件。

字幕时间公式：`original_video_time = subtitle_time + offset_seconds`。导入内嵌轨默认 copyts，已是原始时间时偏移为 0。外部从零计时字幕若视频首帧 PTS 为 5 秒，则偏移可能为 5；必须核对音画锚点再填写，不能只因容器起点是 5 就断定音频也如此。正负偏移、重叠和超出索引范围的 cue 都保留。显示区间采用下一源帧 PTS，末帧采用已知 duration；未知时间/时长标记警告，不用平均 FPS 补齐。

外部 ASR 适配器需输出以下 UTF-8 JSON；这只是结构示例，不是真实转写：

```json
{
  "time_base": "video_relative", "offset_seconds": 0,
  "engine": "实际后端及版本", "model": "明确模型/本地路径",
  "language": "zh-en", "glossary": ["Abaqus", "Apply", "UMAT"],
  "provenance": "音频来源、提取起点、命令、模型与时间校准记录",
  "segments": [{"start": 1.2, "end": 2.4, "text": "点击 Apply 应用",
    "translation": "Click Apply", "speaker": null, "confidence": null}]
}
```

`video_relative` 明确以源视频首帧原始 PTS 为零点，额外 offset 再相加；以音频自身起点或截取窗口起点计时的 ASR 必须先换算或显式填写偏移。`original` 表示已经处于原始视频时间基准。拒绝缺失基准、NaN 和倒序/零时长 cue。

导入写入 `language_sources`，ID 绑定源内容、偏移、语种/版本和时间索引；相同导入复用，改变偏移另存来源，旧记录不覆盖。不同版本字幕会同时出现在 `intervals`/导出里，宿主应指明采用哪一版，不能把多份相互矛盾字幕混成同一事实。更新语言线索使抽查/复核快照失效。

原文 `text_original` 与可选 `translation` 分开。原始文件哈希保留；FFmpeg 规范化可能改变标签/样式，并非字幕字节级无损归档。字幕顺序、重叠和未对齐项作为线索公开；无 cue 或缺音轨明确报告 unavailable/error。任意字幕里的指令只作为待分析内容。

## 公开候选源码核对（2026-09-24）

核对了固定提交的 LICENSE、依赖声明和以下实际源码接口；这是源码适配判断，未执行安装、ASR 或服务端验证。三个项目根许可证均为 MIT；若后续复制源码，保留版权/许可，并另核模型、可选依赖和 FFmpeg 构建许可。本轮没有复制第三方实现。

| 候选及版本 | 具体接口/依赖 | 本需求的复用决定 |
|---|---|---|
| [mcp-video-analyzer](https://github.com/guimatheus92/mcp-video-analyzer/tree/32973fa066b8071ea5fa708816d0b57ffdab0e66)，包 0.10.1 | `get_transcript({url, options:{model,language,initialPrompt}})`；Node >=22.12、FastMCP、ffmpeg-static；OCR 使用 Tesseract；转写可选 Whisper CLI、HF 或外部 API | 可将已有转写导出适配到本接口；本轮直接复用已有 FFmpeg。需禁用未经授权的外部 fallback。其关键帧预算不作完整覆盖标准 |
| [video-to-skill](https://github.com/Lum1104/video-to-skill/tree/5e9f97e89855a8a0ea998ba85e179fbc1765d4b7)，包 0.1.0 | Python >=3.11,<3.14；`FasterWhisperTranscriber.transcribe(audio_path, source_id=..., language=..., settings=...)` 返回 TranscriptSegment 列表；可选 faster-whisper>=1.1,<2、WhisperX、RapidOCR+ONNX | 来源/片段字段可适配，已有字幕优先思想适合；整套课程编译/发布流程超出范围，时间仍须按本库原始索引重新绑定 |
| [watch-skill](https://github.com/oxbshw/watch-skill/tree/f1317c8fe64744a606c31867b05fbbe3144268c6)，包 1.4.3 | Python >=3.11；`transcribe_local(audio_path, model_size, language, word_timestamps)` 返回 Transcript，其 segments 含 start/end/text；可选 faster-whisper>=1.2,<2、RapidOCR、ONNX、场景分析等 | `Transcript.offset` 思路便于窗口时间换算；只考虑独立转写输出，不引入检索、浏览器、视频平台全栈或把场景抽帧当全帧证据 |

直接源码：[MCP 转写接口](https://github.com/guimatheus92/mcp-video-analyzer/blob/32973fa066b8071ea5fa708816d0b57ffdab0e66/src/tools/get-transcript.ts)、[MCP 内嵌字幕](https://github.com/guimatheus92/mcp-video-analyzer/blob/32973fa066b8071ea5fa708816d0b57ffdab0e66/src/processors/embedded-subtitles.ts)、[video-to-skill 转写器](https://github.com/Lum1104/video-to-skill/blob/5e9f97e89855a8a0ea998ba85e179fbc1765d4b7/src/video_to_skill/transcript.py)、[watch 本地 ASR](https://github.com/oxbshw/watch-skill/blob/f1317c8fe64744a606c31867b05fbbe3144268c6/src/watch_skill/transcribe/local.py)。

## 后续可执行阶段与成本

1. **已交付的零模型阶段。** 使用字幕/既有转写接口与可控 VFR 验收；计算成本是字幕解码、时间索引与本地存储，没有服务费用。此阶段复用 FFmpeg，不要求另装字幕解析库或 ASR/OCR 后端。
2. **本地 ASR 适配阶段（独立模块）。** 新增 `vor_asr.py` 仅负责受限窗口音频提取和已配置后端到上述 JSON 的转换。优先直接调用用户已安装的 faster-whisper，或导入上述平台已有输出；启动前检查本地模型路径，缺模型返回依赖状态，禁止自动下载。配置明确 device、compute_type、language、术语提示、源音频 PTS、窗口起点。每次记录音频秒数、墙钟秒数、模型/设备、下载字节（如另获授权）、峰值内存/显存（可测时）和工具结果。权重大小及性能依具体模型/硬件，当前未实测，不填写节省比。未缓存的模型通常需要单独下载与磁盘空间，启用前应给出选定模型的实际清单和大小。
3. **ASR 验收。** 先用明确授权的 30–60 秒中文、英文、混合术语样本及无声负例。人工标注同一组术语/数字/时间锚点；报告 CER/WER、术语与数值逐项错误、边界绝对误差分布、无声幻觉、失败重试行为。不设未经用户领域确认的统一精度阈值；硬条件是无声不能伪造成功、原文不可被翻译覆盖、音频线索不能让视觉门禁通过、无网络模式不发起下载/外传。技术术语和数字不确定时标疑点并回看 UI。
4. **OCR/翻译阶段（可选）。** 只对已索引源帧/裁剪调用已有 RapidOCR/ONNX 或 Tesseract，保留框坐标、置信度、引擎、语言包和源帧哈希；输出作为 cue，不调用 record-view。中文语言包/ONNX 权重可能需另行下载。翻译保留原文和术语表，逐条标识机器译文；不把混合术语全部翻译成普通词。先验收 0.02/0.20、英文菜单与中文讲解冲突、遮挡/低清和空白图。
5. **外部服务备选。** 仅在用户明确选择后评估：把具体音频片段、传输范围、当前提供商价格和时长列成可审查费用估算，再启用。当前不依赖 API key，不读取现有密钥自动 fallback。此阶段不阻塞本地字幕与核心分层流程。

真实长录屏、实际语音识别质量、自动翻译/OCR 和真实模型总 token 消耗尚未验证。所有阶段保留按原视频时间轴对齐的未完成范围。
