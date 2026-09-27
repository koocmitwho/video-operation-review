# 严格逐状态审阅

strict/coverage 用于逐状态穷尽复核。默认分层流程见 [layered-review.md](layered-review.md)，本文的 transition 结构也用于分层步骤。

## 检查对象

先 select --mode coverage。每段连续相同 RGB 画面作为一个状态，以首帧 frame_no 标识。审阅者查看状态并判断其操作归属。audit 遍历已计算的完整状态索引，检查状态说明、原图登记、步骤关联、参数/对象/文件衔接、疑点、引用及当前复核。

## 逐状态记录

audit.coverage.states 提供代表帧、原始时间和段结束帧。实际查看后导入：

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

operation 说明变化并关联具体步骤；context 描述有原图依据的背景状态；uncertain 关联待核对 issue。reviewer 对应 record-view.actor。精确重复段内的原图可作为该状态证据，查看数量按实际登记源帧去重。相同 frame_no 更新当前判断并保留 history。

## 步骤前后状态

基础步骤补充以下字段，嵌套 evidence 同时列入顶层 evidence：

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
      "note": "状态栏可见 Applied rate = 5，据此登记应用状态。"
    },
    "result": {
      "status": "observed",
      "evidence": ["f000000006"],
      "note": "主界面 Current rate 显示 5。"
    }
  }
}
```

使用稳定且带对象作用域的键，如 SampleA.rate；跨步骤保持键名和值类型一致。待辨认值使用 null。控件可见状态可写 `{"value":{"visible":false},"evidence":["关闭画面 ID"]}`；打开时可写 `{"value":{"visible":true,"text":"20"},"evidence":["输入框画面 ID"]}`。业务参数和控件状态分别建模。

按时间顺序编写细步骤，用 phase 分组。前一步 after 与后一步 before 的同名键出现不同值时进入补查清单，审计保留跨步骤的最近已登记值。

confirmation/result 的 observed 关联可见状态和证据；not_applicable 说明适用理由；not_shown/inferred/uncertain 保留当前疑点并在补查后更新。

## 补查与复核

命令变量按 [examples.md](examples.md) 的技能根设置，依次运行 audit --summary、audit --queue、extract --candidates。--queue 添加具体补查帧与邻接上下文，候选保留原选择历史。

1. 复核者接收源身份、完整状态序列、图片路径、阶段背景和目标，先查看操作序列并记录观察。
2. 对照主稿检查对象选择、临时值、取消/执行、确认、结果和文件交接，以自己的 actor 登记图片调用。
3. 将发现写入 issues，并更新对应步骤和 coverage。
4. 运行 audit 取得当前 snapshot，在当前内容上登记复核结果。

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
    "note": "实际复核范围、样本和比对发现。"
  }]
}
```

checked_state_frames 填当前完整状态清单。结论为 no_additional_omissions_found、gaps_found 或 incomplete；发现关联 issue。自审使用 independence=self_review，报告保留该复核状态。

tool_trace_refs 关联该复核者对 evidence 的有效查看登记，帧号和哈希一起核对。snapshot 绑定源内容、索引、计算状态、步骤、疑点、状态说明与引用图片。相关内容变化后重新复核，追加查看事件保持内容快照。

## 交付

运行 validate --require-coverage 与 export。valid 表示记录完整性，review_complete 表示候选与当前门禁完成；records_ready_for_omission_review 表示进入复核的记录已就绪，review_gate_passed_recorded 包括当前独立复核登记。报告输出当前进度、待查帧和复核状态，按实际预算安排后续检查。
