# 分层记录与有界复核

本流程使用原始 0 起始帧号和闭区间；时间始终由索引 PTS 解析。`segments` 是程序建议，`intervals` 是宿主看图后形成的人工判断。两者分开，运行计划不会覆盖已审阅记录。

## 命令次序

```powershell
$ReviewScript = (Resolve-Path './scripts/review_video.py').Path
$ReviewWork = './work/tutorial'
python -X utf8 $ReviewScript plan --work $ReviewWork
python -X utf8 $ReviewScript candidates --work $ReviewWork
python -X utf8 $ReviewScript extract --candidates --work $ReviewWork
python -X utf8 $ReviewScript intervals --work $ReviewWork
```

`plan` 默认上下文上界 15 秒，是粗审分组时长而非跳帧间隔或完成上限。界面大变化/稳定段可提前分组；一帧菜单不会因为持续短就删除。弱局部变化和短暂状态仍保存在风险线索及逐帧数据库内。局部连续变化可以合成一个操作单元，但窗口/面板/对象/动作的语义仍由宿主看图判定。长等待中的鼠标/闪烁可能留在同一区间；没有算法证明它们全无关。

`layer-plan.json` 保存建议区间及 `[区间内首帧, 区间内末帧, 原 exact_start]` 映射。`intervals` 返回人工区间的完整状态映射、原始时间与风险抽查需求。原始帧表从不因合并删除。首尾落在精确重复段中时，可以引用该段真正看过的代表；不同 RGB 状态不共享证据身份。

实际查看代表画面后，用以下格式导入 `import-records`。这是格式示例，帧号、来源和观察均需换成当前视频的事实，不能直接用作查看证明。

```json
{
  "intervals": [{
    "id": "I01", "start_frame": 0, "end_frame": 15,
    "phase": "等待参数窗口", "disposition": "context",
    "reason": "首尾窗口与对象一致；中间有鼠标/光标变化，按风险样本复核，未逐帧精审",
    "reviewer": "main", "merge": "approximate", "fine_status": "not_reviewed",
    "evidence": ["f000000000", "f000000015"], "step_ids": [], "issue_ids": []
  }]
}
```

所有源帧必须最终落在一段人工区间内，不能重叠；等待也有去向。`operation` 需要 step_ids；`uncertain` 需要 issue_ids 且保留未完成。`merge` 为 none/exact/approximate：不同状态合并必须明确 approximate（单个操作内部跨状态可为 none，因已有操作结构解释）。`fine_status` 为 not_reviewed/partial/reviewed。context 的全区间永远不因抽几个样本就算全区间精审。

拆分/合并时同次导入 `retire_intervals: ["旧ID"]` 和新 `intervals`，旧记录写入 history；旧异常抽查不会因退役被消除。不要编辑数据库抹掉未完成项。

## 原图、裁剪与拼图

拼图可降低工具调用/概览上下文开销，但不是每个面板原图大小的精审：

```powershell
python -X utf8 $ReviewScript sheet --work $ReviewWork --frames '0,15,16,18' --thumb-width 480 --columns 2
# 图片工具实际打开 sheet 返回的 absolute_path 后，写 observations.json：asset_id 到逐面板观察的对象。
python -X utf8 $ReviewScript record-sheet-view --work $ReviewWork --sheet '实际 sheet ID' --actor main `
  --trace '实际工具调用位置' --observations './observations.json'
```

只能登记工具实际显示且能够定位的面板。生成拼图不会登记查看；拼图登记是 overview，不能通过原图数值/抽查检查。重复打开、裁剪、拼图面板按源帧去重；native 表示原始证据图/裁剪已被工具展示，仍需实际使用 original 细节或合适裁剪确认可读性，不由脚本证明工具没有缩放。若文字不清楚，保留未知。

## 操作精审

基本步骤字段见 [records.md](records.md)，前后状态结构见 [omission-review.md](omission-review.md) 中的 transition 示例；分层模式不需要逐状态 coverage。为每个操作另加：

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

这些图必须位于该步骤帧范围内、顺序正确、均列入步骤顶层 evidence，且该作者实际查看了原图或裁剪。before/during/after 可以在素材只给静态状态时引用同帧，但必须说明证据限制，不能据此补出点击过程。确认/结果仍要在 transition 内 observed 或有理由的 not_applicable；未展示则 partial 加 issue。

`final_parameters` 只写确认后的值；临时 0.20、取消、重输 0.02 应按可见过程区分。对话框消失本身不能证明 Apply；可见控件不存在可用 `{"visible": false}`，业务值未知才用 null。

文件交接使用同一个稳定逻辑键，例如两个步骤的 `transition.after["file:exchange"]` 和 `transition.before["file:exchange"]`，value 写可见名称/路径/版本等事实。换文件名或对象但无解释的跳变会报缺口。相同文件名不证明内容相同；不要把预期输出当作实际输出。

## 抽查和自适应展开

先导入区间/步骤，再运行 `intervals` 取得 `sample_requirements`。approximate 或 context 区间要求抽查：最强局部变化、最弱非零局部变化、按内容哈希种子选的状态。相同帧去重；策略覆盖有限，不保证发现每次极小编辑。每个样本必须查看该状态的原图，不能仅凭 OCR 或拼图。

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

`clear` 是本次有界抽查未发现异常，不是对所有帧无遗漏的证明。异常用 expand；信息不足用 incomplete。抽查 ID 不可原地覆盖；内容变更保留旧记录并导入新 ID。`audit --queue` 会把 expand 对应局部窗口内不同状态及邻接上下文入队。补充/修正操作后，用当前 scope_hash、method=exhaustive、全部该窗口状态的原图证据作新检查，`resolves` 指向原异常检查 ID。审计也要求被解决旧异常的原范围完整被新证据覆盖，不能把区间缩小来消警。

## 当前内容的遗漏复核

主稿和抽查就绪后，运行 `audit` 获取 snapshot。独立审阅者看完整区间序列的首尾代表、关键操作角色证据和抽查样本，再导入：

```json
{
  "layer_reviews": [{
    "id": "R01", "reviewer": "reviewer", "independence": "independent",
    "snapshot": "当前 audit snapshot", "checked_interval_ids": ["I01"],
    "evidence": ["复核者实际看过的证据ID"],
    "tool_trace_refs": ["与复核者查看登记一致的实际调用位置"],
    "issue_ids": [], "conclusion": "no_additional_omissions_found",
    "note": "说明检查范围、抽样边界和新发现，不能只写通过"
  }]
}
```

自审保留 self_review；门禁不会把自审当独立检查。步骤、区间、抽查或语言来源变更使 snapshot 失效。只追加查看记录不改变内容快照。`validate` 是记录一致性检查；`validate --require-coverage` 检查当前模式门禁；`export` 始终允许交付部分报告并保留缺口。

统计区分 **已进行精审** `fine_examined_*` 与 **已完成精审** `fine_reviewed_*`：实际看过操作前/中/后的原图但仍缺菜单入口时，前者可计入，后者保持未完成。两者均是操作区间的覆盖长度，不是逐帧看图数。context 抽查不使整段等待变成已精审；真实查看数仍只取独立源帧去重登记并核对工具结果。

## 严格模式

显式 `select --mode coverage` 保留每个连续不同 RGB 状态；`audit --mode strict` / `validate --mode strict --require-coverage` 按旧覆盖和独立复核规则检查。用于疑难片段/独立严格工作目录、穷尽验收或回归基线，不作为普通分层任务的隐性要求。分层里的异常展开使用同一精确状态索引，无需重算原视频。
