# 0.1.0-rc.1 本地修复复核 / Local repair review

基线为已发布提交 `482a0da520b717974352b9c9d9778261ac316103`。本页记录发布前的独立分支复核：该阶段未提交、推送、打标签或替换发布资产，版本仍为0.1.0-rc.1。随后获准的0.1.0-rc.2发布单独见 [RC.2说明](release-rc2.md)；本页历史测试与验收边界不随发布改变。

## 有证据的修复

缺陷位于上一轮项目外的验收整理脚本。两次实际重放复现：最终值置为 null 后，第二次整理又把它覆盖到观察值；补查内容重复追加；加载行数已为 unknown，确认/结果文字仍断言整数。另一个区间标题也仍断言提交完成。生产 CLI 按 ID 保存收到的内容，没有证据把这些问题归因为识别程序。

最小修复保存已存在的观察值、阻止相同补查再次追加，并同步不确定性的叙述。原始历史与已经存在的重复项不删除；受损的五项窗口观察值经本轮看图后仅在副本恢复，最终生效值仍为 null。补丁见 [finalize_reviews.patch](../validation/rc1-repair/finalize_reviews.patch)，可选实际账本回归见 [test_consolidation.py](../validation/rc1-repair/test_consolidation.py)。补丁采用无上下文格式，使用 `git apply --unidiff-zero` 应用到已设置显式环境路径的隔离脚本副本。该测试必须显式提供有权使用的本地资料及整理脚本，不纳入默认公开夹具测试，也不包含真实视频。

## 验收范围

八份记录重新校验后均 valid=true、review_complete=false。六个原疑点涉及局部种子、网格确认、工作簿保存、文件版本交接、实际执行和输出目录，均仍缺证据。不能通过承认材料不足就关闭门禁。

用户明确确认了一段38秒真实录屏的H01-H07草稿，形成四操作单元的有限语义核对基准。它是人工确认的AI草稿，不是独立盲标注；仅评估草稿明确列出的主张。其他真实片段的AI观察、项目自建合成测试和人工确认结果分别报告。精确鼠标按下时刻、该片段没有的取消动作、软件内照做、长片性能和一般化准确率未评估。

完整本地证据（视频、图像、账本、人工确认回执及源帧映射）留在项目外；分发仅包含脱敏摘要、代码补丁和可选测试。公开验收摘要见 [rc1-repair.json](../validation/rc1-repair.json)。MIT许可和原有Python/FFmpeg支持范围不变；该本地复核阶段未运行新的远端CI，也未验证新的平台组合。继续保留RC。

## English

This page records the pre-publication local review starting from published commit `482a0da`. During that review, the production CLI, version, schema and review gates were unchanged. The subsequently authorized RC.2 publication is documented separately in the RC.2 notes. The reproduced defects belong to the private acceptance consolidation script: repeating it overwrote observed values with null, appended identical investigations, and retained definite numerical claims after the structured value became unknown. A stale interval title also asserted confirmation. The minimal patch preserves observations and history, avoids new duplicate attempts, and aligns uncertainty in the prose. Five damaged observations were restored only in copies using fresh image review; effective values remain unknown.

All eight records were revalidated and remain valid but incomplete; none of the six original evidence gaps is closed. The user confirmed seven draft claims for one real 38-second clip, covering four operation units. This is human adjudication of an AI draft, not blind annotation or evidence of general accuracy. AI-only checks and synthetic regression results remain separate. Exact click timing, absent cancellation examples, in-software reproduction, long-video performance and additional platforms are not evaluated. Private media and ledgers are excluded from distribution. No new remote CI or release was performed during that local review; RC status remains appropriate. Apply the zero-context patch with `git apply --unidiff-zero` to an isolated script copy that uses explicit environment paths. See the linked summary, minimal patch and optional local regression above.
