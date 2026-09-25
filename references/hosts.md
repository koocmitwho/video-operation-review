# Codex 与 DeepSeek Harness 适配

本技能共用一个 `SKILL.md` 和一套 Python 脚本。宿主负责执行本地命令、把图片送给支持图像的模型，以及提供实际工具调用引用。目录发现、脚本能运行、图片能看懂是三个不同的验收层次。

纯文本模型不兼容本 skill；识别到纯文本模型后直接说明并停止审阅。新模型基准和旧视觉模型的兼容策略见 [models.md](models.md)。

## 共同准备

1. 从当前加载的 `SKILL.md` 路径确定技能根。脚本位于它的 `scripts/review_video.py`，相对参考文件也从技能根解析。
2. 选择已安装依赖的 Python 解释器；显式调用它，不假定系统 `python` 与终端或虚拟环境一致。
3. 运行 `doctor`。缺项时检查同一解释器和当前宿主进程 PATH；命令返回 JSON，退出码 0 表示本地处理依赖通过，1 表示存在缺项。诊断不创建审阅库、不安装依赖、不测试模型。
4. 对本轮素材使用独立、可写的 `--work`。图片工具若运行在另一主机，先确认它能访问导出的同一图片；本机路径不代表远端存在文件。
5. 对实际导出的证据使用当前宿主图片工具。只有收到可见图片并完成观察后才登记查看；模型或工具拒绝图片时保留待审阅状态。

以下 PowerShell 示例从任何工作目录运行；安装位置不同时修改 `$skillRoot`，使用虚拟环境时修改 `$pythonExe`：

```powershell
$skillRoot = Join-Path $env:USERPROFILE '.agents\skills\video-operation-review'
$pythonExe = 'python'
$reviewCli = Join-Path $skillRoot 'scripts\review_video.py'
& $pythonExe -X utf8 $reviewCli doctor
& $pythonExe -X utf8 $reviewCli --help
```

FFmpeg 不在 PATH 时，可在每条需要它的命令上指定 `--ffmpeg '完整路径'`；`scan`、`tracks` 和 `doctor` 的 ffprobe 路径用 `--ffprobe`。也可在同一 shell 中设置：

```powershell
$env:VOR_FFMPEG = 'C:\tools\ffmpeg\bin\ffmpeg.exe'
$env:VOR_FFPROBE = 'C:\tools\ffmpeg\bin\ffprobe.exe'
& $pythonExe -X utf8 $reviewCli doctor
```

这是示例路径，需要替换。环境变量只对继承它们的进程有效；若宿主每次另起 shell，使用显式参数或在同一调用中设置。优先级为命令参数 → `VOR_*` → PATH 中的默认程序。检查输出可能含本机路径，公开分享前先去除个人路径。

## Codex

- 默认用户安装位置为 `~/.agents/skills/video-operation-review/`；项目内可使用 `<项目根>/.agents/skills/video-operation-review/`。完整目录必须包括脚本和参考文档。
- 用 `$video-operation-review` 明确调用，或让 Codex 根据用途选择。`agents/openai.yaml` 提供界面名称和简介；不把它当作 DeepSeek 的运行配置。
- 命令工具与图片工具名称以当前环境为准。例如 `view_image` 成功展示证据后，使用 `record-view --tool view_image`；若工具经过封装，用 `image_tool` 并在 trace 中写清实际工具名和调用引用。
- 图片缩放可能使数字不可读；需要数值证据时打开原图或无插值裁剪。没有独立审阅能力时照常交付部分结果，明确 self_review 与未通过的复核条件。

官方规范：[Build skills](https://learn.chatgpt.com/docs/build-skills)。旧环境可能仍发现 `.codex/skills`；本项目推荐上述共同目录，避免依赖旧路径兼容行为。

## DeepSeek Harness

- 默认可发现 `<项目根>/.agents/skills/` 和 `~/.agents/skills/` 中的 bundle；若配置了 `DSH_AGENTS_HOME` 或 `agentsHome`，以实际目录为准。也可使用 `<项目根>/.dsh/skills/` 或 `<DSH_HOME>/skills/`。
- 本仓库是文件系统 skill，不需要把它作为 npm 插件执行 `dsh plugin add`。宿主需要已挂载 skill 注册表、文件系统提供方和加载工具，即 `dsh-skill`、`dsh-skill-filesystem`、`dsh-tool-skill`。修改宿主组合应另行按其配置流程执行。
- 用户要求“使用 video-operation-review 审阅……”后，模型通过已暴露的 `skill` 工具加载；若用户选择 skill 已注入完整正文，不重复加载。只读取与当前阶段有关的参考文档。
- 使用当前提供的 `pwsh` / `bash` 等命令工具运行 Python；使用 `read_image` 读取 PNG 证据。`read` 的文本输出不能替代图片。
- `read_image` 需要附件服务，并且当前路由的模型必须声明图像输入能力。工具名可见不证明图片调用成功；若路由为纯文本，明确“不兼容本 skill”并停止，不自动切模型或用字幕补猜画面。图片模型的工具故障需单独说明，不把所有文件/权限错误都误报成纯文本模型。
- 成功显示后登记 `--tool read_image`，trace 使用真实调用引用。相同源帧在两个宿主中被重复查看仍只计一个源帧。
- DSH 按 skill 根目录的直接子项扫描，不递归发现任意深度的 `SKILL.md`。避免 `skills/video-operation-review/repo/SKILL.md` 这种多套一层的安装。

官方规范：[文件系统发现](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/skill/skill-filesystem)、[图片与文件工具](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/tool/tool-fs)。版本升级后应重新检查目录发现和视觉路由。

## 有界验收

在独立目录中准备自建短视频，执行 `doctor → scan → plan → extract`。确认未看图前视觉计数为 0；实际展示一张图并登记后应增加一个源帧，重复展示、裁剪或跨宿主查看同源帧不应重复计数。保留真实工具记录。

脚本测试中的 synthetic 查看记录只测试记账，不证明宿主模型看过图。技能发现检查也不等于完整视频语义验收；完整验收继续使用 [layered-acceptance.md](layered-acceptance.md)。
