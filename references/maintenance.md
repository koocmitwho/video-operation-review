# 开发来源与发布检查

主开发目录为 video-operation-review，video-operation-review-github 为本机 Git 发布副本。其他机器可直接使用 Git checkout。脚本、测试和中英文说明在选定的主目录修改，再核对同步到发布副本。

## 维护次序

1. 检查两份目录状态，保留改前快照；逐项合并现有差异。
2. 在主目录新增失败用例，再修改实现；运行 `python -X utf8 -m unittest discover -s scripts/tests -v`。
3. 更新中文说明，再同步英文。验证结果写明日期、环境、素材、命令和实测值。
4. 同步核对过的交付文件，保留目标 .git 和已有工作。输入视频、工作数据库、会话日志与含个人路径的记录保存到项目外。
5. 按字节 SHA-256 比较交付文件：

```text
python scripts/check_release.py --target ../video-operation-review-github
```

可用 --source 指定主目录。退出码 0 为一致，1 列出修改/缺失/多余文件，2 为路径或枚举错误。检查器忽略 .git、Python 缓存和虚拟环境，其他文件逐项核对；路径链接及读取问题显示为错误。

## 文档与安装验收

test_docs.py 纳入 unittest discovery，检查 Markdown 相对链接、从 SKILL.md 到参考文档的可达性、中英文 README 标题层级和代码块数量、参数字面、验证日志、技能元数据、许可与产物忽略规则。frontmatter.name 与 README 所载安装目录名对应；行尾检查使用 Git 索引，非 Git 检出时跳过该项。

本项目采用 [MIT 许可](../LICENSE)，标准文本来源为 [Open Source Initiative](https://opensource.org/license/mit)。

## 2026-09-27 行尾规范化

新增 .gitattributes，文本统一 LF，图片采用 binary。此次规范化包括已有混合行尾文件及历史测试日志，日志中的用例、状态和耗时保持原值。61 项历史日志改名为 script-tests-20260924.log，98 项基线另存 tests-98.log。

check_release.py 按字节计算哈希，因此行尾调整会显示 changed。同步两份目录的规范化文本后再运行核对。Git 分支保留本轮可审阅改动。

## CI 环境

矩阵使用 Ubuntu 24.04 / Windows 2022 与 Python 3.10 / 3.12。Ubuntu 固定 [ffmpeg 7:6.1.1-3ubuntu5](https://packages.ubuntu.com/noble/ffmpeg)，Windows 固定 [ffmpeg 8.1.2](https://community.chocolatey.org/packages/ffmpeg/8.1.2)；安装后打印 ffmpeg/ffprobe 版本，再运行 doctor 和完整 unittest。远端结果按对应提交的工作流记录查阅。

本地运行和远端 CI 分别留存，日期明确的历史结果持续保留。发布和提交按维护者的当前授权执行。

固定版本从 [VERSION](../VERSION) 读取；`python scripts/review_video.py --version` 可在无第三方依赖时检查候选身份。当前候选的范围见 [RC.5 说明](release-rc5.md)，此前材料见 [RC.4 说明](release-rc4.md)，此前运行逻辑的兼容边界见 [RC.3 说明](release-rc3.md)，首个候选的历史交付见 [候选说明](release-candidate.md)。
