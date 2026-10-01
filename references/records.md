# 操作记录、统计与审计

本文定义供代理填写和导入的步骤 JSON、证据引用和统计口径。用户无需准备这些记录；面向用户的步骤、参数、截图、疑点和继续回执按 [交付指引](delivery.md) 整理。

## 目录与身份

每个 `--work` 包含 `review.sqlite3`、`logs/` 和按需产生的 `evidence/`；export 生成 `review.json`、`frames.jsonl`、`omission-audit.json`、`report.md`。输入视频保留在 source.path。迁移缓存时保留数据库和证据；活动库使用 SQLite backup，或结束写入并正常关闭数据库后复制。

源帧身份为“源文件 SHA-256 + v:0 + 0 起始 frame_no”。全图 ID 如 `f000000003`，裁剪 ID 附带坐标并继承源帧。查看事件按该身份去重，精确重复段另外保留代表映射。

## 步骤与疑点导入

下面是字段示例。由代理按实际观察填写，保存 UTF-8 JSON 后运行 import-records。时间由 start_frame/end_frame 查询原始索引。

```json
{
  "steps": [{
    "id": "S02",
    "phase": "参数设置",
    "start_frame": 3,
    "end_frame": 6,
    "software": "实际软件名，未知则注明",
    "module": "实际模块",
    "menu_path": ["菜单名", "子菜单名"],
    "selected_objects": ["可见选中对象"],
    "input_action": "输入框最后显示 0.02；没有看到确认或应用后状态",
    "final_parameters": {
      "步长": {"value": null, "unit": "未展示", "evidence": ["f000000006"], "basis": "最后输入框显示 0.02；确认或应用后状态未见，生效值未知"}
    },
    "confirmation_action": "未看清确认动作，待补查",
    "visible_result": "对话框关闭；尚未展示运行结果",
    "input_files": [{"visible_name": "input.csv", "full_path": "未展示", "role": "输入"}],
    "output_files": [],
    "evidence": ["f000000003", "f000000006"],
    "uncertainties": ["关闭对话框是否源于确认或取消尚不明确"],
    "status": "partial"
  }],
  "issues": [{
    "id": "Q02",
    "status": "open",
    "question": "最终输入后是否确认执行？",
    "start_frame": 3,
    "end_frame": 6,
    "attempts": [{
      "original_time_range": [0.4, 0.8],
      "action": "补查原图和确认按钮区域",
      "evidence": ["f000000006"],
      "new_information": "按钮被遮挡，未获得新证据",
      "conclusion": "保留疑点，不把关闭窗口解释为执行"
    }]
  }]
}
```

步骤状态为 `confirmed`、`partial`、`unresolved`；疑点状态为 `open`、`blocked`、`resolved`。`confirmed` 对应证据齐全且疑点已解决的步骤，`blocked` 表示该疑点等待补充材料。

`final_parameters` 只把有确认或应用依据的值表述为生效值；未确认的业务值用 null，并在 basis、confirmation_action、visible_result 或 uncertainties 中保留最后输入、取消及可见状态。上述示例中的 `0.02` 是观察到的输入，不能当作已应用。用户说明按 phase 与 selected_objects 整理，同名参数在不同对象、阶段分别列出；沿用现有字段，不合并成一个全局值。

可选 `input_action` 是审阅者依据画面记录的输入过程，用于报告的“填写什么”，例如“Rate 输入 20，随后取消”。没有发生输入时可写“只核对现有值”；未展示时写明未展示。`final_parameters` 保存阶段结果，不能从结果值反推输入动作。旧记录没有 `input_action` 时仍可导出，不要求补造过程。

疑点可选 `impact`、`next_action`、`needed_information` 分别记录影响、下一步和需要补充的信息；仍保留原有 question、帧范围和 attempts。

疑点应写清时间范围、关联操作及对复现结果的影响；attempts 保留已补查的证据、新信息和仍缺的内容。若原视频缺少相应画面，说明需要哪段补充材料，保留 open 或 blocked，继续其他可完成的步骤；不要反复读取同一证据来推断未知值。

顶层 evidence 包含步骤的全部引用，包括参数内部的 evidence。每个引用关联具体图片和查看登记。文件交接按可见对象、路径、窗口标题、版本与参数状态逐项核对。

分层记录补充 author、transition、role_evidence、intervals、抽查和复核，见 [layered-review.md](layered-review.md)。严格模式的 coverage 和 omission_reviews 见 [omission-review.md](omission-review.md)。多位审阅者返回相同结构及实际工具引用，由单一记录者核对后串行导入。稳定 ID 用于更新，history 保留版本。

## 查看登记

record-view 接收 asset ID、actor、tool、trace 和具体 observation。工具类型为 view_image、read_image、image_tool、visible_attachment；封装工具的实际名称写入 trace。

图片展示后登记调用位置，如 `read_image#msg-42`、`session://abc/step-7`、`/tmp/attach/xxx.png#L1`。形式检查识别图片文件名、短裸名称和资产自身 path/id，并提示填写调用引用。交付时把登记与宿主实际工具结果核对，写明核对范围。

观察示例：“frame 37，Rate 框为 5，Apply 按钮可见；状态栏待辨认”。重复打开保存多条事件，独立源帧计数保持去重；候选完成采用原图 native 查看登记。

## 校验与完成度

`valid` 表示源视频、证据哈希和记录引用的完整性；`review_complete` 要求全帧计算、候选选择、候选原图查看和当前模式复核门禁均完成。默认 validate 按 valid 返回 0/1，`--require-coverage` 将 review_complete 加入退出条件：记录有效但审阅未完成时仍为 `valid=true`、`review_complete=false`，退出码 1，门禁原因写入 `coverage_errors`，记录错误保留在 `errors`。

source_verification 包含源路径、预期/当前 SHA-256、method 和 rehashed。文件属性匹配时复用扫描哈希，属性变化时重算；`--rehash-source` 显式触发完整哈希。导出报告分别展示记录完整性与审阅完成度。

## 统计字段

| 字段 | 口径 |
|---|---|
| video_total_frames | 完整干净索引得到的可解码呈现帧总数；待完成时 null |
| container_declared_frames | 容器声明的帧数 |
| frame_count_basis | decoded_presentation_frames，frame_no 为呈现顺序序号 |
| container_frame_count_mismatch | 两种已知计数的比较结果；待比较时 null |
| computed_frames / computed_ranges | 已持久化差分的源帧数与闭区间 |
| candidate_requests / candidate_frames | 请求源帧数 / 精确重复合并后的代表数 |
| candidates_reviewed_recorded / candidates_pending | 有 native 原图登记的候选 / 待查看候选 |
| recorded_visual_unique_frames | 原图、裁剪、拼图查看事件按源帧全局去重 |
| recorded_full_image_unique_frames | native 全图登记按源帧去重 |
| recorded_overview_unique_frames | overview 查看事件按源帧去重；各粒度可交叠 |
| independently_verified_visual_frames | 独立核实过的源帧数；脚本无法独立核实，恒为 null |
| unprocessed_ranges / unindexed_tail | 待计算闭区间 / 待索引尾部 |
| source_frames_without_full_view_record_ranges | 待补充 native 全图查看登记的源帧范围 |
| unresolved_issues | open/blocked 疑点列表 |
| attempts | 各次探测、索引、计算、抽图、轨道和字幕尝试的状态、数量与日志 |
| state_accounting_records / omission_review_records | 逐状态说明 / 遗漏复核登记数 |
| coarse_reviewed_frames_recorded / coarse_reviewed_ranges | 有首尾概览依据的人工区间并集 |
| fine_examined_frames_recorded / fine_examined_ranges | 有合规 before/during/after 原图或裁剪证据的操作区间并集，包含 partial |
| fine_reviewed_frames_recorded / fine_reviewed_ranges | 已登记 reviewed 且角色证据齐全的操作区间并集 |
| not_coarse_reviewed_ranges / not_fine_examined_ranges / not_fine_reviewed_ranges | 对应审阅层级的后续范围 |
| candidate_operation_units | 人工候选步骤 ID 去重数 |
| true_operation_count | 视频真实操作总数；程序不判定，恒为 null |
| approximate_merge_intervals | 人工近似合并的区间数 |
| review_gate_passed_recorded | 当前模式记录是否满足复核规则；只比对记录，不构成独立核实 |
| semantic_completeness_proven | 语义完整性是否被证明；恒为 false |

交付同时报告全帧计算、时间线粗审、操作精审、候选完成与实际图片查看登记，并附工具核对记录。

已关联未解决疑点的操作区间仍可计入“已进行精审”，不计入“已完成精审”。关联采用区间 issue_ids、疑点 step_ids/step_id；没有显式步骤关联时使用相交帧范围。原步骤状态和疑点历史保留，报告标题将受疑点影响的 confirmed 步骤显示为待核实。
