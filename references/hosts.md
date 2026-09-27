# Codex 与 DeepSeek Harness 适配

两种宿主共用 `SKILL.md`、Python 脚本和审阅数据库。宿主提供本地命令执行、图像输入及图片调用引用。模型与证据呈现策略见 [models.md](models.md)。

## 共同准备

1. 从当前加载的 `SKILL.md` 路径确定技能根，脚本与参考文档都从该根解析。
2. 选择已安装依赖的 Python 解释器，运行 `doctor`，检查 Python、NumPy、Pillow、FFmpeg 和 ffprobe。JSON 的 ready 与退出码 0/1 表示本地处理环境状态。
3. 为本轮素材指定可写的独立 `--work`，确认命令工具和图片工具都能访问证据路径。
4. 用支持图像输入的模型实际打开一张导出的图片，确认内容清晰，再登记观察。

从任意工作目录可运行；技能安装位置不同时修改 `$skillRoot`，使用虚拟环境时修改 `$pythonExe`：

```powershell
$skillRoot = Join-Path $env:USERPROFILE '.agents\skills\video-operation-review'
$pythonExe = 'python'
$reviewCli = Join-Path $skillRoot 'scripts\review_video.py'
& $pythonExe -X utf8 $reviewCli doctor
& $pythonExe -X utf8 $reviewCli --help
```

FFmpeg/ffprobe 支持显式 `--ffmpeg` / `--ffprobe` 路径，也支持当前进程环境变量：

```powershell
$env:VOR_FFMPEG = 'C:\tools\ffmpeg\bin\ffmpeg.exe'
$env:VOR_FFPROBE = 'C:\tools\ffmpeg\bin\ffprobe.exe'
& $pythonExe -X utf8 $reviewCli doctor
```

按实际安装路径替换示例。优先级为命令参数 → `VOR_*` → PATH。宿主每次新建 shell 时，可用命令参数或在同一次调用中设置变量。公开分享诊断结果前整理其中的个人路径。

## Codex

- 用户目录为 `~/.agents/skills/video-operation-review/`；项目目录为 `<项目根>/.agents/skills/video-operation-review/`。安装完整 bundle。
- 使用 `$video-operation-review` 明确调用。`agents/openai.yaml` 的 `interface.default_prompt` 提供调用示例，`policy.allow_implicit_invocation: false` 将调用方式设为用户显式选择。
- `view_image` 成功展示后使用 `record-view --tool view_image`。封装工具可归类为 `image_tool`，trace 写实际工具名称及消息位置。
- 数值证据使用清晰的原图或局部裁剪；自审记为 `self_review`，复核状态在报告中单列。

字段和目录依据 [Codex Agent Skills](https://developers.openai.com/codex/skills)。

## DeepSeek Harness

- 默认发现 `<项目根>/.agents/skills/` 和 `~/.agents/skills/`；自定义 `DSH_AGENTS_HOME` / `agentsHome` 时使用实际配置。DSH 专用目录也可采用 `<项目根>/.dsh/skills/` 或 `<DSH_HOME>/skills/`。
- 按文件系统 skill 加载，宿主配置包含 `dsh-skill`、`dsh-skill-filesystem` 和 `dsh-tool-skill`。技能正文已注入时，直接按当前阶段读取参考文件。
- 使用宿主的 `pwsh` / `bash` 等命令工具运行 Python，使用 `read_image` 与附件服务将图片交给支持图像输入的模型。
- 图片显示后登记 `--tool read_image`，trace 使用实际调用引用。同源帧跨宿主重复查看按一个源帧计数。
- 目录结构为 `skills/video-operation-review/SKILL.md`，SKILL.md 位于 bundle 根。

官方接口：[文件系统发现](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/skill/skill-filesystem)、[图片与文件工具](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/tool/tool-fs)。

## 验收

用自建短视频执行 `doctor → scan → plan → extract`，记录看图前计数；实际展示一张图并登记后检查源帧数增加 1，再检查重复打开、裁剪和跨宿主去重。保留图片工具结果与数据库。完整验收见 [layered-acceptance.md](layered-acceptance.md)。
