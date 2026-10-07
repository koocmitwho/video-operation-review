# 2026-10-07 本地优化与验收

> 本页及同名 JSON 保留实施轮结束时的本地冻结状态。用户随后另行授权发布；RC.5 的发行范围与核验方式见 [RC.5 说明](../references/release-rc5.md)。本页的“未发布”等字段不覆盖之后的发行状态。

本轮在 RC.4（`45ea1511021dc41937a7cdeddb2af8f06939f200`）基础上实施、测试并保存本地成果，没有提交、推送、打标签或发布。保留步骤纠错功能；唯一分组试验因未建立实际审阅负担收益而撤回。具体数字与运行文件身份见[结构化摘要](next-iteration-20261007.json)。

## 负担归因与分组决定

Inkscape 的 394 个建议段由首段与 393 个布局变化边界形成。393 次全都满足全局变化量条件；其中 145 次同时满足面积条件，248 次仅满足全局条件，面积独占为 0。291 个单帧建议均被紧邻的下一次触发截断。实际原图抽样可见构图移动、菜单悬停和列表滚动，不能把全部触发解释成缩放噪声。

三个受控例分别核对上下文概览、细小参数／取消／确认的原图职责，以及风险样本异常后按原范围展开。概览不替代原图，裁剪不充当全图候选完成，区间覆盖不表示逐帧看过。

唯一试验把连续单帧建议合成组，完整保留代表帧、请求行及底层状态：建议段 394→154，候选 585→585，原有人工区间仍为 7。另两个短例没有数量收益。试验未减轻原图要求或实际登记；实现已撤回，`vor_layers.py` 与 RC.4 字节相同。红绿日志和拒绝方案完整保存在项目外，没有继续叠加其他策略。

## 同库纠错

新增 `retire_steps`，必须给出理由、记录者和替代关系，显式处理所有活跃引用。原步骤、关联前后状态及相关历史区间版本保留。事务失败整批回滚；原图和查看记录不变；未解决疑点、替代步骤已有未知、异常展开及历史版本都不能借退休抹掉。退休历史绑定复核快照，旧结论不能复活；空退休历史仍使用旧快照字节。

正则实测在同一账本撤下片头静态步骤，补齐有效步骤的正则开关、大小写开关与匹配数前提。另一代理实际复核全部 38 帧和参数裁剪，再核对最终快照。最终 `valid=true`、`review_complete=true`，原 39 条查看不变，新增 39 条独立查看。这个结果不代表一般语义准确性。

使用退休功能的库须由支持该入口的版本维护；RC.4 不认识新退休历史，不能用于这些库的后续写入、验证或重导出。详见[记录契约](../references/records.md)和[调用示例](../references/examples.md)。

## 失败到通过与独立代码复核

新增 28 项产品回归。实现过程中独立复核发现并修复 8 项边界问题，包括疑点隐式关联丢失、旧快照复活、已有替代未知被覆盖、历史异常与同 ID 历史版本遗漏、归档完整性漏检及多条归档的变量遮蔽。最后 17 项独立检查和 18 种归档组合通过；首次失败及历次候选全部保留。

|本地环境|运行数|通过|跳过|耗时|
|---|---:|---:|---:|---:|
|Windows／Python 3.12.10|209|208|1|192.982 秒|
|Windows／Python 3.10.11|209|208|1|261.095 秒|

完整日志：[Python 3.12](tests-next-iteration-py312-20261007.log)、[Python 3.10](tests-next-iteration-py310-20261007.log)。唯一跳过项是非 Git 主目录无法执行的 Git 索引行尾检查；发布副本的文档检查另行核对。分发日志只规范为 UTF-8／LF，原始日志哈希与分发哈希均记录在结构化摘要。

## 三组新上下文配对

六次均使用同一正则问题账本与原视频、相同任务、GPT-6 Astra／ultra；每次全新上下文。任务是从已有审计问题到主审首次交付冻结，后续独立复核不属于计时终点。每组两代理并行、三组依次进行；六份首次结果全部冻结并重算哈希。

|组|RC.4 总历时|候选总历时|重建 RC.4→候选|本轮查看登记 RC.4→候选|
|---|---:|---:|---:|---:|
|1|678.51 秒|528.46 秒|1→0|78→39|
|2|543.54 秒|547.45 秒|1→0|78→39|
|3|624.02 秒|487.43 秒|1→0|78→39|

表格沿用各参与者 `metrics` 的计时截止点；哈希冻结的精确时刻另存，差异小于 0.3 秒，不混入分阶段耗时或用于选择有利结果。

六次都输入 38 张原图与 1 张裁剪、0 张概览，求助均为 0。六个宿主会话实际各返回 39 个图像输入，其图像字节哈希全部匹配冻结素材；宿主同时记录了相同模型与推理档位。它证明图像送达和素材身份，不证明模型理解正确。

RC.4 的第二次登记复用已看证据，不能计作额外看图。各次非预期工具／辅助脚本错误依次为 2、1、0、0、1、0；预期的自审未完成退出另计。部分 RC.4 交付还保留了将 JSON 显示转义当成原值错误的溯源误判，最终可复制参数正确；这些首结果不被改写，后验裁定单列过程错误。

独立后验审阅再次实际查看 38 帧及参数裁剪，核对六份当前记录与 70 个冻结文件：本任务范围内未发现最终关键操作错误或可见动作遗漏。R1A、R2A 保留了错误的原值归因；R1B 的同类假设已在冻结前撤回。R2B 未自行测量首次打开前的库字节哈希，组织者的预先输入清单和纠错前八张表逐行核对补充了身份证据，未发现历史记录丢失。图像送达、记录一致性、操作结果及这些过程错误分开解释。

候选稳定避免了本案例的重建与重复登记，总时间两组下降、一组上升，**未建立稳定省时**。分阶段计时有交叉登记和模型／工具／写作开销，保留原口径，不相加成纯模型耗时。六次 `valid=true`、`review_complete=false`，剩余为缺少独立复核；这个预先固定的主审终点不冒充完整门禁通过。

## 新来源与发布边界

另用不同作者的 CC BY 3.0、153.581 秒 [Python 完整编辑／运行录屏](../examples/open-cases/python-exception-20261007/README.md)。主审交付和另一代理仅按说明照做的首次结果冻结后才打开参考；两组真实 Python 输入的结果一致，最终独立视觉复核通过当前门禁。该例从已有完整脚本开始，不包括安装、新建文件或 Spyder 界面复现。

Inkscape 的 Q01 重启生效、Q02 录屏保存仍是来源缺口；585 个候选中 507 个仍缺原图要求的现场状态没有因本次优化被关闭。真人可靠性、泛化和语义零遗漏未建立。新改动没有对应的新提交远端矩阵或发行包下载验收，**完整发布条件尚未满足**。

## English summary

The local change adds reasoned, atomic step retirement/replacement with preserved evidence, history, unresolved issues, and stale review snapshots. Twenty-eight new product tests and an independent code recheck passed; both Windows Python suites ran 209 tests with 208 passes and one Git-checkout-only skip. The single grouping experiment was rejected: 394 proposals became 154, but all 585 candidates and original requests remained.

Three fresh-context pairs used the same seeded regex correction task. RC.4 rebuilt once per run and registered 78 view events; the candidate rebuilt zero times and registered 39. All six actually received the same 38 full images plus one crop, verified from host image outputs. Wall times were 678.51/528.46, 543.54/547.45, and 624.02/487.43 seconds (RC.4/candidate). Timing did not improve consistently. Frozen process mistakes remain disclosed; valid records and author-stage results are not semantic or human validation. A separate new-source Python case includes frozen delivery-only replay and independent visual acceptance. No commit, push, tag, or release was performed.
