# 操作遗漏检查

> 本文是显式 strict/coverage 模式的旧逐状态契约；新默认分层流程请读 [layered-review.md](layered-review.md)。仅 transition 状态建模示例也适用于分层操作步骤，逐状态 coverage 与 checked_state_frames 不属于分层默认要求。

在逐步演示中检查是否漏写操作、状态衔接不明，或准备声称操作还原已经完成时读本文。复用现有索引和图像，不调用额外模型 API。

## 检查对象与边界

先 `select --mode coverage`，再按自然操作阶段查看。每一段完全相同的连续 RGB 画面是一个“状态”，以该段首帧 `frame_no` 标识；两个相隔一段变化、外观相同的画面仍是两个状态。鼠标移动、闪烁和压缩噪声也会产生状态；程序只负责列出，审阅者负责判断是否影响复现。

`audit` 遍历所有已计算状态，而非只遍历候选或主稿。它检查：

- 状态是否得到说明，说明者是否有本状态原图查看登记；只看裁剪不够。
- 标为操作的状态是否绑定存在且时间相交的步骤；步骤是否至少绑定一个操作状态。
- 每步是否记录前后状态、确认、结果及作者；是否有同名对象/参数/文件状态突然变化。
- 是否仍有不确定步骤、未解决疑点、失效引用或未完成计算。
- 独立遗漏复核是否覆盖全部不同状态、由不同署名者登记、附有其自身原图查看记录，并针对当前内容快照。

这些只能发现**记录层的遗漏风险**。错误地把一个操作说成无关、把一个参数读错、不同对象使用了不同键名而无法比较、没有视觉变化的动作、录屏未展示的步骤，仍需视觉/语义判断。`semantic_completeness_proven` 永远为 false。

## 逐状态覆盖记录

`audit` 的 `coverage.states` 给出全部代表帧、原始时间和段结束帧。查看后，通过 `import-records` 导入：

```json
{
  "coverage": [{
    "frame_no": 3,
    "classification": "operation",
    "step_ids": ["S02"],
    "issue_ids": [],
    "reason": "Rate 输入框从 1 改成 5，是 S02 的参数输入状态。",
    "evidence": ["f000000003"],
    "reviewer": "main"
  }]
}
```

- `operation`：说明具体变化，绑定对应步骤；不要用“整段视频操作”笼统覆盖所有状态。
- `context`：有原图依据的非操作/背景状态，例如操作前初始界面、已核实的仅光标闪烁。写明为何不改变操作含义，不能因没时间看就标 context。
- `uncertain`：无法判定，绑定实际 issue。即使 issue 后来改为 resolved，该状态也要重新判断并更新。

`reviewer` 必须与实际 `record-view --actor` 对应。相同精确重复段中的其他全图可以提供该状态的证据，但不能因此增加没有实际打开的源帧计数。每个代表帧一条记录，可在一个 JSON 文件中批量导入；重复导入同一 frame_no 更新当前判断并保留历史。

## 步骤前后状态

在基础步骤记录中添加以下字段，并将所有嵌套 evidence 同时列入该步骤顶层 evidence：

```json
{
  "author": "main",
  "transition": {
    "before": {
      "SampleA.rate": {"value": "1", "evidence": ["f000000002"]},
      "input_file": {"value": "input.csv", "evidence": ["f000000002"]}
    },
    "after": {
      "SampleA.rate": {"value": "5", "evidence": ["f000000006"]},
      "input_file": {"value": "input.csv", "evidence": ["f000000006"]}
    },
    "confirmation": {
      "status": "observed",
      "evidence": ["f000000006"],
      "note": "状态栏可见 Applied rate = 5；鼠标按下瞬间未显示，不额外声称已看见点击。"
    },
    "result": {
      "status": "observed",
      "evidence": ["f000000006"],
      "note": "主界面 Current rate 显示 5。"
    }
  }
}
```

上述示例只说明格式，必须替换成当前视频的事实。选择一个稳定、带对象作用域的键，比如 `SampleA.rate`；跨步骤用同一键名和同一数据表示，不把 `"5"`、`5`、`"5 mm"` 当作自动可换算值。读不清用 `null` 并记录疑点。程序比较显式同名键，不从自然语言猜参数对应关系。必要的对象、输入文件、输出文件和模块状态也可作为键。

只记录对复现有意义的可见状态，不猜软件内部变量。**控件已经消失和参数值未知是两回事**：例如对话框关闭后，`dialog.rate_field` 可记录为 `{"value":{"visible":false},"evidence":["实际关闭画面 ID"]}`；打开时则记录 `{"value":{"visible":true,"text":"20"},"evidence":["实际输入框画面 ID"]}`。这个对象值表示看到的控件状态，不断言软件内部仍保存或已经清除了什么。真正需要知道却无法辨认的业务参数仍用 null；不能用 visible:false 掩盖它。前后保持同一表示方式。

按时间顺序写可执行的细步骤，以 `phase` 组织阶段，不再加入与所有子步骤时间重叠的总括步骤。前一步 `after` 和后一步 `before` 出现同名不同值，会形成补查任务；程序跨越未提及该键的中间步骤保留上次已登记值。

`confirmation` 和 `result`：

- `observed`：提供实际可见的确认/结果证据和具体说明。确认可由明确的应用状态支持，但不能把未见的点击说成直接看见。
- `not_applicable`：本步骤确实不涉及确认或结果，必须写理由；不是消除警告的通用开关。
- `not_shown`、`inferred`、`uncertain`：允许如实保存，但遗漏检查保留相应缺口。解决疑点后需更新事实记录，不能只修改 issue 状态。

## 补查与独立复核

```powershell
python -X utf8 $ReviewScript audit --work $ReviewWork --summary
python -X utf8 $ReviewScript audit --work $ReviewWork --queue
python -X utf8 $ReviewScript extract --candidates --work $ReviewWork
```

`--queue` 只追加具体缺口的帧及前后上下文，不重新扫描视频，也不登记已查看。重新选帧不会丢掉补查候选。完整 findings 较长时导出到文件，按阶段消费；不能通过截断列表冒充审阅完成。

记录检查就绪后，进行独立遗漏复核：

1. 给可用且获准的独立代理源视频身份、完整状态清单、图片路径、阶段前后背景和用户目标。先让它独立看操作序列并记下操作；避免先用主稿限定它应该看到什么。
2. 再对照主稿检查漏写的对象选择、临时输入/最终值、取消/执行、确认、运行结果与文件交接。真实图片工具查看后，用自己的稳定 actor 名登记。
3. 新发现写入 issues 并修正对应步骤/coverage。没有新增有效证据的缺口保留，不无限重查。
4. 在修正后的内容上重新运行 `audit`，取得当前 `snapshot`，导入下面的复核记录。若修正改变了主稿，复核者需检查修正后的版本，不能直接把旧判断换一个新摘要。

```json
{
  "omission_reviews": [{
    "id": "R01",
    "reviewer": "independent-reviewer",
    "independence": "independent",
    "snapshot": "从当前 audit 输出复制完整的 64 位摘要",
    "checked_state_frames": [0, 3, 6],
    "evidence": ["f000000000", "f000000003", "f000000006"],
    "tool_trace_refs": ["实际图片工具调用位置"],
    "issue_ids": [],
    "conclusion": "no_additional_omissions_found",
    "note": "实际复核范围、比对发现，以及结论适用的边界。"
  }]
}
```

状态列表必须对应当前视频的全部不同状态；示例数字不是固定数量。结论可为 `no_additional_omissions_found`、`gaps_found`、`incomplete`。有发现时引用相关 issue。没有独立代理时用 `independence: self_review` 如实交付，严格门槛会保持未通过；这不是要求用户额外授权或必须启动新任务。

`snapshot` 绑定源内容指纹、全帧索引、计算状态、步骤、疑点、状态说明和被引用图片的哈希。修改这些内容会让旧复核过期。追加查看事件或未引用裁剪不改变被复核内容，但当前引用与查看登记仍会重新检查。审计针对已缓存源指纹；源文件被更改后必须使用新的审阅目录。

名字不同、填写 trace 或摘要匹配，都不能独立证明真的用了不同代理、真的打开图片或真的没有漏读。主代理仍须核对实际工具历史。所有通过字段均使用 `recorded` 口径。

## 交付口径

```powershell
python -X utf8 $ReviewScript validate --work $ReviewWork --require-coverage
python -X utf8 $ReviewScript export --work $ReviewWork
```

- 普通 `validate`：基础记录一致性；可用于旧记录。
- `records_ready_for_omission_review`：状态说明和步骤衔接的程序检查就绪。
- `review_gate_passed_recorded`：再加上针对当前内容的独立复核登记；不是语义完整性证明。
- `semantic_completeness_proven`：始终 false。

未就绪也能导出，报告必须保留缺口、待查帧和复核状态。严格检查返回非零不代表产物应删除或流程应无限重跑。完整模式和第二次查看可能增加时间及模型消耗；显式预算用尽就交付未完成范围，不能按固定帧数宣布完成。
