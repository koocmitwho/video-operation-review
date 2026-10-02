# 0.1.0-rc.3

2026-10-02，第三个固定版本预发布候选。此候选包含审阅完整性修复，继续通过 prerelease 渠道提供受限试用。

## 本次变化

- 报告把能够关联到步骤或参数的审计冲突、确认/结果证据缺口显示为待核实，并保留原值、原登记状态和证据。未受影响的步骤不会仅因全局审阅未完成而被一并降级。
- 导入前校验步骤和疑点的非空 ID、同批唯一性及已知扩展字段结构；合法跨批 ID 更新保留。旧库坏记录返回字段诊断，导出在更新交付文件前拒绝。
- 导出先生成完整暂存文件组，再切换固定文件名，成功后提供 `export-manifest.json` 的代次、大小和 SHA-256。`export.pending.json` 存在时不得将文件组当作完整交付；需要保留暂存与备份，核对后处理。普通异常尝试回滚，不保证断电原子性，也不承诺自动恢复。
- 视频输入收窄到按实际内容识别的本地自包含 Matroska/WebM、AVI、MOV/MP4。播放列表、拼接清单、图像序列、外部引用及其他不支持格式会被拒绝，改扩展名不能绕过检查。SRT/VTT 和支持容器中的内嵌文本字幕继续可用。
- `--require-coverage` 只将完成度加入退出条件，不改变 `valid` 的记录完整性含义。导出清单、pending 和包含历史备份的暂存目录默认被 Git 忽略。

## 兼容与恢复边界

`VERSION` 和 `--version` 为 `0.1.0-rc.3`。数据库仍为 schema 3，保留旧有效记录、严格模式、固定报告链接和分阶段导出。旧导出没有清单时继续作为旧格式保留，不能倒推其已经过代次校验。

不支持的旧源文件也会被拒绝；若要继续，应保留原素材和旧证据，用明确来源的自包含媒体建立新工作目录，不直接改写旧源身份。输入格式允许不等于全部编码、高位深、动态分辨率或平台组合均已验证。

处理和记录契约详见 [处理方法](method.md)、[记录、校验及导出](records.md)。`valid=true`、完整文件清单或测试通过均不代表视频语义已经证明正确。

## 已有验证及待核对范围

2026-10-02 修复阶段，在隔离 Git 副本上使用 Windows / Python 3.12.10 和 3.10.11 各运行 181 项测试，均通过，无跳过；耗时分别为 163.798 秒和 214.210 秒。这些结果发生在本候选版本号更新前。脱敏摘要见 [fixes-20261002.json](../validation/fixes-20261002.json)；RC.3 发布候选重测和对应提交的 [CI](https://github.com/koocmitwho/video-operation-review/actions/workflows/tests.yml) 应分别核对，不以历史本地结果替代。

八份旧账本在隔离副本重验后仍全部 `valid=true`、`review_complete=false`；六个原始证据疑点没有关闭。公开 6 秒合成例完成 12 帧计算、9 候选、5 张本轮实际看图和阶段导出，保留 4 候选待看、3 个 partial 步骤与 1 个 open 疑点，四个交付文件的清单与代次一致。该试用是已知样例的内部一致性检查，不是独立人标、完整审阅或语义准确率。

一般语义准确率、真实用户逐步照做、长视频性能、macOS 实装和新的多语言/跨软件盲测均未由这次修复建立。以后的独立人工标注和候选新功能不包含在本次发行范围内。

## 安装与分发

使用完整技能 ZIP，核对同一预发布的 `release-manifest.json` 与 `SHA256SUMS.txt`，然后运行 `--version`、`doctor` 和授权短例。包外发布清单绑定提交与分发文件；工作目录里的 `export-manifest.json` 只绑定一代审阅交付，两者用途不同。

Python、NumPy、Pillow、FFmpeg/ffprobe 不随包分发。MIT 许可保留；包内媒体仅为项目自建合成示例。真实私有视频、截图、数据库、调用收据和个人路径不进入公开包。RC.1、RC.2 的标签和资产保留，不替换历史版本。

## English

This third prerelease contains review-integrity fixes. Reports mark locatable audit conflicts and evidence gaps on the affected steps or parameters while retaining original values and records. Step and issue imports reject invalid known structures and duplicate IDs within a batch; valid updates in later batches remain supported. Legacy malformed records receive field diagnostics and block export before delivered files change.

Exports retain the four fixed delivery filenames and add an `export-manifest.json` generation with file sizes and SHA-256 hashes. Consumers must reject a group while `export.pending.json` exists and preserve its staging and previous-generation backups for inspection. Ordinary exceptions attempt rollback; cross-file power-loss atomicity and automatic recovery are not guaranteed.

Video input is now restricted to recognizable local, self-contained Matroska/WebM, AVI, and MOV/MP4. Playlists, concatenation manifests, image sequences, external references, and other unsupported formats are rejected, including renamed manifests. SRT/VTT and embedded text subtitles in supported containers remain available. Existing sources must meet the same boundary; use a new work directory for a separately prepared self-contained source rather than rewriting old evidence identity.

The version becomes `0.1.0-rc.3`; schema 3, valid legacy records, strict mode, fixed links, and staged delivery remain. The prior repair-stage Windows/Python 3.12.10 and 3.10.11 suites each passed 181 tests without skips, in 163.798 and 214.210 seconds. These measurements precede the version update and do not establish the candidate's later test or remote CI results.

All eight isolated legacy ledgers remain valid but incomplete, and the six original evidence gaps remain unresolved. The known public synthetic sample had five fresh image views and a verified four-file export generation; it is not independent human ground truth or a measure of general semantic accuracy. Independent user reproduction, long-video performance, additional platform combinations, and new cross-language or cross-application blind evaluation remain unverified.

Install the complete skill ZIP with its commit-bound release manifest and checksums, then check the version and processing environment. The release manifest is distinct from a review directory's export manifest. Runtime dependencies and private media are excluded; the project MIT license and authored synthetic example remain. Prior release tags and assets are preserved.
