# 0.1.0-rc.6

2026-10-13，交付、独立补证与问题优先审阅的预发布候选。此页记录候选内容；实际发布以对应 Git 提交、tag、CI 和下载安装回执为准。既有发行标签和资产保留。

## 本次变化

- 报告先给连续操作清单，完整证据可展开查看；呈现音轨检查、语言使用与真实照做记录。照做记录绑定交付内容和产物哈希，内容或证据改变时显示失效原因。
- 新疑点结案必须提供记录者、理由以及本库证据或误设撤销依据。旧 resolved 缺依据时保留原文，按结案依据待补参与完成门禁。
- `delivery_context` 保存问题、范围和下一步；固定 `handoff.md` 与另外四份交付文件同代导出。手写交接笔记受覆盖保护，已有导出失败恢复流程保留。
- `supplement-import` 保存另一份完整导出的独立来源快照。后续说明的作者实际查看本地原图并登记后，使用疑点 `followup` 关联补证；原问题、状态、范围与补查历史继续保留。
- `queue` 以用户问题的原始 PTS 范围优先返回一批既有待看原图。按 represented requests 匹配范围，保留代表图在范围外的精确重复段；实际登记后重调，无 offset，不减少候选或审阅要求。
- 优化逐帧变化计算的实现，保持原有帧身份、变化指标、分段与候选结果。没有新增 OCR、ASR、云服务或运行依赖。

入口及完整字段见 [命令示例](examples.md)、[记录契约](records.md) 与 [用户交付](delivery.md)。

## 补证如何解释

导入只接受独立源的完整五文件导出，核对导出代次、文件摘要、已记录的源哈希验证以及所选 full/native 原图的查看归属。来源查看不会自动成为当前作者的查看；必须实际打开本地快照再登记。来源录像、原帧与原审阅库不被拼接或改写。

`followup` 分别保存后续主张与 `original_record_limit`，不自动改变原疑点状态，不计入原片候选、确认动作或 coverage。`resolution.mode` 继续只有 `evidence` / `withdrawn`，没有补证结案模式。例如，后交材料可以支持当前界面为某种语言；它不能补写原录像没有展示的重新启动过程。

`archive_non_live=true` 表示导入时的固定快照。源目录以后变化不自动刷新；新内容用新 ID 导入。迁移目标目录时保留数据库与 `supplements/`。本地清单、来源报告、图片或查看绑定变化会造成完整性错误，不把旧通过继续用于损坏快照。

## 机器阶段测量

同一份 64.289 秒 Inkscape 公开录像，在 Windows、Python 3.12.10、NumPy 2.5.1、FFmpeg 8.1.2 下完成两组隔离配对：

| 配对 | 优化前扫描 | 优化后扫描 | 扫描耗时下降 |
|---|---:|---:|---:|
| 2 | 111.394 秒 | 72.039 秒 | 35.33% |
| 3 | 116.336 秒 | 74.069 秒 | 36.33% |

全部 1903 帧的 18 个字段、394 个建议段、573 个请求和候选逐项一致。配对 1 的扫描与诊断存在约两秒重叠，原记录保留但不计入上述隔离验收。两组都没有进行视觉审阅，两边图片工具调用和图像输入均为 0；该结论只覆盖此素材和环境的机器扫描阶段。队列调整返回次序与批量，不据此宣称少看图、整体审阅省时或语义准确率提升。

来源 SHA-256、顺序、逐表摘要和测量边界见 [脱敏摘要](../validation/completion-20261013.json)，原媒体的归属与许可见 [第三方声明](../examples/open-cases/THIRD_PARTY_NOTICES.md)。发布专用全套回归、对应提交 CI、真实补交流程和发行包下载验收各自记录，不用这里的机器测量代替。

## 本地工作流核验

两份来源哈希不同的公开 VS Code 录屏用于独立追加示例。导入后实际打开两张补证原图并登记，原库的 44 帧、44 个资产、44 条查看记录和 3 个步骤保持不变；原问题仍为 blocked，记录完整性通过、原片审阅未完成。两个片段不证明同一文档或会话延续。

Inkscape 的 45–50 秒问题队列优先返回 3 张原图，实际查看登记后总候选仍为 573、待查看从 573 变为 570，范围内待查看从 42 变为 39；下一批不重复上述已看候选。此项是局部工作流核验，不是全片语义验收。详情见同一脱敏摘要。

## 兼容与分发

数据库仍为 schema 3，旧 strict/layered 模式和审阅完成条件保留。新结案依据会使缺依据的旧 resolved 按待补处理，不自动改写它的历史。`valid` 仍描述来源、证据与记录完整性；`review_complete` 仍要求候选查看与当前复核门禁，不等于语义无遗漏。

已采用新交付上下文、照做记录、补证或 followup 的库，须继续使用 RC.6 或更新的兼容实现。RC.5 及更早版本忽略这些新元数据与第五份交付文件，不得用它们继续写入、验证或重导出新库。回退应使用未采用新字段的冻结副本。

发行包从审核后的 Git 文件清单生成，配套每文件 SHA-256 的 `release-manifest.json` 与 `SHA256SUMS.txt`。原始外部录像、工作数据库、补证快照、宿主会话、个人路径及三个既有本地历史回执不入包；此前合成教程及已审查的项目试用材料继续保留。当前候选不提前声明 CI 或下载验收成功。

## English

RC.6 adds a readable operation checklist, reasoned issue closure, content-bound reproduction records, and a persistent `handoff.md` in the five-file export. Independent supplementary recordings retain their own source hashes, frame identities, export generations and attributed views. The followup author must actually view the locally archived image before referencing it. A followup preserves the original question and its limitations; it does not close source gaps or add coverage to the primary video. Archives remain fixed when the source directory changes, while damaged local snapshots fail integrity checks.

The new read-only queue prioritizes existing pending original-image requests by the original PTS of their represented frames, including requests whose exact-run representative lies outside the chosen window. Batch size controls one response, not total review scope. Register actual native views and request the queue again without an offset. Overview and crop views do not clear full-image requirements.

Two isolated pairs on one Inkscape recording measured scan times of 111.394 → 72.039 seconds and 116.336 → 74.069 seconds, reductions of 35.33% and 36.33%. All 18 fields of 1,903 frame rows, 394 segment proposals, and 573 requests/candidates were identical. The diagnostic pair is retained but excluded because it overlapped other computation. There were zero image-tool calls and image inputs in these measurements. These are machine-scan observations, not evidence of overall review time savings, reduced visual requirements, human reliability or semantic accuracy.

Schema 3, strict/layered gates and runtime dependencies remain. Ledgers using the new delivery or supplementary records require RC.6 or a later compatible implementation; RC.5 and earlier must not maintain or re-export them. This candidate note does not certify publication: final regression, commit-bound CI and downloaded-package acceptance are separate evidence. Earlier releases and historical results are retained.
