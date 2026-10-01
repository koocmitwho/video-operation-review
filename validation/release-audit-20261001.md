# 0.1.0-rc.1 发布审核（2026-10-01 UTC）

结论：有条件接受为 GitHub RC 预发布；对应提交与标签的远端 CI 全部通过后才发布。不能按稳定版或语义验收完成发布。

本次在冻结候选基础上审核实际实现、回归用例、安装、许可与分发内容，未修改生产代码。新增记录与文档澄清单独纳入发布。历史冻结摘要继续保留当时的未提交、未发布状态；当前发布事实以标签、GitHub Release 与对应工作流为准。

## 新验收

- Windows / Python 3.12.10：152 项通过、0 跳过、0 失败，112.009 秒；[完整日志](tests-release-audit-python312.log)。
- Windows / Python 3.10.11：152 项通过、0 跳过、0 失败，153.726 秒；[完整日志](tests-release-audit-python310.log)。两套并行执行，时间不相加。
- 冻结候选 85 个文件在主开发目录和 Git 副本中均与清单 SHA-256 一致。ZIP 的全部成员逐项核对，未发现多余、重复、路径逃逸或链接条目。
- 冻结 ZIP 解压到全新目录，从无关工作目录使用绝对脚本路径运行。无第三方依赖的 help/version、doctor、12 帧自建视频的 scan/plan/candidates/extract/validate/export 均通过。覆盖未完成时 valid=true、review_complete=false，require-coverage 退出 1。
- 实际打开合成证据帧 5、8、10：取消后仍为 1，应用后为 5，编辑器中的 SUCCESS 与可见运行错误分开。doctor 不冒称宿主视觉验收已完成。

## 审核范围与边界

实现与回归覆盖 valid/coverage_errors/退出码、疑点关联后的精审计数和报告提示、恢复抽图日志目录、失败 attempt 收尾，以及固定 VERSION。数据库仍为 schema 3。未发现需要额外修补的阻断代码问题。

原 6 个疑点全部尚未关闭；8 份记录有效但完整审阅均未通过。没有独立人工标注、用户在实际软件内照做验收、长视频性能或 token 实测。本次安装 smoke 没有制造看图登记或替这些疑点补结论。现有 Python 依赖与 FFmpeg 被复用；不声称在全新机器离线安装了运行时或完成模型兼容性认证。

分发保留 MIT 许可。视频与九张截图由项目自建生成；检查图像及生成脚本，未加入第三方真实录屏、工作数据库或原始会话。候选文本扫描与命中人工检查未发现凭据或实际个人路径；通用 Windows 路径例子和测试夹具不是用户私有路径。之前执行受阻的本地报告继续保留，因其路径和过时结论不纳入提交或 ZIP。

## 发布核验

发布包从最终 Git 提交导出，包外清单绑定版本、提交、每个文件 SHA-256 和 ZIP SHA-256；下载后重新核对并从全新目录验证安装。GitHub Release 必须为 prerelease。远端 [测试工作流](https://github.com/koocmitwho/video-operation-review/actions/workflows/tests.yml) 的 Ubuntu/Windows 与 Python 3.10/3.12 矩阵需检查至终态。最终发布收据另记实际提交、标签、CI、资产与下载核验结果。

机器摘要见 [release-audit-20261001.json](release-audit-20261001.json)，冻结历史见 [rc-20260930.json](rc-20260930.json)，范围见 [候选说明](../references/release-candidate.md)。
