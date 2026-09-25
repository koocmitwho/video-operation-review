# 操作记录、统计与审计

编写步骤、合并子代理结果或检查证据口径时读本文。

## 目录与身份

每个 `--work` 包含 `review.sqlite3`、`logs/`、按需产生的 `evidence/`；`export` 额外生成 `review.json`、`frames.jsonl`、`omission-audit.json`、`report.md`。输入视频不会复制到输出目录。缓存迁移需连同数据库和证据保留；若有 WAL/SHM 文件，应先结束写进程，再正常打开关闭数据库或使用 SQLite backup，不只复制正在写入的主文件。

源帧身份为“源文件 SHA-256 + v:0 + 0 起始 frame_no”。全图 ID 为 `f000000003`；裁剪 ID 包含坐标，但仍引用同一源帧。重复打开、裁剪或放大均按该身份去重。两个不同帧即使像素相同，若实际分别打开，仍是两个源帧；被代表图覆盖而未打开的帧不计入实际查看。

## 步骤与疑点导入

以下是格式示例，不是任何真实录屏的已确认事实。将字段改为实际观察后保存 UTF-8 JSON，运行 `import-records`。每条步骤必须有所有字段；未出现的菜单、参数或文件标为“未展示/不适用”，不能补猜。时间由 `start_frame/end_frame` 从索引解析，报告显示原始秒和帧号。

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
    "final_parameters": {
      "步长": {"value": "0.02", "unit": "未展示", "evidence": ["f000000006"], "basis": "确认前最终输入框"}
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

步骤状态：`confirmed`（列出的关键事实均有证据且无未解决项）、`partial`（部分确定）、`unresolved`（仍待确认）。没有证据的推测单独列为 issue，不作为已还原步骤。疑点状态：`open`、`blocked`、`resolved`；`blocked` 仅说明现有录屏不足，不是平台任务状态。

顶层 `evidence` 列出本步骤所有引用，参数内部的 evidence 也必须列于顶层，便于校验。校验器验证引用存在且该具体图有查看登记；看过全图不会自动证明后来裁剪图也被看过。文件名相同不证明文件内容/版本相同；源码显示不证明已经运行。跨阶段用可见对象名、路径、窗口标题和参数状态核对交接，不靠时间接近来猜。

上面是兼容的基本步骤结构。默认分层审计还需 `author`、`transition`、`role_evidence`，以及区间、抽查与有界复核，见 [layered-review.md](layered-review.md)。只有显式严格模式才需要逐状态 `coverage` 与 `omission_reviews`，见 [omission-review.md](omission-review.md)。普通 `validate` 通过不代表遗漏检查通过。

子代理返回同一 JSON 结构，并另附每张证据的真实图片工具调用位置、观察、审阅帧清单及阶段前后状态。主代理对照真实工具输出确认后登记，不能批量依据“我已看过”清单登记。重复阶段用稳定 ID 更新；`history` 保留导入版本。不要让多个代理同时写同一个数据库。

## 查看登记与审计

`record-view` 需要已导出的 asset ID、观察者、图片工具类型、实际调用/消息引用、具体视觉观察。可用工具类型为 `view_image`、`read_image`、`image_tool`、`visible_attachment`；DeepSeek Harness 的图片读取直接登记为 `read_image`。使用其他工具并归类为 `image_tool` 时，在 trace 中写明真实工具名称。工具成功返回图片后才能登记，不把文件名当工具调用位置。文字读取、OCR 及不支持图像的模型返回均不算看图。

记录说明应能支持复核，例如：“frame 37，Rate 框为 5，Apply 按钮可见；状态栏被遮住”。不能仅写“已查看”。同一帧反复打开会保存多条事件，但去重计数不变。仅有裁剪的登记计入曾看过的源帧数，候选的完成还需全图查看记录。

`validate` 证明的只是数据库结构、文件哈希和引用一致；无法从调用引用字符串鉴别是否真的调用了图片工具。`independently_verified_visual_frames=null` 是设计边界；不要声称脚本能独立证明视觉查看。主代理对可访问的真实工具历史核对，并在最终报告附一句核对范围；核实不了的子代理结果单列待核实。

## 统计字段

| 字段 | 口径 |
|---|---|
| video_total_frames | 完整干净 ffprobe 索引得到的总数；不完整则 null |
| container_declared_frames | 容器声明，可为空或不准确 |
| computed_frames / computed_ranges | 实际有持久化完整差分记录的源帧及闭区间 |
| candidate_requests / candidate_frames | 合并前请求源帧数 / 完全重复段合并后的代表数 |
| candidates_reviewed_recorded / candidates_pending | 有完整原图查看登记的候选 / 待登记候选 |
| recorded_visual_unique_frames | 任意原图/裁剪查看登记按源帧去重；需对照实际调用核实 |
| recorded_full_image_unique_frames | 有全图查看登记的去重源帧数 |
| independently_verified_visual_frames | 始终 null；仅脚本无法独立核实 |
| unprocessed_ranges / unindexed_tail | 已索引但未计算的闭区间 / 未完成索引的未知尾部 |
| source_frames_without_full_view_record_ranges | 已索引、尚无全图查看登记的源帧闭区间，包含未逐张打开的重复帧 |
| unresolved_issues | 尚未 resolved 的问题，不等同于尚未计算帧 |
| attempts | 索引、计算、抽图各次尝试、数量、状态和日志位置 |
| state_accounting_records / omission_review_records | 逐状态说明记录数 / 遗漏复核登记数，均不是完整性证明 |
| coarse_reviewed_frames_recorded / coarse_reviewed_ranges | 具有本人首尾概览证据的人工区间并集；不等于逐帧看图 |
| fine_reviewed_frames_recorded / fine_reviewed_ranges | 具有合规操作角色原图/裁剪证据且登记 reviewed 的操作区间并集；仍不是每帧视觉计数 |
| fine_examined_frames_recorded / fine_examined_ranges | 已看原图/裁剪并形成合规 before/during/after 证据的操作区间；允许结论 partial，区别于已完成精审 |
| not_fine_examined_ranges | 尚未形成合规操作精审角色证据的范围；不能与尚有疑点、未完成精审的范围混用 |
| not_coarse_reviewed_ranges / not_fine_reviewed_ranges | 各层未完成范围；背景/等待抽样不自动变为全区间精审 |
| candidate_operation_units / true_operation_count | 人工候选步骤 ID 去重数 / 始终 null，不能把候选当真实总操作数 |
| recorded_overview_unique_frames | 实际拼图查看登记涉及的去重源帧；与原图计数可重叠，不能相加得总数 |
| approximate_merge_intervals | 人工近似合并区间数；精确 RGB 身份不受其影响 |

报告必须同时列这几种完成状态：全帧计算、选定候选审阅、全部帧逐张视觉审阅。即使所有代表图都看过，第三项也不会因此完成。审计只有登记口径时须在数值旁标注，不能静默转成“实际核实数”。
