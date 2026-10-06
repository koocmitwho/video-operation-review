# 0.1.0-rc.4

2026-10-06，公开案例验证与可移植试用材料更新，继续采用 prerelease。

## 范围

- 新增[公开案例入口](../examples/open-cases/README.md)、固定来源/许可/哈希、三个录屏的当前验证状态。
- 新增[独立试用材料](../examples/open-cases/trial/README.md)：参与者材料、空白结果表和组织者答案分开，修正本地材料的路径引用。
- 收录[新上下文代理试用摘要](../examples/open-cases/trial-observed/summary.json)及实际界面截图，区分原冻结记录与公开脱敏转录。
- 更新版本标识与中英文说明。生产脚本逻辑、schema 3、依赖、媒体输入规则和审阅门禁不变；RC.1–RC.3标签与资产保留。

## 证据边界

本次被收录的视觉试验使用RC.3。两个VS Code交付均在真实网页编辑器中复现；新上下文代理未获预期答案，第一次实际输出冻结后核验通过，仅CRLF/LF不同。21秒是任务阶段历时，96秒是准备阶段；没有单独计量主动/等待时间，不包含停止后取证、清理和核验。浏览器不是清空配置的全新资料，正则选项开始时已开启。

Inkscape保留Q01重启生效、Q02录屏保存缺口，`valid=true`、`review_complete=false`。585候选都有至少概览或原图登记，其中507个未达原图级要求。记录中的区间覆盖、图片查看粒度和语义正确性不得互相替代。

公开可移植说明属于发布时修订，未重新进行该修订字节的UI试用；历史试用不得被称作它的直接验收。工程回归、打包安装与对应提交的[CI](https://github.com/koocmitwho/video-operation-review/actions/workflows/tests.yml)另行核对。没有独立真人金标准、真人试用结果、总体省时结论或跨软件泛化保证。

## 分发

完整技能ZIP配套`release-manifest.json`及`SHA256SUMS.txt`。包外发行清单绑定提交与文件，工作目录的`export-manifest.json`只绑定一代审阅交付。原第三方录屏、网页快照、数据库、会话日志及个人路径不入包；固定下载链接和哈希在`sources.json`。来源归属见[第三方声明](../examples/open-cases/THIRD_PARTY_NOTICES.md)。

## English

This prerelease publishes source-qualified summaries for three external recordings, a portable participant/organizer trial pack, and a redacted record of one fresh-context agent replay. Runtime logic, schema 3, dependencies, input rules, and review gates are unchanged. Earlier tags and assets remain available.

The visual trials used RC.3. The subsequent agent received no expected answer before freezing its first output; the editor-buffer content matched except for CRLF/LF. The measured phases were 21 seconds for the task and 96 seconds for preparation, excluding later capture, freezing, cleanup, and verification. Active and waiting time were not separated; the browser was not a new profile and regex was already enabled. These numbers do not establish time savings.

The Inkscape ledger is valid but incomplete: all 585 candidates have an overview or native view, but 507 lack native-level viewing; restart application and recording-save outcomes remain unknown. Overview coverage is not native coverage or semantic proof. No independent human ground truth, human acceptance, general semantic accuracy, or cross-software reliability is claimed.

The public trial instructions are a portable publication revision with corrected references; their exact bytes have not undergone a new UI trial. RC.4 packaging, installation, and regression checks are separate from the historical visual experiments. Source videos, databases, raw sessions, and personal paths are excluded; attribution and pinned media hashes accompany the source links.
