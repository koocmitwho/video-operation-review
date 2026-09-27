# 分层记录与复核

源帧从 0 起始，区间采用闭区间，时间由原始 PTS 解析。segments 保存程序建议，intervals 保存实际看图后的人工判断。

## 命令次序

从任意工作目录可运行；技能安装位置不同时修改 `$skillRoot`。视频与审阅目录使用本轮实际绝对路径。

```powershell
$skillRoot = Join-Path $env:USERPROFILE '.agents\skills\video-operation-review'
$pythonExe = 'python'
$reviewCli = Join-Path $skillRoot 'scripts\review_video.py'
$VideoInput = 'D:\video-reviews\input\tutorial.mp4'
$ReviewWork = 'D:\video-reviews\tutorial'
& $pythonExe -X utf8 $reviewCli plan --work $ReviewWork --max-span 15
& $pythonExe -X utf8 $reviewCli candidates --work $ReviewWork
& $pythonExe -X utf8 $reviewCli extract --candidates --work $ReviewWork
& $pythonExe -X utf8 $reviewCli intervals --work $ReviewWork
```

`--max-span` 默认 15 秒，控制粗审分组上下文时长；界面变化和稳定段可提前分组。短暂状态与局部变化保存在原始索引和风险线索中。宿主实际看图后，按窗口、面板、对象与动作形成操作区间。

layer-plan.json 保存建议和 `[区间内首帧, 区间内末帧, 原 exact_start]` 映射；intervals 返回人工区间、原始时间和 sample_requirements。精确重复段可引用实际查看的代表图。以下 JSON 沿用字段格式，填写本轮帧号、观察和证据：

```json
{
  "intervals": [{
    "id": "I01", "start_frame": 0, "end_frame": 15,
    "phase": "等待参数窗口", "disposition": "context",
    "reason": "首尾窗口与对象一致；中间有鼠标/光标变化，按风险样本复核，精审状态见 fine_status",
    "reviewer": "main", "merge": "approximate", "fine_status": "not_reviewed",
    "evidence": ["f000000000", "f000000015"], "step_ids": [], "issue_ids": []
  }]
}
```

人工区间应完整、互斥地覆盖已计算时间线。operation 关联 step_ids，uncertain 关联 issue_ids；merge 取 none/exact/approximate，fine_status 取 not_reviewed/partial/reviewed。不同背景状态的组合使用 approximate，单个操作内跨状态可使用 none。

拆分/合并时同时导入 retire_intervals 和新 intervals。history 保留旧版本，既有异常继续关联原范围和后续复查。

## 原图、裁剪与拼图

拼图用于多画面概览。以下代码沿用上面的路径变量：

```powershell
& $pythonExe -X utf8 $reviewCli sheet --work $ReviewWork --frames '0,15,16,18' --thumb-width 480 --columns 2
# 图片工具实际打开 sheet 返回的 absolute_path 后，写 observations.json：asset_id 到逐面板观察的对象。
& $pythonExe -X utf8 $reviewCli record-sheet-view --work $ReviewWork --sheet '实际 sheet ID' --actor main `
  --trace '实际工具调用位置' --observations './observations.json'
```

按实际显示且可定位的面板填写 observations。拼图登记为 overview；原图或裁剪登记为 native。源帧全局去重，粒度分别记录。最终数值使用可读的原图或局部裁剪。

## 操作精审

基本步骤字段见 [records.md](records.md)，transition 结构见 [omission-review.md](omission-review.md)。为每个操作补充作者与角色证据：

```json
{
  "author": "main",
  "role_evidence": {
    "before": ["f000000019"],
    "during": ["f000000020"],
    "after": ["f000000021"]
  }
}
```

角色图位于步骤范围内，按 before/during/after 顺序排列，列入顶层 evidence，并有该作者的 native 登记。静态状态可共用一帧，note 说明可见过程。transition 的确认/结果取 observed 或有理由的 not_applicable；待核对步骤使用 partial 和 issue。

独立复核查看该资产、覆盖目标区域的裁剪或完整原图。嵌套裁剪换算到源图区域；精确重复等价采用同一连续段。

final_parameters 填写确认后的值，临时输入、取消、重输分开描述。控件消失可用 `{"visible": false}` 表示，待辨认的业务值用 null。文件交接采用同一 `file:exchange` 状态键，value 记录可见名称、路径和版本等事实。

## 抽查与展开

导入区间/步骤后，运行 intervals 获取 sample_requirements。approximate/context 区间抽查最强局部变化、最弱非零变化和内容哈希种子样本，逐项查看原图。

```json
{
  "interval_checks": [{
    "id": "C01", "interval_id": "I01", "reviewer": "main",
    "scope_hash": "从当前 intervals 输出复制的 scope_hash",
    "method": "risk_and_random", "evidence": ["实际已查看样本ID"],
    "reason": "说明复核了哪些变化及仍看不清的部分",
    "conclusion": "clear", "resolves": []
  }]
}
```

clear 表示本次样本检查完成，expand 表示需要展开，incomplete 表示继续补查。每次检查使用新 ID 保留历史。audit --queue 将异常区间的不同状态和邻接帧加入候选；完成复查后，以当前 scope_hash、method=exhaustive 和原范围的全部状态证据登记新检查，resolves 关联原异常 ID。

## 当前内容的遗漏复核

主稿与抽查就绪后取得 audit.snapshot。复核者查看区间首尾、关键角色证据和抽查样本，再导入：

```json
{
  "layer_reviews": [{
    "id": "R01", "reviewer": "reviewer", "independence": "independent",
    "snapshot": "当前 audit snapshot", "checked_interval_ids": ["I01"],
    "evidence": ["复核者实际看过的证据ID"],
    "tool_trace_refs": ["与复核者查看登记一致的实际调用位置"],
    "issue_ids": [], "conclusion": "no_additional_omissions_found",
    "note": "填写检查范围、样本与具体发现"
  }]
}
```

自审使用 self_review。步骤、区间、抽查和语言来源变化后重新取得 snapshot 并复核；追加查看事件保留内容快照。validate 输出记录完整性 valid 与审阅完成度 review_complete；--require-coverage 将审阅完成条件加入退出状态。export 输出当前进度。

fine_examined_* 表示已形成精审角色证据的操作区间，fine_reviewed_* 表示已完成精审的区间；二者均按区间长度统计。实际图片查看另按源帧去重，context 抽查保留自己的样本与粗审口径。

## 严格模式

`select --mode coverage` 保留所有连续不同 RGB 状态；`audit --mode strict` 和 `validate --mode strict --require-coverage` 执行逐状态规则，适用于疑难片段、穷尽验收和回归。分层局部展开复用同一精确状态索引。
