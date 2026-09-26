# video-operation-review

**面向软件操作录屏的分层审阅技能：还原操作步骤，保留画面。**

适用于建模、编程、数据处理等逐步演示的软件教程。它帮助具备视觉能力的 AI 助手从录屏中整理菜单入口、选中对象、最终参数、确认或取消、文件交接和可见结果，输出可以核对和继续完善的操作记录。

例如，视频里先输入 `0.20`，取消后重新输入 `0.02` 并应用，审阅结果应区分临时输入与最终值；看不清按钮或没有展示执行结果时，会保留疑问。

> 脚本负责视频索引、证据管理和记录检查；操作语义由 AI 助手实际查看图片后判断。

## 主要作用

- **完整帧索引。** 顺序处理视频，记录真实源帧号、原始 PTS 时间戳、精确画面身份和变化线索；支持可变帧率视频及非零起点。
- **分层查看。** 先准备全片分段和代表画面，再对关键操作查看原图、裁剪和前后状态。等待、鼠标移动和闪烁可以在有依据时合并说明，无需默认逐一精审每种像素状态。
- **恢复操作过程。** 记录菜单、对象、参数、确认或取消、输入输出及可见结果，区分临时输入、最终值与未知内容。
- **检查缺口并局部展开。** 检查重叠、状态跳变和缺失；对合并或低优先级区间抽查，发现异常后展开相关窗口。
- **接收字幕和已有转写。** 支持 SRT、VTT、内嵌文本字幕及带明确时间基准的转写 JSON；保留原文、可选译文、来源、偏移和重叠提示。
- **保留审阅进度。** 使用 SQLite 保存索引、证据、查看记录、步骤和疑点；支持暂停后继续，并复用已有结果。

## 环境要求

- Python 3.10 或更新版本。
- NumPy、Pillow；依赖列表见 [requirements.txt](requirements.txt)。
- 可调用的 FFmpeg 与 ffprobe，FFmpeg 需支持 `-fps_mode passthrough`。
- 用于语义审阅的宿主助手需要能读取文件、执行本地命令，并实际查看图片。

**纯文本模型不兼容本 skill。** 模型和当前宿主都必须支持实际图片输入。

已在 Windows 上验证 Python 3.10.11 与 Python 3.12.10，使用 FFmpeg 8.1.2。

如需安装 Python 依赖，建议在自己的虚拟环境中执行：

```text
python -m pip install -r requirements.txt
```


## 开始使用

### 在 Codex 和 DeepSeek Harness 中安装

两边使用同一份 skill 和同一套审阅记录。默认情况下，可将完整仓库放入用户目录下的 `.agents/skills/video-operation-review`。

Windows PowerShell：

```powershell
git clone https://github.com/koocmitwho/video-operation-review.git "$env:USERPROFILE\.agents\skills\video-operation-review"
```

macOS / Linux shell：

```bash
git clone https://github.com/koocmitwho/video-operation-review.git "$HOME/.agents/skills/video-operation-review"
```

若目标目录已存在，先检查其中的版本和本地修改。也可下载 ZIP 后把完整目录放到该位置；确认 `SKILL.md` 紧接在 `video-operation-review` 目录内。

仅用于一个项目时，放入 `<项目根>/.agents/skills/video-operation-review/`。DeepSeek Harness 如使用自定义 `DSH_AGENTS_HOME`，需按实际配置放置；只给 DSH 使用时，也可以放入 `<DSH_HOME>/skills/video-operation-review/`。

| 宿主 | 调用方式 | 看图要求 |
|---|---|---|
| Codex | 明确使用 `$video-operation-review`，或按任务自动选择 | 当前环境提供可用的图片查看工具，例如 `view_image` |
| DeepSeek Harness | 要求使用 `video-operation-review`，由已有的 skill 加载工具读取 | `read_image`、附件服务和支持图像输入的当前模型 |

DeepSeek Harness 需要已启用本地 skill 发现与加载。该仓库按文件系统 skill 使用。详细的目录、工具差异和排查方法见 [宿主适配说明](references/hosts.md)；目录规范参考 [Codex 官方文档](https://learn.chatgpt.com/docs/build-skills) 与 [DeepSeek Harness 官方文档](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/skill/skill-filesystem)。

### 先检查环境

从仓库根目录运行：

```text
python scripts/review_video.py doctor
```

诊断检查当前 Python、NumPy、Pillow、FFmpeg 和 ffprobe，输出 JSON；退出码 0 表示本地处理依赖通过，1 表示存在缺项。它不安装软件或创建审阅数据库。缺少 NumPy/Pillow 时，诊断和 `--help` 仍可使用。

如果桌面宿主没有继承终端的 PATH，可用 `--ffmpeg` / `--ffprobe` 指定完整程序路径，或在同一进程环境设置 `VOR_FFMPEG` / `VOR_FFPROBE`；命令参数优先。使用虚拟环境时，请用同一 Python 解释器安装依赖、诊断和运行脚本。

**依赖检查通过不等于模型具备视觉能力。** 纯文本模型直接标明不兼容并停止审阅；图片模型的工具缺失、文件不可访问等问题则说明具体阻碍。

### 新模型与旧模型兼容

本次以 Codex 的 GPT-6 系列和 DeepSeek Harness 的 DeepSeek-V4.1-Flash（`deepseek-flash`）作为新模型优化基准：按操作关系组织证据、减少重复说明，并针对图片缩放补看局部裁剪。模型基准来自 [OpenAI 模型目录](https://developers.openai.com/api/docs/models) 和 [DeepSeek 更新日志](https://api-docs.deepseek.com/updates/)。

同时兼容仍具备图像输入和必要工具能力的旧模型：上下文较小时缩小每批操作范围，逐批保存并恢复进度；没有异步或子代理工具时使用顺序流程。

新旧型号的具体策略、图片清晰度和能力检查见 [模型适配说明](references/models.md)。型号兼容规则与实际验收结果分别记录。

### 让 AI 助手执行审阅

下载或克隆本仓库后，可以向能访问该目录的助手提出：

> 请按照本目录 `SKILL.md` 的 video-operation-review 流程审阅这段软件教程。先检查已有结果，再做完整索引、分层粗审和关键操作精审。交付可复现的步骤、关键证据及未解决项，分别报告计算覆盖、审阅覆盖和实际看图数量。

技能入口是 [SKILL.md](SKILL.md)。未安装到发现目录时，也可直接让助手读取该文件。宿主从其他工作目录调用时，使用脚本的绝对路径，并为输入视频和 `--work` 明确指定位置。

### 使用命令行准备证据

下面从仓库根目录运行，将输入文件替换为自己的视频。`--work` 应为这个视频专用的审阅目录。

```text
python scripts/review_video.py --help
python scripts/review_video.py scan ./input/tutorial.mp4 --work ./work/tutorial
python scripts/review_video.py plan --work ./work/tutorial
python scripts/review_video.py candidates --work ./work/tutorial
python scripts/review_video.py extract --candidates --work ./work/tutorial
```

这些命令完成索引、分段建议与图片导出。随后由宿主实际打开图片，再登记查看、填写操作记录并导入。完整操作示例和字段说明见：

- [命令示例](references/examples.md)
- [分层审阅与抽查](references/layered-review.md)
- [步骤、证据与统计字段](references/records.md)

### 字幕与转写

```text
python scripts/review_video.py tracks --work ./work/tutorial
python scripts/review_video.py subtitles ./input/narration.srt --work ./work/tutorial --language zh-en --offset 0
python scripts/review_video.py transcript ./input/speech.json --work ./work/tutorial
```

字幕按“字幕时间 + 显式偏移”对齐原始视频时间；转写 JSON 必须声明时间基准。

当前支持字幕和已有转写的输入与对齐；实际语音识别、OCR 推理和自动翻译尚未接入。模块边界及后续方案见 [语言、音频与字幕](references/language.md)。

### 校验与导出

```text
python scripts/review_video.py validate --work ./work/tutorial
python scripts/review_video.py audit --work ./work/tutorial --summary
python scripts/review_video.py export --work ./work/tutorial
```

需要检查当前模式的完整审阅条件时，使用 `validate --require-coverage`。信息不足时允许导出部分结果。

## 输出内容

| 文件 | 内容 |
|---|---|
| `review.sqlite3` | 索引、步骤、证据、查看记录与审阅历史 |
| `layer-plan.json` | 分段建议、代表画面和原始状态映射 |
| `review.json` | 结构化步骤、区间、疑点、统计与审计信息 |
| `frames.jsonl` | 逐帧索引和变化指标 |
| `omission-audit.json` | 覆盖、衔接、抽查和复核检查结果 |
| `report.md` | 便于阅读的操作说明、截图与未解决项 |
| `evidence/` | 按需导出的原图、裁剪和概览拼图 |

输入视频、审阅数据库和证据可能包含使用者自己的内容。它们应保存在各自工作目录。

## 如何理解覆盖统计

本项目分开记录：

1. **全帧计算覆盖**：程序处理过哪些源帧。
2. **粗审覆盖**：哪些时间区间已有含义说明和代表证据。
3. **已进行／已完成精审**：哪些操作已查看关键原图，哪些还保留未解决项。
4. **实际视觉查看登记**：图片工具真正展示后登记的不同源帧数。

同一源帧的原图、裁剪、放大和拼图面板按源帧去重；拼图与原尺寸证据的粒度分别记录。

查看登记仍需与真实工具调用核对。审计通过表示记录满足检查规则。

## 验证情况

2026-09-26 在 Windows / Python 3.10 和 3.12 下分别重新运行，**两套环境均为 98 项脚本测试全部通过**。保留旧严格模式、分层流程、宿主适配和帧数口径修复，并新增裁剪区域复核、调用引用关联、600 个稀疏帧抽取、预算末帧、异常时间戳对齐、FFmpeg 新旧文件滤镜接口和发布副本差异检查。可在准备好依赖后运行：

```text
python -X utf8 -m unittest discover -s scripts/tests -v
```

一次 32 帧合成教程试用中，分层方式实际显示了 18 个不同源帧，严格方式为 32 个；两者均记录了 9 个预设可见状态检查点，最终参数错误为 0。

2026-09-25 在 Windows 上完成两边的技能加载检查，以及 DeepSeek Harness `deepseek-flash` 的实际视觉审阅：对另一段 32 帧合成录屏完成全帧索引、看图、操作记录、校验和导出。55 次成功图片调用覆盖 32 张原图、22 张裁剪和 1 张拼图，真实工具记录与证据哈希已核对；取消值 `0.73`、最终值 `0.04`、文件名 `measurements.csv` 和导入行数 `13` 均识别正确。记录校验通过，素材缺失的点击过程及文件同一性继续保留为疑点，完整审阅门禁未通过。这是历史视觉试用，2026-09-26 的优化验证使用合成测试；macOS 未运行验收，Windows/Linux 的远端结果见对应提交的 [CI](https://github.com/koocmitwho/video-operation-review/actions/workflows/tests.yml)。

详细结果与限制见 [验证说明](references/validation.md) 和 [本次适配验证摘要](validation/host-adaptation.json)。


维护与验收约定见 [分层验收](references/layered-acceptance.md)、[处理方法](references/method.md) 和 [开发来源与发布检查](references/maintenance.md)。发布副本可用 `python scripts/check_release.py --target <发布目录>` 只读核对；新增 CI 配置需以对应提交的实际运行结果为准。
