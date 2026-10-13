# 可执行命令与阶段审阅示例

本页供代理执行和调试。代理按顺序准备环境、查看证据、登记观察和导出，用户提供视频与问题即可。路径、工具引用和 JSON 记录均由代理填写；路径作为独立参数传递。用户说明与继续回执见 [delivery.md](delivery.md)。

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
& $pythonExe -X utf8 $reviewCli queue --batch-size 8 --work $ReviewWork
```

`doctor` 列出环境状态。FFmpeg/ffprobe 可通过 `--ffmpeg` / `--ffprobe` 指定程序路径，详细设置见 [hosts.md](hosts.md)。后续代码块沿用上面的变量。

## 图片审阅

先读取当前队列。用户问题对应明确时间时使用下面的原始 PTS 范围；数值按实际问题替换，没有明确范围时省略两个边界参数。

```powershell
$NextImages = (& $pythonExe -X utf8 $reviewCli queue --start 12.3 --end 13.1 --batch-size 8 --work $ReviewWork) | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw '队列读取失败；先查看诊断。' }
$BatchFrames = @($NextImages.batch | ForEach-Object { $_.frame_no }) -join ','
if ($BatchFrames) {
  & $pythonExe -X utf8 $reviewCli extract --frames $BatchFrames --work $ReviewWork
  & $pythonExe -X utf8 $reviewCli queue --start 12.3 --end 13.1 --batch-size 8 --work $ReviewWork
}
```

第二次 queue 取得抽图后的 `absolute_path`。范围内候选优先，其余待审仍保留；范围按代表图所代表的原请求帧时间匹配。`batch_size` 是响应数量，不能当作本轮总帧预算。用宿主图片工具打开返回的原图；小字另用细节或裁剪。图片展示后，填写实际工具消息引用与观察：

```powershell
& $pythonExe -X utf8 $reviewCli record-view --work $ReviewWork --asset f000000003 `
  --actor main --tool read_image --trace 'read_image#实际消息ID' `
  --observation '填写本图可见菜单、对象、参数及待辨认区域'
```

`--trace` 接收调用/消息位置，例如 `read_image#msg-42`、`session://abc/step-7` 或带锚点的附件路径。把示例替换为本次真实引用。`--tool` 与宿主实际工具对应；查看计数按源帧去重。

实际登记后，重调相同的 queue 获取下一批，不设 offset。若没有新查看记录，同一批仍会返回。`candidates --pending` 继续提供完整清单；`candidates --start/--end` 只按代表帧时间过滤，不用于替代 queue 的原请求范围匹配。

## 将补交录像关联到原疑点

先在另一个审阅目录完成补交录像的索引、实际原图查看与 export；可以是阶段导出，但须完整五文件清单且来源、证据有效。下面假设选中的原图为 `f000000003`，由代理替换为真实目录与 ID。

```powershell
$SupplementWork = 'D:\video-reviews\followup'
& $pythonExe -X utf8 $reviewCli supplement-import --work $ReviewWork --source-review $SupplementWork `
  --id SUP1 --assets 'f000000003' --actor main --note '用户补交的重新启动后画面'
& $pythonExe -X utf8 $reviewCli supplements --work $ReviewWork
```

从返回的 `assets[].relative_path` 解析当前审阅目录内的图片路径。主张作者通过宿主图片工具实际打开该图后才运行：

```powershell
& $pythonExe -X utf8 $reviewCli supplement-view --work $ReviewWork --id SUP1 --asset f000000003 `
  --actor main --tool read_image --trace 'read_image#实际补证消息ID' `
  --observation '填写后交图实际可见的状态，以及仍看不见的过程'
& $pythonExe -X utf8 $reviewCli export --work $ReviewWork
```

以下将 followup 加到当前导出的 Q01，保留它原有的问题、状态、范围与补查。Q01、主张和原片限制均须替换为本轮真实内容。若新材料仅显示结果，就只写这个结果，不能补写未出现的点击或重新启动动作。

```powershell
$CurrentReview = Get-Content -LiteralPath (Join-Path $ReviewWork 'review.json') -Raw | ConvertFrom-Json
$Matches = @($CurrentReview.issues | Where-Object { $_.payload.id -eq 'Q01' })
if ($Matches.Count -ne 1) { throw '必须先定位唯一的原疑点。' }
$IssueUpdate = $Matches[0].payload
$Followup = @{
  claim = '后交录像显示重新启动后的界面为所需语言'
  original_record_limit = '原录像没有展示重新启动及当时设置的生效过程'
  reviewer = 'main'
  supplement_refs = @(@{ supplement_id = 'SUP1'; asset_id = 'f000000003' })
}
$IssueUpdate | Add-Member -NotePropertyName followup -NotePropertyValue $Followup -Force
$FollowupInput = Join-Path $ReviewWork 'followup-records.json'
@{ issues = @($IssueUpdate) } | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $FollowupInput -Encoding utf8
& $pythonExe -X utf8 $reviewCli import-records $FollowupInput --work $ReviewWork
& $pythonExe -X utf8 $reviewCli validate --work $ReviewWork
& $pythonExe -X utf8 $reviewCli export --work $ReviewWork
```

`followup` 的 reviewer 必须与本地补证查看者一致；来源自己的查看记录不替代它。补证快照不自动随源目录更新，不增加原片覆盖，也不自动结案。契约和迁移要求见 [records.md](records.md)。

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

以下新增帧预算演示已有接口，不是每轮默认限制。用户指定预算时才按其要求安排；恢复前先读取已有状态，确认没有活动写入者，不新建另一份相同视频的审阅库。

```powershell
& $pythonExe -X utf8 $reviewCli scan $VideoInput --work $ReviewWork --max-new-frames 500
& $pythonExe -X utf8 $reviewCli status --work $ReviewWork
& $pythonExe -X utf8 $reviewCli scan $VideoInput --work $ReviewWork
& $pythonExe -X utf8 $reviewCli select --work $ReviewWork
```

`--max-new-frames` 是本次新增计算预算。恢复时回放已缓存前缀并复用差分和审阅记录。恰好达到索引末帧时检查实际 EOF、退出码和日志后标记完成。Ctrl+C 或外部终止后先检查 `status` 和 attempts，再继续扫描。

阶段结束或暂停后，代理根据这些状态说明已完成内容和下一步，给出实际审阅目录及继续回执。长命令未返回时说明当前阶段；这些命令提供状态快照，不提供实时百分比。全帧计算已完成时直接继续剩余审阅。

## 保存本轮问题与继续信息

下面示例保存不使用语言文本的交付上下文。把问题、范围和下一步替换为本轮实际内容；若采用已导入字幕或转写，将 `used_language_source_ids` 替换为实际使用的来源 ID，不能根据文件名编造。`tracks` 仅检查并记录轨道，不启动 ASR。

```powershell
& $pythonExe -X utf8 $reviewCli tracks --work $ReviewWork
$DeliveryInput = Join-Path $ReviewWork 'delivery-context.json'
@{
  delivery_context = @{
    question = '确认参数是否应用，以及运行是否产生结果'
    scope = '本轮源视频中参数设置与运行结果部分'
    next_action = '补查确认后的主界面，保留尚未展示的输出结果疑点'
    used_language_source_ids = @()
  }
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $DeliveryInput -Encoding utf8
& $pythonExe -X utf8 $reviewCli import-records $DeliveryInput --work $ReviewWork
& $pythonExe -X utf8 $reviewCli export --work $ReviewWork
```

导出后把 `handoff.md` 交给继续任务的代理，并保留同代报告及附件。更新下一步时提交完整 `delivery_context`；只修改 `next_action` 不会使已有照做验收过期。其余内容变化的规则见 [records.md](records.md)。

如果原来已有手写或手改的 `handoff.md`，导出会先拒绝。先将原笔记另名保留，再把需要延续的内容写入 `delivery_context`；不要直接删除原笔记或改清单哈希来绕过检查。

## 记录疑点的结案依据

新结案需要完整疑点记录，已有帧范围、步骤关联和 attempts 均应保留。下面仅展示一个独立字段示例；`f000000006` 必须替换成本库已实际查看、确实支持结论的证据，不能直接拿示例作为新观察。

```json
{
  "issues": [{
    "id": "Q02",
    "question": "最终输入后是否确认执行？",
    "status": "resolved",
    "attempts": [{"action": "核对确认后的参数栏", "evidence": ["f000000006"], "new_information": "确认后参数栏显示目标值", "conclusion": "本问题在该阶段有画面依据"}],
    "resolution": {
      "mode": "evidence",
      "reviewer": "本次实际复核者",
      "reason": "确认后的参数栏支持该阶段已应用，不推断后续运行结果。",
      "evidence": ["f000000006"]
    }
  }]
}
```

如果疑点本身误设，可将 resolution 改为 `{"mode":"withdrawn","reviewer":"本次实际复核者","reason":"问题误把片头既有值当作新增输入。","basis":"原 Q02 问题及 S02.input_action：仅核对现有值，没有本次输入。"}`，并据实修改理由与原记录位置。撤销误设不是对未展示过程的确认，不接受空理由；新导入不能沿用旧字符串结案说明。

## 追加已经完成的照做验收

仅在实际照做已获授权且已经产生可核对结果后使用。以下脚本不执行录屏命令、不生成成功结果；示例假设真实日志已保存为工作目录内 `replay/run-log.txt`。执行者、范围、环境、结论、步骤 ID 和 outcome 必须按本次观察填写，部分完成用 `partial`、失败用 `failed`，不能照抄为 passed。

日志必须是新照做的实际证据；不能引用 report、handoff、其他导出文件、清单、数据库及 WAL/SHM、`.export-*` 内容、源视频或已登记的原图/裁剪充当产物。这些路径会被拒绝，匹配哈希也不能代替语义核对。

```powershell
$DeliveryState = & $pythonExe -X utf8 $reviewCli status --work $ReviewWork | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw '读取审阅状态失败' }
$ReplayArtifact = 'replay/run-log.txt'
$ReplayHash = (Get-FileHash -LiteralPath (Join-Path $ReviewWork $ReplayArtifact) -Algorithm SHA256).Hash.ToLowerInvariant()
$ReplayInput = Join-Path $ReviewWork 'reproduction-check.json'
@{
  reproduction_checks = @(@{
    id = 'R01'
    reviewer = '本次实际执行者'
    scope = 'S02 参数设置后的结果核对'
    environment = '填写实际软件、版本与运行环境'
    result = '填写实际观察和日志结论；没有验证的部分明确列出'
    step_ids = @('S02')
    outcome = 'partial'
    content_snapshot = $DeliveryState.delivery_snapshot
    artifacts = @(@{ path = $ReplayArtifact; sha256 = $ReplayHash })
  })
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ReplayInput -Encoding utf8
& $pythonExe -X utf8 $reviewCli import-records $ReplayInput --work $ReviewWork
& $pythonExe -X utf8 $reviewCli export --work $ReviewWork
```

这里取得的 snapshot 必须仍对应刚才实际照做的交付；步骤或问题中途改变时重验，不能换一个 snapshot 保留旧通过。R01 已存在时使用新的 ID，不覆盖历史。交付内容变化后报告显示 `stale`，日志缺失或改变显示 `evidence_changed`；再次导出不会把这些旧结果自动升级为当前有效。记录照做结果不改变 `review_complete`。

## 汇总与导出

```powershell
& $pythonExe -X utf8 $reviewCli import-records 'D:\video-reviews\annotations.json' --work $ReviewWork
& $pythonExe -X utf8 $reviewCli validate --work $ReviewWork
& $pythonExe -X utf8 $reviewCli audit --work $ReviewWork --summary
& $pythonExe -X utf8 $reviewCli validate --work $ReviewWork --require-coverage
& $pythonExe -X utf8 $reviewCli export --work $ReviewWork
```

默认 validate 的退出码按记录完整性 `valid` 返回 0/1；`review_complete` 单列审阅完成度。`--require-coverage` 将候选完成和复核门禁加入退出条件。`--rehash-source` 可用于 validate/export，显式重算源视频 SHA-256。export 写出当前进度及校验结果，适合分阶段交付。

RC.6 一次导出 `review.json`、`omission-audit.json`、`frames.jsonl`、`report.md` 和 `handoff.md` 五份文件，并生成同代清单。先确认无 `export.pending.json`，再按清单核对五份文件；完整规则见 [records.md](records.md)。RC.5 及更早版本不支持新交付与补证元数据，不能用于这些工作库的维护或重导出。

分层记录见 [layered-review.md](layered-review.md)，字幕接口见 [language.md](language.md)，严格模式见 [omission-review.md](omission-review.md)。`audit --queue` 把具体补查帧加入候选，查看数量继续按实际图片登记计算。

调用示例：

> 请使用 `$video-operation-review` 审阅本轮软件录屏，给出可照做的步骤、各对象的最终参数、关键截图和仍需确认的地方。

完整交付样式见 [软件教程示例](../examples/tutorial/report.md)。用户交付先给操作说明，覆盖统计和底层记录置于其后。

## 在同一账本纠正误设步骤

例如 S01 只描述片头已存在的条件，实际操作是 S02。先核对现有 `steps`、`intervals`、`coverage`、`issues`，将片头条件保存在 S02 前提中；将受影响记录的完整更新内容与下面的退休请求写入同一个 JSON，再运行上面的 `import-records`。这只是退休字段的例子，不能省略实际存在的关联更新。

```json
{
  "retire_steps": [{
    "id": "S01",
    "reason": "片头字段已经存在，没有输入动作；条件保留在 S02 操作前提中。",
    "reviewer": "本次实际纠错者",
    "replacement_step_ids": ["S02"]
  }]
}
```

如果 I01 原来绑定 S01，则在同批 `intervals` 提交完整 I01，明确其新的 `step_ids`；有 Q01 等疑点或严格模式 coverage 引用时也须一并处理。没有替代操作的误设记录可使用空 `replacement_step_ids`，但不得丢失未解决内容或相关展开历史。随后重新运行 audit；旧抽查或复核显示 stale 时，根据当前内容重新核对和登记，再验证并导出。保留原库，不重新扫描、不重复登记已经看过的图，也不修改旧查看调用引用。完整保护与跨版本边界见 [记录契约](records.md)。
