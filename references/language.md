# 语言、音频与字幕

本模块提供媒体轨调查、SRT/VTT/内嵌文本字幕导入、时间偏移、原始 PTS 对齐、重叠提示、原文与译文保存、外部转写 JSON 和缓存。

## 本地接口

路径变量按 [examples.md](examples.md) 设置后运行：

```powershell
& $pythonExe -X utf8 $reviewCli tracks --work $ReviewWork
& $pythonExe -X utf8 $reviewCli subtitles './input/narration.srt' --work $ReviewWork --offset 5 --language zh-en
& $pythonExe -X utf8 $reviewCli subtitles './input/tutorial.mkv' --work $ReviewWork --stream 0 --language zh
& $pythonExe -X utf8 $reviewCli transcript './input/speech.json' --work $ReviewWork
```

--stream 0 表示字幕序号 s:0。FFmpeg 将 sidecar 或内嵌文本字幕转换为规范 SRT，再解析为 cue。输入采用 UTF-8；其他编码可先转换并保留原件。解析错误保存到 logs，并记录 failed attempt；超时使用 helper_timeout。

时间公式为 `original_video_time = subtitle_time + offset_seconds`。内嵌字幕使用 copyts；外部字幕偏移通过音画锚点核对。cue 与帧显示区间按原始 PTS 求交，末帧使用已知 duration，缺失时间按 warning 标记。重叠、正负偏移与超出索引的 cue 保留来源。

## 外部转写格式

外部 ASR 适配器提供以下 UTF-8 JSON，示例值替换为实际转写与来源：

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

video_relative 以源视频首帧 PTS 为零点，额外加 offset_seconds；original 使用原始视频时间。segments 需要有限数值的 start/end、正时长与原文 text。音频窗口输出先换算到该时间基准。

language_sources 的 ID 绑定源内容、偏移、语种/版本与时间索引。相同导入复用；改变偏移或算法版本后另存结果。多份字幕来源分别显示，由审阅者选定当前采用版本。语言来源变化后更新复核快照。

对齐支持重复/倒退 PTS 的重叠显示区间、未知时间附近的已知长时长画面和零时长点。text_original 与 translation 分开保存，保留原文件哈希。讲解用于发现线索，菜单、数值、点击状态和运行结果引用画面证据。

## 扩展接口参考

2026-09-24 按以下固定源码版本核对了接口和根目录 MIT 许可。复用时保留对应版权与许可，并检查所选模型和依赖的授权。

| 来源 | 接口 | 对接方式 |
|---|---|---|
| [mcp-video-analyzer](https://github.com/guimatheus92/mcp-video-analyzer/tree/32973fa066b8071ea5fa708816d0b57ffdab0e66)，0.10.1 | get_transcript；Whisper CLI、HF 或 API | 将原文、时间、来源转换为上述 JSON |
| [video-to-skill](https://github.com/Lum1104/video-to-skill/tree/5e9f97e89855a8a0ea998ba85e179fbc1765d4b7)，0.1.0 | FasterWhisperTranscriber.transcribe | 将 TranscriptSegment 和源时间绑定到本库 PTS |
| [watch-skill](https://github.com/oxbshw/watch-skill/tree/f1317c8fe64744a606c31867b05fbbe3144268c6)，1.4.3 | transcribe_local、Transcript.offset | 将窗口起点与字幕时间统一换算 |

## 扩展验收设计

1. 本地 ASR 适配按所选窗口提取音频，使用明确的模型路径、设备、compute_type、语言和术语提示；保存音频 PTS、窗口起点、模型版本、墙钟时间和可测内存。
2. 语音验收采用人工标注的中文、英文、混合术语和无声样本，报告 CER/WER、术语/数字错误、时间边界误差与重试结果。
3. OCR 适配在已索引原图/裁剪上保存文字框、置信度、引擎和源帧哈希；数值与术语回看原图核对。译文按条保存，原文和术语表持续保留。
4. 用户选择外部服务时，先列出具体片段、传输范围、计价与时长，按授权执行并保存调用来源。

现有字幕与转写接口的实际测试见 [validation.md](validation.md)。
