# 可执行命令与阶段审阅示例

按顺序准备环境、查看证据、登记观察和导出。路径作为独立参数传递。

从任意工作目录可运行；技能安装位置不同时修改 `$skillRoot`。视频与审阅目录使用本轮实际绝对路径。

```powershell
$skillRoot = Join-Path $env:USERPROFILE '.agents\skills\video-operation-review'
$pythonExe = 'python'
$reviewCli = Join-Path $skillRoot 'scripts\review_video.py'
$VideoInput = 'D:\video-reviews\input\tutorial.mp4'
$ReviewWork = 'D:\video-reviews\tutorial'
& $pythonExe -X utf8 $reviewCli doctor
& $pythonExe -X utf8 $reviewCli --help
& $pythonExe -X utf8 $reviewCli scan $VideoInput --work $ReviewWork
& $pythonExe -X utf8 $reviewCli select --work $ReviewWork
& $pythonExe -X utf8 $reviewCli status --work $ReviewWork
& $pythonExe -X utf8 $reviewCli candidates --pending --work $ReviewWork
```

`doctor` 列出环境状态。FFmpeg/ffprobe 可通过 `--ffmpeg` / `--ffprobe` 指定程序路径，详细设置见 [hosts.md](hosts.md)。后续代码块沿用上面的变量。

## 图片审阅

```powershell
& $pythonExe -X utf8 $reviewCli extract --candidates --work $ReviewWork
& $pythonExe -X utf8 $reviewCli candidates --start 0 --end 30 --pending --work $ReviewWork
```

`candidates` 返回原始时间、选择原因、代表/请求帧号和图片绝对路径。用宿主图片工具打开 `absolute_path`；小字使用原图细节或裁剪。图片展示后，填写实际工具消息引用与观察：

```powershell
& $pythonExe -X utf8 $reviewCli record-view --work $ReviewWork --asset f000000003 `
  --actor main --tool read_image --trace 'read_image#实际消息ID' `
  --observation '填写本图可见菜单、对象、参数及待辨认区域'
```

`--trace` 接收调用/消息位置，例如 `read_image#msg-42`、`session://abc/step-7` 或带锚点的附件路径。把示例替换为本次真实引用。`--tool` 与宿主实际工具对应；查看计数按源帧去重。

## 调整候选与局部补查

```powershell
& $pythonExe -X utf8 $reviewCli select --mode changes --work $ReviewWork --anchor-seconds 3 `
  --global-threshold 1 --local-threshold 0.4 --min-changed-pixels 4 --context-frames 2
& $pythonExe -X utf8 $reviewCli focus --work $ReviewWork --start 12.3 --end 13.1 --stride 1 `
  --reason '核实最终参数与确认状态'
& $pythonExe -X utf8 $reviewCli extract --candidates --work $ReviewWork
& $pythonExe -X utf8 $reviewCli crop --work $ReviewWork --asset f000000003 --box '10,10,150,80'
```

`--stride 1` 包括区间内每个已计算帧，再按精确重复段合并。裁剪坐标取自原图，右/下边界为开区间。`extract --frames '0,1,2,3'` 可显式抽取指定源帧。分层 select 使用默认旧阈值，分段时长通过 `plan --max-span` 调整；逐状态穷尽选择用 `--mode coverage`。

## 暂停与恢复

```powershell
& $pythonExe -X utf8 $reviewCli scan $VideoInput --work $ReviewWork --max-new-frames 500
& $pythonExe -X utf8 $reviewCli status --work $ReviewWork
& $pythonExe -X utf8 $reviewCli scan $VideoInput --work $ReviewWork
& $pythonExe -X utf8 $reviewCli select --work $ReviewWork
```

`--max-new-frames` 是本次新增计算预算。恢复时回放已缓存前缀并复用差分和审阅记录。恰好达到索引末帧时检查实际 EOF、退出码和日志后标记完成。Ctrl+C 或外部终止后先检查 `status` 和 attempts，再继续扫描。

## 汇总与导出

```powershell
& $pythonExe -X utf8 $reviewCli import-records 'D:ideo-reviewsnnotations.json' --work $ReviewWork
& $pythonExe -X utf8 $reviewCli validate --work $ReviewWork
& $pythonExe -X utf8 $reviewCli audit --work $ReviewWork --summary
& $pythonExe -X utf8 $reviewCli validate --work $ReviewWork --require-coverage
& $pythonExe -X utf8 $reviewCli export --work $ReviewWork
```

默认 validate 的退出码按记录完整性 `valid` 返回 0/1；`review_complete` 单列审阅完成度。`--require-coverage` 将候选完成和复核门禁加入退出条件。`--rehash-source` 可用于 validate/export，显式重算源视频 SHA-256。export 写出当前进度及校验结果，适合分阶段交付。

分层记录见 [layered-review.md](layered-review.md)，字幕接口见 [language.md](language.md)，严格模式见 [omission-review.md](omission-review.md)。`audit --queue` 把具体补查帧加入候选，查看数量继续按实际图片登记计算。

调用示例：

> 请使用 `$video-operation-review` 审阅本轮软件录屏，生成可照做的步骤、关键截图和待核对项，分别报告全帧计算、粗审、精审和去重查看源帧。
