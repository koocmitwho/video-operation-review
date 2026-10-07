# 操作记录、统计与审计

本文定义供代理填写和导入的步骤 JSON、证据引用和统计口径。用户无需准备这些记录；面向用户的步骤、参数、截图、疑点和继续回执按 [交付指引](delivery.md) 整理。

## 目录与身份

每个 `--work` 包含 `review.sqlite3`、`logs/` 和按需产生的 `evidence/`；export 生成 `review.json`、`frames.jsonl`、`omission-audit.json`、`report.md` 及 `export-manifest.json`。输入视频保留在 source.path，并需满足 [自包含媒体边界](method.md)。迁移缓存时保留数据库和证据；活动库使用 SQLite backup，或结束写入并正常关闭数据库后复制。

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

`steps` 和 `issues` 中的 ID 必须是非空字符串；同一批各自列表中不能重复，跨批同 ID 更新继续保留。导入先校验整批，再进入写入事务；类型或同批 ID 冲突会给出如 `steps[0].role_evidence` 的字段位置，整批不会部分写入。已知 `role_evidence`、`transition` 及其受支持子字段须符合文档结构；所有 `evidence` 引用均为非空资产 ID 的列表，JSON 数值须有限。尚未提供的语义证据仍由审计列为缺口，不能为通过结构校验补造事实。未知扩展字段仍保留，schema 继续为 3。

## 纠正误设步骤

片头已经存在的参数可以作为真实操作的前提；没有发生操作时，不必为了填表将其单列为步骤。若已有记录误设，可在原库用 `import-records` 的顶层 `retire_steps` 数组纠正：每项必填非空的 `id`、`reason`、`reviewer`，以及 `replacement_step_ids`（去重的有效步骤 ID 列表，可为空）。替代步骤既可已存在，也可在同批 `steps` 中新增或更新。理由说明误设之处和保留事实的位置，不是新的视觉证据。

导入须在同一批明确处理所有相关 `intervals`、`coverage`、`issues` 的步骤关联；可改写关联，或通过既有 `retire_intervals` 撤下旧区间。程序不猜测关联，不接受遗留的退休 ID 引用。有效步骤与退休列表不能同批使用同一 ID；重复退休、失效替代、自指及同批互相替代均拒绝。退休 ID 不再复用，后续确需增加操作使用新 ID。

原步骤完整 payload、理由、记录者、时间、替代 ID，以及关联记录的纠正前后状态保存到新增的 `step_retirements` 表与 `history` 中。当前 `steps` 只含有效步骤；导出 `review.json` 同时包含 `step_retirements`，报告附录展示纠错历史。原帧、PTS/RGB 身份、资产与查看事件保持不变；退休原记录与三类关联快照的字段、嵌套证据仍参与完整性校验。整批导入使用一个事务，后续任何记录失败都会回滚，包含已进行的退休和历史写入。

退休不能关闭异常：关联的 open/blocked 疑点只能改步骤关联，原问题、状态、帧范围、补查历史及其他字段必须保留，并显式关联至少一个替代步骤；原来关联的其他有效步骤也须保留。范围相交及区间疑点同样受保护。原步骤的内嵌 uncertainties 须逐项保留到替代步骤，partial/unresolved 状态须由仍未确认的替代步骤承接。相关区间出现过 `expand` 抽查时，保守要求提供替代步骤；既有抽查、原范围及展开门禁持续保留，退休不会自动解决它们。没有替代步骤的撤下入口只适用于没有这些未解决内容及展开历史的误设记录。

范围推断形成的其他步骤疑点关联同样保留；不能将其改为显式关联后漏掉仍受影响的操作。替代步骤若已存在，同一退休批次不得丢失它原有的不确定性或提升其未确认状态。退休步骤与既有替代步骤经当前 intervals/coverage 或历史 retired_interval 间接关联的疑点也进入保护集合，即使疑点自身没有步骤或帧范围字段。已经退休的关联区间也从历史中查回，避免先退休区间再退休步骤绕过展开保护。

同一区间 ID 曾多次退休或被重新使用时，每条相关历史 payload 都单独保存在 `references_before.intervals`，各自的 issue_ids 和 evidence 继续参与保护与校验，当前版本不能遮蔽旧版本。归档中的这些同 ID 版本逐条校验；它们不是一批新的区间导入。普通导入仍拒绝同批重复 ID，原有跨批更新与区间退休入口不变。

纠正会使绑定旧内容的 strict/layered 复核快照失效；快照纳入非空退休历史，因此“新增误设步骤→退休”也不能让更早的复核复活。没有退休历史时保持旧快照算法兼容。受影响区间的旧抽查也可能失效。按新内容重新核对并登记，不能复制旧 snapshot 冒充当前复核。`valid`、`review_complete` 和严格模式门禁不因退休而放宽。

兼容边界：本实现对 schema 3 增量增加退休表，未使用退休的旧库与旧 JSON 继续可读写。RC.4 及更早程序不理解 `retire_steps`，会忽略该输入字段；它们也不会导出或检查新增退休表，因此**不能用旧程序继续写入、验证或重新导出已使用步骤退休的工作库**。继续使用支持该入口的程序，保留原 SQLite 和完整新导出；跨版本回退用未纠错的冻结副本，不能把旧程序的通过结论用于新退休契约。

English contract: `retire_steps` is an atomic, reasoned correction in the existing ledger. Active steps are exported separately from immutable retired originals and their before/after references. Source frames, assets and view events stay unchanged; archived evidence still participates in integrity checks. Open questions, inline uncertainties and expansion history cannot be erased, and prior review snapshots become stale. Schema 3 gains an additive retirement table. RC.4 and earlier ignore the new request and archive: do not use those versions to write, validate or re-export a ledger that uses retirement. They remain supported for untouched legacy ledgers.

## 查看登记

record-view 接收 asset ID、actor、tool、trace 和具体 observation。工具类型为 view_image、read_image、image_tool、visible_attachment；封装工具的实际名称写入 trace。

图片展示后登记调用位置，如 `read_image#msg-42`、`session://abc/step-7`、`/tmp/attach/xxx.png#L1`。形式检查识别图片文件名、短裸名称和资产自身 path/id，并提示填写调用引用。交付时把登记与宿主实际工具结果核对，写明核对范围。

观察示例：“frame 37，Rate 框为 5，Apply 按钮可见；状态栏待辨认”。重复打开保存多条事件，独立源帧计数保持去重；候选完成采用原图 native 查看登记。

## 校验与完成度

`valid` 表示源视频、证据哈希和记录引用的完整性；`review_complete` 要求全帧计算、候选选择、候选原图查看和当前模式复核门禁均完成。默认 validate 按 valid 返回 0/1，`--require-coverage` 将 review_complete 加入退出条件：记录有效但审阅未完成时仍为 `valid=true`、`review_complete=false`，退出码 1，门禁原因写入 `coverage_errors`，记录错误保留在 `errors`。

source_verification 包含源路径、预期/当前 SHA-256、method 和 rehashed。文件属性匹配时复用扫描哈希，属性变化时重算；`--rehash-source` 显式触发完整哈希。导出报告分别展示记录完整性与审阅完成度。

旧库中的非法步骤或疑点会返回 `errors` 中的 `invalid_step` / `invalid_issue` 及 `record_contract_errors`，不会自动删除或修写原记录。`status` 同样提供诊断，`annotation_counts_available=false` 时相关粗审、精审与操作计数/范围为 null；null 表示无法可靠统计，不是零。此时审计显示 `blocked_invalid_records`，导出在更新任何交付文件前拒绝，先根据字段诊断在保留原记录的前提下修正。结构有效仍不证明自由文字与视频一致。

报告还会将能够关联到步骤或参数的审计冲突、证据缺口显示为待核实，保留原记录状态、参数值、发现代码和证据。能定位参数键的参数内部矛盾只降级对应参数；其他步骤不会仅因整个审阅尚未完成而被一并降级。这是呈现当前审计结果，不改写原始判断或关闭疑点。

## 导出代次与中断检查

正常导出保留上述四个固定交付文件名，并最后生成 `export-manifest.json`。清单字段为 `version: 1`、`state: "complete"`、`generation` 和 `files`；每个文件条目含 `sha256` 与字节数 `size`。CLI 返回值增加 `export_manifest` 与 `generation`。`review.json`、`omission-audit.json` 含 `export_generation`，`report.md` 末尾的 HTML 注释保留同一代次；`frames.jsonl` 通过清单哈希归属于该代。

消费一组新交付时按次序检查：

1. 工作目录不存在 `export.pending.json`；存在时不要读取为已完成的一代。
2. 清单为 `version=1`、`state=complete`，四个文件均存在，大小和 SHA-256 与清单一致。
3. 两份 JSON 与报告注释的代次对应清单 `generation`。清单描述导出文件组完整性，不表示 `review_complete=true` 或语义正确。

全部内容先生成到本工作目录下独立的 `.export-*` 目录，文件切换前写入 `export.pending.json`。普通切换异常会尝试恢复上一代；回滚失败或进程在切换期间被终止时，pending 和可用的暂存/`previous` 备份保留，下一次 export 会拒绝覆盖。先保留现场，核对 pending 指向的目录、备份与清单，再决定恢复哪一代；不要在未核对文件前删除 pending，也不要把手工删除标记当成恢复。程序不自动恢复，跨文件替换不保证断电原子性。

旧导出没有清单时仍作为旧格式记录保留，不要求删除，也不能倒推它已经经过代次校验。继续使用有效的旧库导出即可产生新清单；schema 3 与旧固定链接保持兼容。

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
