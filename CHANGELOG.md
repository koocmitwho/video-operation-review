# 版本记录

## 0.1.0-rc.1 — 2026-09-30–2026-10-01

首个固定版本候选，采用 GitHub prerelease 渠道。冻结与发布验收分别记录，见 [发布审核](validation/release-audit-20261001.md)。

- `--require-coverage` 保留 `valid` 的记录完整性含义，门禁失败写入 `coverage_errors`；未完成时仍退出 1。
- 已关联未解决疑点的区间不计入完成精审；报告标题展示其待核实状态，原步骤登记与历史保留。
- 恢复数据库与证据后抽图会创建日志目录；滤镜文件写入失败正确结束 attempt。
- 增加 `VERSION` 与无第三方依赖可用的 `--version`，候选身份为 `0.1.0-rc.1`。
- 规范帧号、PTS、可见范围、临时输入、确认与结果的核对表；自动答案不作为独立人工标准。

数据库保持 schema 3，旧严格模式及旧记录继续支持。调用者如曾用 `valid` 判断 `--require-coverage` 是否通过，应改用退出码与 `review_complete`。见 [候选说明](references/release-candidate.md)。
