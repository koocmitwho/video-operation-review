# 处理方法、参数与恢复

本文说明源文件身份、时间索引、选帧、缓存和进程生命周期。

## 索引与源身份

`scan` 绑定本地视频的绝对路径、字节数和 SHA-256。使用第一个视频流 `v:0`，保存容器元数据和逐帧信息：0 起始呈现顺序帧号、原始整数 PTS、PTS 秒、best-effort 时间、尺寸、帧时长及编码关键帧标志。

视频入口仅支持本地自包含的 Matroska/WebM、AVI、MOV/MP4。程序按文件内容识别容器；MOV/MP4 还检查内部引用和容器结构。播放列表、ffconcat 等拼接清单、图像序列及其他格式不受支持，即使改成 `.mkv` 或 `.mp4` 扩展名也不会放行。MOV/MP4 的外部数据引用、压缩或引用电影、独立媒体分片及图像项依赖同样拒绝。此边界使源文件本身的字节能够代表受支持的媒体来源，不承诺所有这些容器变体都可读。

读取媒体的 ffprobe/FFmpeg 调用只允许本地 file 协议及已识别容器对应的解复用器，不读取清单所指向的其他素材。新扫描的输入策略拒绝返回 `unsupported_media_input`，保留 failed 的 `input_policy` attempt 与日志；旧库校验的来源拒绝使用 `source_unsupported_media_input`。已有库不能凭旧索引绕过检查，程序不自动转换源文件或改写旧源身份。SRT/VTT 独立字幕和受支持容器内的文本字幕继续使用同一入口限制；外部转写 JSON 仍按 [语言接口](language.md) 导入。高位深、动态分辨率和多视频流的支持范围不因此扩大。

`validate` 与 `export` 核对源路径和内容身份。源文件缺失返回 `source_missing`，SHA-256 变化返回 `source_hash_mismatch`，均计入 `errors`。源文件大小、纳秒时间、设备和文件标识一致时复用扫描哈希；Windows 还比较文件变更时间。属性变化或旧库缺少属性缓存时重新读取 SHA-256，读取前后核对属性。

`source_verification.rehashed` 记录本次是否重算；`method` 为 `sha256_recomputed` 或 `cached_sha256_stat_match`。`validate --rehash-source` 和 `export --rehash-source` 可显式重算完整文件哈希。哈希缓存单独存入 meta，保持原有 source 身份与复核快照稳定。

时间优先使用原始 PTS，其次使用标注来源的 best-effort；缺失时间保存为 null。缺失、重复及倒退分别计数。`focus` 和 `candidates --start/--end` 接收原始时间，VFR 也按索引时间定位。

完整且干净结束的 ffprobe 索引提供 `video_total_frames`，口径为可解码呈现帧。容器声明数另列；`container_frame_count_mismatch` 报告两种已知计数的差异。计算范围、已索引前缀、待处理尾部和解码日志分别保留，便于检查源包和 PTS。

## 顺序解码与变化计算

FFmpeg 使用 `-noautorotate`、`-copyts`、`-fps_mode passthrough`，通过 PPM 管道输出原尺寸 RGB24。内存中保留相邻图像与差分矩阵，每帧写入 SQLite 指标，证据 PNG 按需抽取。

- **精确重复**：宽高与完整 RGB24 内容的 SHA-256 相同且连续，使用同一 `exact_start`。
- **整体变化**：逐像素取三个通道绝对差的最大值，再求全图平均。
- **局部变化**：全分辨率方块平均差，保存最大值及对应矩形；`--tile-size` 默认 32 像素，边缘按实际面积归一。
- **变化像素**：差值达到 `--pixel-threshold` 的像素数及比例，默认阈值 8。
- **尺寸变化**：记录变化边界，并核对实际解码尺寸、索引尺寸和帧数。

完整逐帧索引和精确状态持续保留。变化指标用于定位画面，操作含义由审阅者通过原图、局部裁剪和前后状态判断。

## 选帧与证据

`select --mode layered` 使用 `plan` 的分段参数：`max_span=15.0`、`layout_fraction=0.12`、`stable_seconds=0.75`。分层参数写入 `selection_config`，可从 `plan --max-span` 调整上下文时长。分层 select 接收旧阈值的默认值以兼容调用；显式修改这些阈值时返回参数错误，并提示使用 coverage/changes。

`--mode coverage` 保留每个不同连续 RGB 状态；`--mode changes` 使用 `--anchor-seconds`、`--global-threshold`、`--local-threshold`、`--min-changed-pixels`、`--context-frames` 初筛。二者使用 strict 审计模式。

重选替换自动选择原因，保留 focus/audit 补查请求、查看记录、步骤和证据。模式、参数与历史均落库。人工近似合并保存区间归属和原始状态映射。

`extract` 按源帧顺序输出并核对扫描时的完整 RGB 哈希；`crop` 保存父图、坐标与源帧号。证据文件的 SHA-256 用于后续完整性检查。查看数量来自 `record-view` / `record-sheet-view` 的登记。

大量不连续候选使用平衡的 FFmpeg 选帧表达式，连续帧压缩为区间。滤镜写入文件：有 `-filter_script:v` 时使用旧接口，否则使用 `-/filter:v`。提前 EOF 分别报告退出/日志错误、目标帧缺失或像素不匹配，保留完成的证据前缀。语法见 [FFmpeg Options](https://ffmpeg.org/ffmpeg.html#Options)。

## 超时、恢复与预算

外部程序探测默认 30 秒；完整帧索引按连续无输出 120 秒计时，每次收到帧数据更新计时。解码使用连续无输出 24 小时的宽松超时，字幕解析使用 24 小时上限。管道读取由看护线程覆盖，等待退出也带超时；超时结束进程，将 attempt 收尾为 failed，错误包含 `helper_timeout`，CLI 同时返回 `code`。

每个审阅目录由一个写入命令操作，数据库事务保存完整记录。`--checkpoint-frames` 默认 100，控制索引/计算的进度提交频率。异常和 Ctrl+C 保存已提交范围并结束 attempt；系统强制终止留下的 `running_or_unfinalized` 供恢复时检查。`status` 以库内记录计算范围。

数据库 schema 保持 3，v1/v2 增量迁移保留步骤、查看及复核记录。新库默认 layered；旧库运行 plan 后启用 layered。重新计划保留人工区间。

同源同参数 scan 复用完整索引与指标。中断恢复从头顺序回放并核对已缓存前缀，新增帧才计算差分；`attempts.decoded_frames` 与 `new_frames` 分列。计算参数或 FFmpeg 版本变化时使用新的审阅目录。

`--max-new-frames` 设置本次新增计算预算。恰好到索引末帧时继续读取 EOF，核对退出码和错误日志后标记完成。局部补查依据疑点和原始时间范围执行；在 issue.attempts 中记录新增证据与结论，按实际进展安排后续材料或复查。

## 校验与导出

`valid` 表示源文件、证据与记录完整性；`review_complete` 要求全帧计算完成、候选选择及查看完成，并通过当前模式复核门禁。默认 validate 按 valid 返回 0/1；`--require-coverage` 将完整审阅条件加入退出条件，不改变 valid 的含义：有效但尚未完成的记录仍返回 `valid=true`、`review_complete=false`，退出码为 1，未完成原因写入 `coverage_errors`。export 保留当前验证结果并输出可继续完善的报告。

导出先在本工作目录的独立暂存目录生成全部文件，再切换固定文件名，最后写出完整代次清单。消费者必须同时检查 pending 标记和清单中的文件摘要；不能仅凭 `report.md` 存在认定交付完整。渲染失败不更新旧交付，普通切换异常尝试回滚；回滚失败或切换中断需要保留现场并人工核对，不承诺断电原子性或自动恢复。具体文件、字段及旧格式兼容规则见 [记录契约](records.md)。

技术参考：[FFmpeg](https://ffmpeg.org/ffmpeg.html)、[ffprobe](https://ffmpeg.org/ffprobe.html)。
