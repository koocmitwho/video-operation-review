# 可执行命令与阶段审阅示例

以下 PowerShell 示例将脚本路径改为技能所在位置，将视频和工作目录改为本轮实际输入。脚本也可在其他平台用同样参数调用。路径始终作为独立参数传递，不拼接 shell 命令。

```powershell
$ReviewScript = (Resolve-Path './scripts/review_video.py').Path
$VideoInput = './input/tutorial.mp4'
$ReviewWork = './work/tutorial'
python -X utf8 $ReviewScript --help
python -X utf8 -c "import numpy, PIL; print(numpy.__version__, PIL.__version__)"
ffmpeg -version
ffprobe -version

python -X utf8 $ReviewScript scan $VideoInput --work $ReviewWork
python -X utf8 $ReviewScript select --work $ReviewWork
python -X utf8 $ReviewScript status --work $ReviewWork
python -X utf8 $ReviewScript candidates --pending --work $ReviewWork
```

环境检查缺项时先报告；没有必要不要安装或升级。FFmpeg/ffprobe 可通过 `scan --ffmpeg/--ffprobe` 指定可执行文件绝对路径，`extract` 支持同样的 `--ffmpeg`。

## 图片审阅

```powershell
python -X utf8 $ReviewScript extract --candidates --work $ReviewWork
python -X utf8 $ReviewScript candidates --start 0 --end 30 --pending --work $ReviewWork
```

`candidates` 输出原始时间、选取原因、代表/请求帧号、图片绝对路径。原始起点非零时用实际时间筛选。此时视觉查看计数仍为零。用图片工具逐个或按自然阶段批量打开实际图片；比如 `view_image` 打开 `absolute_path`。小字模糊时看 original 细节或裁剪。工具确实返回可见图片之后，登记：

```powershell
python -X utf8 $ReviewScript record-view --work $ReviewWork --asset f000000003 `
  --actor main --tool view_image --trace '实际图片工具调用或消息引用' `
  --observation '写实际看到的菜单、对象、参数和不清楚的区域'
```

上述 trace/observation 是需要替换的示例，不得直接作为实际查看证据使用。脚本无法验证字符串是否真实。

## 调整候选和具体疑点

```powershell
# 默认 layered 的完整流程见 layered-review.md。以下是保留的门限初筛，不替代分层粗审。
python -X utf8 $ReviewScript select --mode changes --work $ReviewWork --anchor-seconds 3 `
  --global-threshold 1 --local-threshold 0.4 --min-changed-pixels 4 --context-frames 2

# 仅补查具体原始时间区间，stride=1 包括该区间每个已计算帧，再精确合并重复段。
python -X utf8 $ReviewScript focus --work $ReviewWork --start 12.3 --end 13.1 `
  --reason '核实最终参数是 0.02 还是临时输入，并确认是否点击确定'
python -X utf8 $ReviewScript extract --candidates --work $ReviewWork
python -X utf8 $ReviewScript crop --work $ReviewWork --asset f000000003 --box '10,10,150,80'
```

裁剪坐标必须符合实际图像尺寸，右/下边界不含在内。裁剪保留原始源帧身份，不增加去重帧数。若需要真正逐帧查看相同画面段，可用 `extract --frames '0,1,2,3'` 明确抽取并逐张打开；默认代表合并不能支持“全部逐帧看过”的声明。

## 暂停与恢复

```powershell
# 仅在用户给定或你明确解释的计算预算下使用，不是固定完成标准。
python -X utf8 $ReviewScript scan $VideoInput --work $ReviewWork --max-new-frames 500
python -X utf8 $ReviewScript status --work $ReviewWork
# 相同源文件/计算参数下继续；会回放解码前缀，已存差分/审阅记录复用。
python -X utf8 $ReviewScript scan $VideoInput --work $ReviewWork
python -X utf8 $ReviewScript select --work $ReviewWork
```

最后一帧恰好达到预算时仍保守为 paused，须重跑至干净 EOF 才确认完整。Ctrl+C、解码错误或被强制终止后，先读 `status` 与日志，不能把“有部分 PNG”解释为完成。

## 汇总与后续改写

```powershell
python -X utf8 $ReviewScript import-records './annotations.json' --work $ReviewWork
python -X utf8 $ReviewScript validate --work $ReviewWork
python -X utf8 $ReviewScript audit --work $ReviewWork --summary
# 按 layered-review.md 完成区间说明、精审、抽查及实际有界复核后：
python -X utf8 $ReviewScript validate --work $ReviewWork --require-coverage
python -X utf8 $ReviewScript export --work $ReviewWork
```

`validate` 有错误时退出码为 1，并列出具体引用；未完成范围作为警告保留。`export` 允许导出未完成报告，但 JSON 内含校验结果；不能把导出成功当作审阅全部通过。后续写说明书时读取 `review.json`、步骤证据和疑点即可；只有出现新缺口再补查视频。

默认区间、操作角色、抽查与复核 JSON 见 [layered-review.md](layered-review.md)；字幕接口见 [language.md](language.md)。严格逐状态说明仅用于显式 coverage/strict，格式见 [omission-review.md](omission-review.md)。`audit --queue` 将缺口和异常局部窗口加入候选，不增加视觉计数；导出含 `omission-audit.json`。

调用技能的例子：

> 请使用 `SKILL.md` 中的 `$video-operation-review`，分析我本轮附上的软件操作录屏，生成可照做的步骤、关键截图和待核对项；分别报告全帧计算、候选审阅及实际视觉查看的覆盖情况。
