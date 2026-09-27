# 分层审阅验收设计

目标：全帧索引、全时间线粗审、操作精审、抽查和当前内容复核形成可回查记录，严格逐 RGB 状态模式继续保留。

架构：vor_layers.py 管理建议、人工区间、抽查及快照；vor_language.py 使用 FFmpeg 读取字幕并接收带时间基准的转写 JSON；宿主视觉负责操作判断。数据使用 SQLite，处理依赖为 Python 3.10+、NumPy、Pillow、FFmpeg/ffprobe。

## 可观察案例

| 案例 | 验收结果 |
|---|---|
| 等待、鼠标、闪烁 | 完整索引和状态映射保留，建议代表与实际查看登记分列 |
| 单帧菜单、局部编辑 | 原帧和变化指标可回查，风险样本可定位 |
| 区间孔洞/重叠 | 列出具体区间错误和补查帧 |
| 粗审与精审 | context 按粗审和抽查统计，操作区间按角色证据统计 |
| 取消与重输 | 临时 0.20、取消后 1.00、最终应用 0.02 分开记录 |
| 文件交接 | 共享 file: 状态键检查跨步骤输入/输出连续性 |
| 抽查过期或异常 | scope_hash 绑定内容，expand 后穷尽原范围并关联 resolves |
| 查看粒度 | 原图/裁剪/拼图按源帧去重，native/overview 各自统计 |
| 时间对齐 | VFR、非零起点按原始 PTS，缺失时间保留来源状态 |
| 字幕与转写 | SRT/VTT/内嵌文本、原文/译文、偏移与重叠分别保存 |
| 源文件变化 | missing/hash_mismatch 进入 validation.errors，部分导出保留结果 |
| 分层参数 | 旧阈值使用默认值，分段参数落库；非默认旧阈值提示 coverage/changes |
| 查看引用 | 图片文件名/资产自身引用返回错误，消息/调用引用写入 views |
| 外部超时 | 挂起程序结束，attempt=failed，错误为 helper_timeout |
| 审阅完成度 | 候选与当前门禁均完成时 review_complete=true |
| 旧库与严格模式 | 增量迁移保留旧记录，显式 coverage/strict 继续回归 |

## 维护顺序

1. 用可控夹具新增失败用例并保存日志。
2. 修改对应模块，跑定向用例及完整 unittest。
3. 核对公开 CLI、JSON 字段和 schema 3 的兼容性。
4. 用实际图片工具执行合成 GUI 端到端，保存调用引用与导出结果。
5. 对同一素材按同一环境测量耗时与内存，分别记录本地和远端结果。

关键状态定义见 [layered-trial-truth.json](../validation/layered-trial-truth.json)，历史严格契约见 [acceptance.md](acceptance.md)，实测与日志见 [validation.md](validation.md)。
