# 0.1.0-rc.2

2026-10-01，第二个固定版本预发布候选。本次交付是在已发布0.1.0-rc.1之后，经用户审阅并授权发布的证据整理与说明更新。

## 内容与兼容性

- 收录[记录修复复核](rc1-repair.md)的脱敏摘要、项目外验收整理脚本的最小补丁和四项可选回归。补丁处理观察值被null覆盖、相同补查重复追加，以及数值、确认文字和标题之间的矛盾。完整私有脚本和真实账本不随包分发；可选测试需显式提供有权使用的本地夹具及隔离脚本。
- `VERSION`和`--version`更新为0.1.0-rc.2。生产CLI实现、schema 3、依赖范围及审阅门禁保持不变。
- 六个原始证据疑点与八份未完成审阅保留。一个38秒片段的七项AI草稿得到用户确认，限定为该片段的人工核对；不表示盲标注、稳定版或一般语义准确率验收通过。

## 安装与验证

安装完整技能ZIP，核对同一[预发布](https://github.com/koocmitwho/video-operation-review/releases/tag/v0.1.0-rc.2)内的`release-manifest.json`和`SHA256SUMS.txt`，再运行`--version`与`doctor`。清单绑定发布提交和每个分发文件的SHA-256；解释器、依赖与FFmpeg不打包。

发布检查重新运行Windows/Python3.10与3.12完整测试，以及单列的四项私有账本整理回归。远端Ubuntu/Windows × Python3.10/3.12结果以该发布提交对应的[CI](https://github.com/koocmitwho/video-operation-review/actions/workflows/tests.yml)为准；历史本地测试不代替新的远端结果。发布资产下载后重新核对清单，并在独立目录运行自建样例流程。

MIT许可保留。媒体分发仅限项目自建合成示例；真实录屏、截图、数据库、会话收据和个人路径留本地。旧`v0.1.0-rc.1`标签和资产保留，继续通过prerelease渠道提供受限试用。

## English

This second prerelease contains the sanitized evidence review, a minimal patch for the private acceptance consolidation script, and four optional regressions. It addresses lost observations on replay, repeated investigations, and inconsistent uncertainty in record prose. The complete private script and real ledgers are excluded; optional tests require explicitly supplied, authorized local fixtures and an isolated script.

The version becomes 0.1.0-rc.2; production CLI implementation, schema 3, dependency ranges and review gates are unchanged. Six original evidence gaps and eight incomplete reviews remain. A user confirmed seven AI-drafted claims for one 38-second clip, which does not establish blind annotation or general semantic accuracy.

Use the complete skill ZIP with its commit-bound manifest and SHA256SUMS, then check `--version` and `doctor`. Publication checks rerun both local Python suites and the separate private regressions; consult the commit-specific CI for the remote matrix. Downloaded assets are rechecked and installed in an independent directory. MIT and authored synthetic media are retained; private media, ledgers and paths are excluded. The previous tag and assets are preserved, and this release remains a prerelease.
