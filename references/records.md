# 操作记录、统计与审计

本文定义供代理填写和导入的步骤 JSON、证据引用和统计口径。用户无需准备这些记录；面向用户的步骤、参数、截图、疑点和继续回执按 [交付指引](delivery.md) 整理。

## 目录与身份

每个 `--work` 包含 `review.sqlite3`、`logs/` 和按需产生的 `evidence/`；export 生成 `review.json`、`frames.jsonl`、`omission-audit.json`、`report.md`、`handoff.md` 及 `export-manifest.json`。输入视频保留在 source.path，并需满足 [自包含媒体边界](method.md)。迁移缓存时保留数据库和证据；活动库使用 SQLite backup，或结束写入并正常关闭数据库后复制。

存在独立补证时，一并保留 `supplements/`。其中每个 ID 对应固定来源快照、所选原图及 `package.json`；数据库元数据绑定该清单的 SHA-256，另存本地查看记录。它们属于用户审阅资料，不属于技能发行包。

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

新导入的 `resolved` 疑点必须有 `resolution` 对象，`mode` 为 `evidence` 或 `withdrawn`，两者均须非空字符串 `reviewer` 和 `reason`。`evidence` 模式还须非空 `evidence` 资产 ID 数组，引用本工作库已经查看的证据；`withdrawn` 模式须非空字符串 `basis`，说明疑点为什么误设并指向可核对的原记录。嵌套证据仍接受原有资产、哈希和查看记录校验；这里只约束依据的记录方式，不自动判断理由是否真实。新导入缺依据会拒绝整批写入。

旧库的 resolved 标签、缺失的 resolution 或旧字符串说明保持可读，原记录不自动修改；仅因缺少新结案依据不会使 `valid` 失败。但它们显示“结案依据待补”，作为未解决事项参与报告、精审和复核门禁，因此 `review_complete` 可能由原来的通过变为待完成。补依据时提交该疑点的完整更新记录并保留已有 attempts，不能只改一个状态字段或删掉历史。

`final_parameters` 只把有确认或应用依据的值表述为生效值；未确认的业务值用 null，并在 basis、confirmation_action、visible_result 或 uncertainties 中保留最后输入、取消及可见状态。上述示例中的 `0.02` 是观察到的输入，不能当作已应用。用户说明按 phase 与 selected_objects 整理，同名参数在不同对象、阶段分别列出；沿用现有字段，不合并成一个全局值。

可选 `input_action` 是审阅者依据画面记录的输入过程，用于报告的“填写什么”，例如“Rate 输入 20，随后取消”。没有发生输入时可写“只核对现有值”；未展示时写明未展示。`final_parameters` 保存阶段结果，不能从结果值反推输入动作。旧记录没有 `input_action` 时仍可导出，不要求补造过程。

疑点可选 `impact`、`next_action`、`needed_information` 分别记录影响、下一步和需要补充的信息；仍保留原有 question、帧范围和 attempts。

疑点应写清时间范围、关联操作及对复现结果的影响；attempts 保留已补查的证据、新信息和仍缺的内容。若原视频缺少相应画面，说明需要哪段补充材料，保留 open 或 blocked，继续其他可完成的步骤；不要反复读取同一证据来推断未知值。

顶层 evidence 包含步骤的全部引用，包括参数内部的 evidence。每个引用关联具体图片和查看登记。文件交接按可见对象、路径、窗口标题、版本与参数状态逐项核对。

分层记录补充 author、transition、role_evidence、intervals、抽查和复核，见 [layered-review.md](layered-review.md)。严格模式的 coverage 和 omission_reviews 见 [omission-review.md](omission-review.md)。多位审阅者返回相同结构及实际工具引用，由单一记录者核对后串行导入。稳定 ID 用于更新，history 保留版本。

`steps` 和 `issues` 中的 ID 必须是非空字符串；同一批各自列表中不能重复，跨批同 ID 更新继续保留。导入先校验整批，再进入写入事务；类型或同批 ID 冲突会给出如 `steps[0].role_evidence` 的字段位置，整批不会部分写入。已知 `role_evidence`、`transition` 及其受支持子字段须符合文档结构；所有 `evidence` 引用均为非空资产 ID 的列表，JSON 数值须有限。尚未提供的语义证据仍由审计列为缺口，不能为通过结构校验补造事实。未知扩展字段仍保留，schema 继续为 3。

## 交付上下文与照做验收

`import-records` 接收顶层 `delivery_context` 对象；更新时提交完整对象。`question`、`scope`、`next_action` 均为非空字符串。`used_language_source_ids` 是去重的已导入语言来源 ID 数组，仅列审阅者实际采用的来源，没有则为 `[]`。文本导入本身不等于使用，更不表示实际听取音频。`tracks` 的成功检查结果保存为 `media_tracks`，报告结合它与使用声明展示音轨和旁白状态。

顶层 `reproduction_checks` 数组只追加真实照做记录，不覆盖已有 ID。每项必填：

| 字段 | 契约 |
|---|---|
| `id` | 非空且未使用的验收 ID；同批也不得重复 |
| `reviewer` / `scope` / `environment` / `result` | 非空字符串；实际执行者、覆盖范围、环境及观察结果 |
| `step_ids` | 非空、去重的当前有效步骤 ID 数组 |
| `outcome` | `passed`、`failed` 或 `partial`；如实保留失败和未完成 |
| `content_snapshot` | 对应交付的 `status.delivery_snapshot`；导入时必须与当前内容一致 |
| `artifacts` | 非空数组；每项有工作目录内实际文件的相对 `path` 和匹配的 64 位小写十六进制 `sha256` |

照做产物建议放在 `replay/`。导出文件、清单、pending、审阅数据库及 WAL/SHM、`.export-*` 暂存内容、源视频、数据库已登记的原图或裁剪均不得作为新照做产物；保存真正的运行日志或结果文件，不用已有审阅材料代替。文件身份校验不判断日志或产物的语义。

快照绑定源 SHA-256、本轮问题、范围、语言使用声明，以及步骤、疑点、区间、步骤退休和语言来源记录；存在补证时也包含其元数据与本地查看记录。先导入当前交付内容并读取快照，再针对这份交付实际照做；内容中途改变时重验，不把旧结果换成新 snapshot。仅更新 `next_action` 不使验收过期。`recorded_at` 由程序生成；验收条目与同批其他记录在同一事务内提交或回滚。

导出保留每条验收的原 `outcome`，另计算 `freshness`：`current` 表示内容和文件身份仍对应；`stale` 表示内容改变；`evidence_changed` 表示文件缺失或 SHA-256 不符；`record_invalid` 表示审阅记录完整性待修复。文件异常优先于内容过期展示。哈希匹配证明文件身份，不能证明结果正确；照做记录不授予执行视频中命令的权限，也不改变审阅门禁或成为真人验收。

本节及下述补证契约从 RC.6 起提供，schema 仍为 3。RC.5 及更早版本可能保留 SQLite 未知元数据，却不会维护、校验或导出这些内容；不能用它们继续写入、验证或重导出已采用新交付、补证或 `followup` 的工作库。保留原库与完整新导出，回退使用未采用新字段的冻结副本。

## 按问题范围优先查看

`queue` 只读取既有候选及查看记录，不改变 requests、candidates、分段或覆盖。默认返回最多 8 张待 native 全图查看的候选；`--batch-size` 须为正整数，只限制本次响应。原图查看登记后重调队列即可获得下一批，不使用 offset。overview 或裁剪查看不会让原图要求消失，返回相同像素的非连续片段也不会互相代替。

`--start` 与 `--end` 须一起提供，为有限且有序的原始时间闭区间。优先级按候选 `represented_requests` 对应原帧的 `time_s` 判断，保留非零 PTS 与小数时间；某张代表图在窗口外，但它代表的请求帧在窗口内时仍优先返回。范围内候选在前，其余按 `frame_no` 在后；空窗口仍返回全局待审候选。没有范围时全部按帧号排序。

返回 `total_pending`、`range_pending`（无范围为 null）、`batch`、`remaining_after_batch` 和 `source`。`remaining_after_batch` 仅表示本次未返回的数量，不表示本批已经看过；再次调用前没有新查看记录，会返回同一批。各项保留代表帧原时间、原因、资产 ID、`absolute_path`（未提取时 null）、`represented_requests` 以及实际匹配的 `matched_request_ranges`。`source_reverified=false` 表示这里只返回扫描时身份，未再次检查原文件；源完整性仍用 validate 核对。`range_scope_is_not_full_review=true` 明确局部优先级不授予全片完成结论。

## 独立补证与原疑点的后续说明

`supplement-import` 明确读取另一审阅目录的完整导出，保存固定快照。源目录须无 pending，五份固定交付文件与清单哈希、大小及导出代次一致；`review.json` 记录的 `validation.valid` 与 `source_verification.valid` 须为 true，验证中的预期、当前 SHA-256 必须与源身份相同。这里核对导出记录和所选图片，不跟随或读取其中的 `source.path`，也不要求来源已经通过完整审阅门禁。旧四文件导出先由兼容工具重新导出，不能手工删改清单以凑齐。

仅可选择来源导出中已有 full 原图和匹配 native 查看记录的资产；每张图保留源帧信息、图像 SHA-256 和归属查看记录。导入者填写 ID、actor 和 note。拒绝同一审阅目录、相同源文件 SHA-256、重复 ID、越界路径及目录链接；一次导入不能覆盖既有快照。源录像和其他审阅库仍保持独立，不把补交内容拼进原片索引。

`archive_non_live=true` 表示快照固定在导入时的代次。源目录以后变化或消失不会自动刷新它；要引用新材料，应以新 ID 明确导入新快照。当前审阅目录连同数据库及 `supplements/` 迁移后可继续检查。本地清单、来源报告、图片或查看绑定损坏时，`supplements` 返回 invalid，相关引用与 validate 报完整性问题；保留现场核对，不更新哈希掩盖差异。

导入不代表后续说明的作者已看过。作者实际打开目标目录内的补证图后，使用 `supplement-view` 保存自己的 actor、实际图片工具、trace 和 observation。该记录独立于来源查看，也不计入原片 views、候选完成或 coverage。

随后用 `import-records` 提交原疑点的完整更新记录，保留原 `question`、`status`、范围和已有 `attempts`，仅追加：

```json
{
  "followup": {
    "claim": "后交录像显示重新启动后的界面为所需语言。",
    "original_record_limit": "原录像没有展示重新启动及当时设置的生效过程。",
    "reviewer": "实际查看本地补证的记录者",
    "supplement_refs": [{"supplement_id": "SUP1", "asset_id": "f000000003"}]
  }
}
```

前三项须为非空字符串，`supplement_refs` 须明确列出已导入的补证 ID 与资产 ID；每项都要求该 reviewer 本人在当前快照上的实际 native 查看登记。引用不存在、快照失效或作者未查看时拒绝整批导入。`followup` 支持说明新材料能证明什么，不自动关闭原疑点，也不把原片未展示的过程改写为已展示。`resolution.mode` 仍只支持 `evidence` / `withdrawn`，没有 `supplement` 模式；后续主张不能充当原片确认动作或完整度证据。报告在原疑点下展示独立来源、帧、代次与原片限制。

## 纠正误设步骤

片头已经存在的参数可以作为真实操作的前提；没有发生操作时，不必为了填表将其单列为步骤。若已有记录误设，可在原库用 `import-records` 的顶层 `retire_steps` 数组纠正：每项必填非空的 `id`、`reason`、`reviewer`，以及 `replacement_step_ids`（去重的有效步骤 ID 列表，可为空）。替代步骤既可已存在，也可在同批 `steps` 中新增或更新。理由说明误设之处和保留事实的位置，不是新的视觉证据。

导入须在同一批明确处理所有相关 `intervals`、`coverage`、`issues` 的步骤关联；可改写关联，或通过既有 `retire_intervals` 撤下旧区间。程序不猜测关联，不接受遗留的退休 ID 引用。有效步骤与退休列表不能同批使用同一 ID；重复退休、失效替代、自指及同批互相替代均拒绝。退休 ID 不再复用，后续确需增加操作使用新 ID。

原步骤完整 payload、理由、记录者、时间、替代 ID，以及关联记录的纠正前后状态保存到新增的 `step_retirements` 表与 `history` 中。当前 `steps` 只含有效步骤；导出 `review.json` 同时包含 `step_retirements`，报告附录展示纠错历史。原帧、PTS/RGB 身份、资产与查看事件保持不变；退休原记录与三类关联快照的字段、嵌套证据仍参与完整性校验。整批导入使用一个事务，后续任何记录失败都会回滚，包含已进行的退休和历史写入。

退休不能关闭异常：关联的未解决疑点（含结案依据待补的旧 resolved）只能改步骤关联，原问题、状态、帧范围、补查历史及其他字段必须保留，并显式关联至少一个替代步骤；原来关联的其他有效步骤也须保留。范围相交及区间疑点同样受保护。原步骤的内嵌 uncertainties 须逐项保留到替代步骤，partial/unresolved 状态须由仍未确认的替代步骤承接。相关区间出现过 `expand` 抽查时，保守要求提供替代步骤；既有抽查、原范围及展开门禁持续保留，退休不会自动解决它们。没有替代步骤的撤下入口只适用于没有这些未解决内容及展开历史的误设记录。

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

正常导出生成五个固定交付文件：`review.json`、`omission-audit.json`、`frames.jsonl`、`report.md`、`handoff.md`，并最后生成 `export-manifest.json`。清单字段为 `version: 1`、`state: "complete"`、`generation` 和 `files`；每个文件条目含 `sha256` 与字节数 `size`。CLI 返回值包含 `export_manifest`、`generation` 和 `handoff` 路径。`review.json`、`omission-audit.json` 含 `export_generation`，`report.md` 与 `handoff.md` 的 HTML 注释保留同一代次；`frames.jsonl` 通过清单哈希归属于该代。

消费一组新交付时按次序检查：

1. 工作目录不存在 `export.pending.json`；存在时不要读取为已完成的一代。
2. 清单为 `version=1`、`state=complete`，五个文件均存在，大小和 SHA-256 与清单一致。
3. 两份 JSON、报告和交接文件注释的代次对应清单 `generation`。清单描述导出文件组完整性，不表示 `review_complete=true` 或语义正确。

全部内容先生成到本工作目录下独立的 `.export-*` 目录，文件切换前写入 `export.pending.json`。普通切换异常会尝试恢复上一代；回滚失败或进程在切换期间被终止时，pending 和可用的暂存/`previous` 备份保留，下一次 export 会拒绝覆盖。先保留现场，核对 pending 指向的目录、备份与清单，再决定恢复哪一代；不要在未核对文件前删除 pending，也不要把手工删除标记当成恢复。程序不自动恢复，跨文件替换不保证断电原子性。

已有 `handoff.md` 若是用户手写、手改或与上一代清单哈希不符，export 会在改动任何交付文件前拒绝。将原文另名保留，把需要延续的意图写入 `delivery_context`，再导出生成受管理的交接文件；不要删除用户笔记来绕过检查。

旧四文件清单和没有清单的旧导出仍按各自原格式保留，不要求删除，也不能倒推它们已经包含新交接文件。用本次兼容实现导出有效旧库可生成五文件清单；缺失的本轮问题、语言使用和照做记录如实显示未记录。schema 3 与原固定链接保持兼容，但旧程序不能用来维护新五文件交付。

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
| unresolved_issues | open/blocked，以及缺少合规结案依据的旧 resolved 疑点列表 |
| delivery_snapshot | 当前交付内容快照；照做验收绑定该值，不代表审阅完成 |
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
