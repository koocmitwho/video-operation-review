# 0.1.0-rc.5

2026-10-07，步骤记录纠错与新上下文验收，继续采用 prerelease。RC.1–RC.4 的标签和资产保留。

## 本次变化

- 增加 `retire_steps`：用理由、记录者与替代关系纠正误设步骤，保留原记录、关联前后状态及相关历史区间的每个版本。
- 同一导入事务处理更正；非法引用或未知丢失整批回滚。原证据和查看事件不变，未解决疑点、替代步骤已有未知以及异常展开要求不能借退休抹掉。
- 退休历史绑定复核快照，阻止旧结论复活；归档继续参与完整性检查，报告附纠错追溯。无退休历史的库保留旧快照字节。
- 补充三组已知开发案例纠错配对与不同来源的完整 Python 编辑／运行案例摘要。来源及许可见[第三方声明](../examples/open-cases/THIRD_PARTY_NOTICES.md)。

接口见[记录契约](records.md)与[示例](examples.md)。`valid` 仍表示来源、证据与记录完整性，`review_complete` 仍要求候选与当前模式复核门禁；旧严格模式和依赖不变。

## 兼容与未纳入内容

数据库仍是 schema 3，通过增量表保存退休历史。未使用退休功能的旧记录继续支持；已使用该功能的库须由 RC.5 或更新的兼容工具维护。RC.4 会忽略新退休历史，不得用它继续写入、验证或重导出这些库。

唯一分组试验将 Inkscape 建议段 394→154，但 585 个候选与全部请求不变，没有原图或登记收益，已撤回。发行版的 `vor_layers.py` 与 RC.4 字节一致；没有引入 OCR、ASR、云服务或新的运行依赖。

## 验证与结论范围

实施轮新增 28 项产品回归，独立复核修复 8 项开发中发现的边界问题。历史本地全套各 209 项运行、208 项通过、1 项 Git 检出专用检查跳过；此次发行的本地重测、对应提交远端矩阵及下载安装验收独立留存，不能用历史数量代替。详细实验见[本地冻结验收](../validation/next-iteration-20261007.md)；当前 tag 对应的 [CI](https://github.com/koocmitwho/video-operation-review/actions/workflows/tests.yml) 与发行清单绑定具体提交。

三组同任务、同模型的新上下文代理纠错对照中，RC.4 每次重建一次、登记 78 次，候选均在同库完成、登记 39 次。各次实际输入均为 38 张原图加一张裁剪。总历时两组下降、一组上升，没有稳定省时结论；两份 RC.4 首交付的转义归因错误保留并单列。配对终点是主审冻结，仍为 `self_review`，不能说成每份都通过独立门禁。

新来源录屏从完整可见的既有脚本开始，首次交付与另一代理仅按说明运行的结果先冻结，之后才核验参考；独立视觉复核通过当前门禁。Python 命令行两次运行不证明 Spyder 原生界面复现，安装、新建、明确保存与旁白未验证。参考不是独立真人金标准。

Inkscape Q01 重启生效、Q02 录屏保存仍是来源缺口，507 个候选仍缺原图要求。概览不是原图，区间覆盖不是逐帧看过，检查通过不证明语义零遗漏；没有真人可靠性、总体省时或跨软件泛化保证。

## 分发与身份

完整技能 ZIP 配套 `release-manifest.json` 与 `SHA256SUMS.txt`。发行清单绑定 tag、提交及每个分发文件的 SHA-256；工作目录的 `export-manifest.json` 只绑定一次审阅导出，不替代发行清单。

包内容按审核后的 Git 文件清单生成。三个既有本地历史回执、原始外部视频、审阅数据库、会话日志、工具截图与个人路径不入包。已有合成教程及此前经许可检查的项目试用截图保留。下载后须核对 ZIP/清单哈希、逐文件身份、版本和实际处理流程。

## English

RC.5 adds reasoned, atomic retirement/replacement of mistaken steps within the same ledger. Original records, all relevant historical interval versions, evidence, viewing events, and unresolved issues remain inspectable. Retirement history makes prior review snapshots stale, and archived evidence remains subject to integrity checks. Existing strict-mode and completion criteria, schema number 3, and runtime dependencies remain unchanged. Ledgers with retirement history require RC.5 or a later compatible implementation; RC.4 must not be used to maintain or re-export them.

The single grouping experiment was rejected and reverted: fewer proposal headers did not reduce the 585 candidate requirements. Three fresh-context agent pairs avoided reconstruction with the new entry point, but wall time did not improve consistently. Their endpoint was author delivery with self-review, not completed independent review. Frozen process attribution errors remain disclosed.

A separate source-qualified Python recording passed delivery-only replay and independent visual checks. It begins with an existing visible script; Python CLI execution is not native Spyder UI reproduction. Installation, file creation, explicit saving, narration, human reliability, semantic-zero-omissions, and generalization are not established. Inkscape restart/save gaps remain open.

Release-specific local regression, commit-bound CI, and downloaded-install acceptance are separate from the dated development evidence. The ZIP, file manifest, and checksum file identify the audited distribution. Raw media, review databases, host sessions, personal paths, and the three pre-existing local-only publication receipts are excluded; earlier tags and assets are retained.
