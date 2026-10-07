# video-operation-review

简体中文 | [English](README.en.md)

固定版本预发布候选：**0.1.0-rc.5**。版本号见 [VERSION](VERSION)，本次步骤纠错与验收范围见 [RC.5 说明](references/release-rc5.md)；历史候选见 [RC.4 说明](references/release-rc4.md)、[RC.3 说明](references/release-rc3.md)、[RC.2 说明](references/release-rc2.md) 和 [RC.1 说明](references/release-candidate.md)。

**面向软件操作录屏的分层审阅技能：还原操作步骤，保留画面。**

适用于建模、编程、数据处理等逐步演示的软件教程。它帮助具备视觉能力的 AI 助手从录屏中整理菜单入口、选中对象、最终参数、确认或取消、文件交接和可见结果，输出可以核对和继续完善的操作记录。

例如，视频里先输入 `0.20`，取消后重新输入 `0.02` 并应用，审阅结果应区分临时输入与最终值；看不清按钮或没有展示执行结果时，会保留疑问。

> 脚本负责视频索引、证据管理和记录检查；操作语义由 AI 助手实际查看图片后判断。

RC.5 增加[带历史的同库步骤纠错](references/records.md)及[新来源 Python 操作案例](examples/open-cases/python-exception-20261007/README.md)。三组代理配对均避免重建，总耗时没有稳定下降；未建立真人可靠性或总体省时。分组算法与审阅完成条件保持原样，已有退休历史的库须使用 RC.5 或更新版本继续维护。

## 主要作用

- **完整帧索引。** 顺序处理视频，记录真实源帧号、原始 PTS 时间戳、精确画面身份和变化线索；支持可变帧率视频及非零起点。
- **分层查看。** 先准备全片分段和代表画面，再对关键操作查看原图、裁剪和前后状态。等待、鼠标移动和闪烁可以在有依据时合并说明，按操作单元逐层精审。
- **恢复操作过程。** 记录菜单、对象、参数、确认或取消、输入输出及可见结果，区分临时输入、最终值与未知内容。
- **检查缺口并局部展开。** 检查重叠、状态跳变和缺失；对合并或低优先级区间抽查，发现异常后展开相关窗口。
- **接收字幕和已有转写。** 支持 SRT、VTT、内嵌文本字幕及带明确时间基准的转写 JSON；保留原文、可选译文、来源、偏移和重叠提示。
- **保留审阅进度。** 使用 SQLite 保存索引、证据、查看记录、步骤和疑点；支持暂停后继续，并复用已有结果。
- **同库更正误设步骤。** 带理由退休或替代步骤，保留原记录和关联历史；非法纠错整批回滚，旧复核结论失效，未解决疑点和异常展开继续保留。

## 环境要求

- Python 3.10 或更新版本。
- NumPy、Pillow；依赖列表见 [requirements.txt](requirements.txt)。
- 可调用的 FFmpeg 与 ffprobe，FFmpeg 需支持 `-fps_mode passthrough`。
- 用于语义审阅的宿主助手需要能读取文件、执行本地命令，并实际查看图片。

模型和当前宿主都需支持实际图片输入；不支持图像输入的纯文本模型无法完成审阅。

已在 Windows 上验证 Python 3.10.11 与 Python 3.12.10，使用 FFmpeg 8.1.2。
当前覆盖单视频流与常见 8-bit 编码；高位深、动态分辨率和其他平台组合未验证。

视频输入仅接受本地自包含的 Matroska/WebM、AVI、MOV/MP4 文件，按实际内容和内部引用检查，不以扩展名放行。播放列表、拼接清单、图像序列、引用外部媒体的 MOV/MP4 及其他格式会被拒绝；已有审阅库的源文件也要满足此边界。独立字幕继续支持 UTF-8 SRT/VTT。具体限制见 [处理方法](references/method.md)。

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
| Codex | 明确使用 `$video-operation-review` | 当前环境提供可用的图片查看工具，例如 `view_image` |
| DeepSeek Harness | 要求使用 `video-operation-review`，由已有的 skill 加载工具读取 | `read_image`、附件服务和支持图像输入的当前模型 |

DeepSeek Harness 需要已启用本地 skill 发现与加载。该仓库按文件系统 skill 使用。详细的目录、工具差异和排查方法见 [宿主适配说明](references/hosts.md)；目录规范参考 [Codex 官方文档](https://learn.chatgpt.com/docs/build-skills) 与 [DeepSeek Harness 官方文档](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/skill/skill-filesystem)。

### 先检查环境

这一步由执行技能的代理完成。从仓库根目录运行；安装为技能后按 [hosts.md](references/hosts.md) 改用绝对路径：

```text
python scripts/review_video.py doctor
```

诊断检查当前 Python、NumPy、Pillow、FFmpeg 和 ffprobe，输出 JSON；退出码 0 表示本地处理依赖通过，1 表示存在缺项。诊断和 `--help` 使用标准库即可运行。

如果桌面宿主没有继承终端的 PATH，可用 `--ffmpeg` / `--ffprobe` 指定完整程序路径，或在同一进程环境设置 `VOR_FFMPEG` / `VOR_FFPROBE`；命令参数优先。使用虚拟环境时，请用同一 Python 解释器安装依赖、诊断和运行脚本。

处理环境就绪后，实际打开一张导出的证据，确认宿主图片工具与模型图像输入链路。

### 新模型与旧模型兼容

本次以 Codex 的 GPT-6 系列和 DeepSeek Harness 的 DeepSeek-V4.1-Flash（`deepseek-flash`）作为新模型优化基准：按操作关系组织证据、减少重复说明，并针对图片缩放补看局部裁剪。模型基准来自 [OpenAI 模型目录](https://developers.openai.com/api/docs/models) 和 [DeepSeek 更新日志](https://api-docs.deepseek.com/updates/)。

同时兼容仍具备图像输入和必要工具能力的旧模型：上下文较小时缩小每批操作范围，逐批保存并恢复进度；没有异步或子代理工具时使用顺序流程。

新旧型号的具体策略、图片清晰度和能力检查见 [模型适配说明](references/models.md)。型号兼容规则与实际验收结果分别记录。

### 由你的代理执行审阅

安装后，向能访问视频的 AI 助手明确调用技能：

> 请使用 `$video-operation-review` 审阅这段软件教程，给出可以照做的步骤、各对象的最终参数、关键截图和仍需确认的地方。

技能入口是 [SKILL.md](SKILL.md)。未安装到发现目录时，也可直接让助手读取该文件。它负责环境检查、选择工作目录、运行脚本、实际看图、记录与导出；用户无需学习命令或填写 JSON。已有素材、范围和模型设置会继续使用，时间或用量预算可按需要提出。

代理优先复用已有审阅目录；新工作使用你指定的位置，否则放在当前任务可写目录中的 `video-reviews/<视频名>/`，并告诉你实际路径。阶段反馈说明已核对的内容与下一步；暂停时给出结果位置和可交给新聊天的继续回执。恢复沿用已有记录，缓存前缀回放仍可能需要时间。

最终说明先列可复现步骤、按对象与阶段整理的最终参数、关键截图和关联时间的疑点，再附覆盖统计与记录。参见 [完整交付示例](examples/tutorial/report.md) 和 [进度、恢复与交付指引](references/delivery.md)。

### 使用命令行准备证据

以下是供代理调用及调试的命令参考。从仓库根目录运行，将输入文件替换为本轮视频；从其他工作目录调用时使用脚本绝对路径。`--work` 应为这个视频专用的审阅目录。

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

本技能不做语音识别、OCR 推理和自动翻译：转写由外部 ASR 适配器产出后以 JSON 导入，没有现成字幕的音频不会被自动转写。接口与依赖见 [语言、音频与字幕](references/language.md)。

代理会说明本次是否利用了旁白及所用来源；只有音轨而没有转写时，报告明确标注“旁白未转写”。

### 校验与导出

```text
python scripts/review_video.py validate --work ./work/tutorial
python scripts/review_video.py audit --work ./work/tutorial --summary
python scripts/review_video.py export --work ./work/tutorial
```

`valid` 表示源文件、证据哈希与记录完整性；`review_complete` 表示候选查看和当前复核门禁完成。默认 validate 按 valid 返回 0/1；`--require-coverage` 将完整审阅加入退出条件，但不改变 valid 的含义：有效记录尚未完成时返回 `valid=true`、`review_complete=false` 和退出码 1，原因见 `coverage_errors`。`--rehash-source` 显式重算源文件哈希，结果中的 rehashed 记录本次行为。export 支持分阶段交付并保留当前状态。

导入步骤和疑点时，ID 必须为非空字符串，在同一批的各自列表内唯一；分批使用相同 ID 更新仍受支持。已知字段的类型错误会在写入前拒绝，错误指出字段位置。旧库中的非法步骤或疑点会被诊断并阻止导出，保留原记录供修正。报告将可定位的审计冲突或证据缺口标到对应步骤和参数，保留原值及依据；它仍不能自动判断自由文字是否符合画面。详见 [记录契约](references/records.md)。

## 输出内容

| 文件 | 内容 |
|---|---|
| `review.sqlite3` | 索引、步骤、证据、查看记录与审阅历史 |
| `layer-plan.json` | 分段建议、代表画面和原始状态映射 |
| `review.json` | 结构化步骤、区间、疑点、统计与审计信息 |
| `frames.jsonl` | 逐帧索引和变化指标 |
| `omission-audit.json` | 覆盖、衔接、抽查和复核检查结果 |
| `report.md` | 便于阅读的操作说明、截图与未解决项 |
| `export-manifest.json` | 本次导出的代次标识及上述四份交付文件的大小、SHA-256 |
| `evidence/` | 按需导出的原图、裁剪和概览拼图 |

读取新导出时，先确认没有 `export.pending.json`，再核对 `export-manifest.json` 的 `state=complete`、代次和四个文件摘要。若存在 pending，保留它及指向的 `.export-*` 暂存目录和 `previous` 备份，核对或恢复上一代后再处理；不要直接删除标记以强行继续，程序也不会自动恢复。文件组切换不具备跨文件的断电原子性。旧导出没有清单时按旧格式处理，无需删除；完整检查规则见 [记录契约](references/records.md)。

输入视频、审阅数据库和证据可能包含使用者自己的内容。它们应保存在各自工作目录。
每个 `--work` 由一个记录者串行写入；多位审阅者各自产出记录后按 ID 导入。

## 如何理解覆盖统计

本项目分开记录：

1. **全帧计算覆盖**：程序处理过哪些源帧。
2. **粗审覆盖**：哪些时间区间已有含义说明和代表证据。
3. **已进行／已完成精审**：哪些操作已查看关键原图，哪些还保留未解决项。
4. **实际视觉查看登记**：图片工具真正展示后登记的不同源帧数。

同一源帧的原图、裁剪、放大和拼图面板按源帧去重；拼图与原尺寸证据的粒度分别记录。

审计核对记录一致性与区间覆盖；查看登记是自报值，不构成独立核实。

## 验证情况

2026-10-02 的审阅完整性修复验收在隔离 Git 副本中完成：Windows / Python 3.12.10 与 3.10.11 各 181 项测试通过，无失败、无跳过，分别耗时 163.798 秒与 214.210 秒。此处记录版本号更新前的修复阶段结果，不代替 RC.3 发布候选重测或对应提交的远端 CI。八份旧账本的隔离副本仍均为 `valid=true`、`review_complete=false`；六个原疑点保留。公开合成短例实际查看 5 张图片后完成阶段导出，四文件清单哈希和代次一致；这不是独立人工语义准确率。脱敏范围与限制见 [修复验收摘要](validation/fixes-20261002.json)，发布兼容变化见 [RC.3 说明](references/release-rc3.md)。

2026-10-01 的[本地修复复核](references/rc1-repair.md)确认了验收整理脚本重复执行丢失观察值、重复追加补查以及记录文字矛盾；生产 CLI 实现未改。一个 38 秒真实片段的 AI 草稿经用户确认，作为该片段的核对基准，不能代表盲标注或其他视频的准确率。6 个原疑点和 8 份未完成审阅仍保留。`0.1.0-rc.2` 收录脱敏摘要、整理补丁及可选回归，详见 [RC.2 说明](references/release-rc2.md)。

2026-09-30–2026-10-01准备`0.1.0-rc.1`：两套Windows/Python环境各152项回归，151通过、1跳过，无失败；有限短片内部复核实际118次图片调用、101个不同clip源帧。8份记录有效、完整审阅均未完成；原6疑点保留，3项补到新信息，数值读法分歧保留null。没有独立人工标注、token实测或该候选的远端CI。见 [候选复核摘要](validation/rc-20260930.json) 与 [候选说明](references/release-candidate.md)。

2026-09-29 完成代理执行指引与报告交付改进。Windows / Python 3.12.10、3.10.11 各运行 145 项检查，均无失败；主目录各跳过 1 项 Git 索引检查，已在发布副本的 15 项文档检查中补验。最后的疑点影响展示修补另在两套环境通过 12 项报告用例。三位代理分别审阅同一真实录屏的 8、26、38 秒片段，共计算 1368 帧、实际调用图片工具 138 次，按各片段源身份去重为 128 帧；三份记录完整性通过，保留 6 个素材或交接疑点，完整审阅门禁未通过。结果见 [本轮验收摘要](validation/agent-delivery-20260929.json)；可直接打开 [自建交付示例](examples/tutorial/report.md)。

2026-09-27 修复后，Windows / Python 3.12.10 与 3.10.11 **均通过 132 项测试（新增 34 项）**，串行运行耗时分别为 93.525 秒、135.805 秒。日志：[Python 3.12](validation/tests-fixes-20260927.log)、[Python 3.10](validation/tests-fixes-python310-20260927.log)。`doctor` 与合成 GUI 手工端到端通过；[修复摘要](validation/fixes-20260927.json) 保存本轮结果。

1080p、120 帧素材的三组扫描中位耗时为 7.170 → 7.205 秒，Python 峰值工作集为 82.92 → 83.28 MiB，逐帧指标哈希一致。[测量数据](validation/performance-1080p-20260927.json)。

2026-09-27 在 Windows / Python 3.12.10 单套环境重跑干净的 98 项基线，全部通过，87.304 秒。[完整日志](validation/tests-98.log) 保留实际输出。

2026-09-26 在 Windows / Python 3.10 和 3.12 下分别重新运行，**两套环境均为 98 项脚本测试全部通过**。保留旧严格模式、分层流程、宿主适配和帧数口径修复，并新增裁剪区域复核、调用引用关联、600 个稀疏帧抽取、预算末帧、异常时间戳对齐、FFmpeg 新旧文件滤镜接口和发布副本差异检查。可在准备好依赖后运行：

```text
python -X utf8 -m unittest discover -s scripts/tests -v
```

一次 32 帧合成教程试用中，分层方式实际显示了 18 个不同源帧，严格方式为 32 个；两者均记录了 [预设关键状态 9 项](validation/layered-trial-truth.json)（原试用汇总），最终参数错误为 0。

该预设与原代理答案用于内部回归，不能作为独立人工标准答案或语义准确率。

2026-09-25 在 Windows 上完成两边的技能加载检查，以及 DeepSeek Harness `deepseek-flash` 的实际视觉审阅：对另一段 32 帧合成录屏完成全帧索引、看图、操作记录、校验和导出。55 次成功图片调用覆盖 32 张原图、22 张裁剪和 1 张拼图，作者核对了工具记录与证据哈希，收据未随仓库公开；取消值 `0.73`、最终值 `0.04`、文件名 `measurements.csv` 和导入行数 `13` 均识别正确。记录校验通过，素材缺失的点击过程及文件同一性继续保留为疑点，完整审阅门禁未通过。此处记录历史视觉试用，2026-09-26 的优化使用合成测试；Windows/Linux 远端结果见对应提交的 [CI](https://github.com/koocmitwho/video-operation-review/actions/workflows/tests.yml)。

已有合成素材、真实短片及三段同源片段的代理试用。用户在软件内照做的验收、长录屏完整流程的吞吐与内存尚未测量；上述性能数据仅覆盖 1080p / 120 帧。

详细结果与测量条件见 [验证说明](references/validation.md) 和 [本次适配验证摘要](validation/host-adaptation.json)。


维护与验收约定见 [分层验收](references/layered-acceptance.md)、[处理方法](references/method.md) 和 [开发来源与发布检查](references/maintenance.md)。发布副本可用 `python scripts/check_release.py --target <发布目录>` 只读核对；CI 实际结果见对应提交的 Actions 运行记录。

许可：[MIT](LICENSE)。
