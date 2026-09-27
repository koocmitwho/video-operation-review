# 模型与图像适配

本技能使用支持图像输入的模型，通过宿主图片工具查看证据。沿用用户选择的模型和推理档位，按画面清晰度、上下文容量和可用工具组织审阅。英文说明见 [models.en.md](models.en.md)。

## 优化基准

2026-09-25 的适配基准用于决定证据呈现方式：

| 宿主 | 基准 | 证据组织 |
|---|---|---|
| Codex | GPT-6 Astra / Sol / Luna | 围绕操作目标与前后状态提供证据，详细命令按需读取 |
| DeepSeek Harness | DeepSeek-V4.1-Flash，API 名 `deepseek-flash` | 同时核对路由的图像能力与实际送入模型的图片尺寸 |

参考：[OpenAI 模型目录](https://developers.openai.com/api/docs/models)、[GPT-6 技能建议](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)、[DeepSeek 更新日志](https://api-docs.deepseek.com/updates/)、[视觉接口](https://api-docs.deepseek.com/guides/vision/)。

## 开始前检查

记录当前模型/路由、图片工具和本地命令工具。实际打开本轮一张证据，检查内容是否可读。DeepSeek 的模型别名、路由能力目录和实际图片结果分别核对；模型兼容依据实际图像输入和工具能力。

## 图片呈现

先用全画面定位对象，再对照操作前、编辑中、确认后和结果。拼图用于粗审，最终值、单位与勾选状态使用单张原图或局部裁剪。每批附带当前问题所需的证据。

已检查的 DSH `dsh-llm-deepseek` 0.1.5-rc.3 默认单图像素预算为 640,000，可用 `imagePixelBudget` 调整。以实际返回尺寸、历史图片状态和服务端 usage 记录当前结果。接口见 [适配器说明](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/llm/llm-deepseek)。

数字在 1920×1080 全画面中较小时，裁剪参数框并保留字段名、单位和上下文。先在已导出的原图定位帧号与区域。

从任意工作目录可运行；技能安装位置不同时修改 `$skillRoot`：

```powershell
$skillRoot = Join-Path $env:USERPROFILE '.agents\skills\video-operation-review'
$pythonExe = 'python'
$reviewCli = Join-Path $skillRoot 'scripts\review_video.py'
$ReviewWork = 'D:\video-reviews\tutorial'
& $pythonExe -X utf8 $reviewCli crop --work $ReviewWork --asset f000000024 --box 400,200,1000,600
```

裁剪保留源帧身份。宿主提供 `original` 细节选项时可按需使用；局部证据的区域以实际可读性选择。

## 上下文与恢复

- 上下文较小时，一批处理一个具有完整前后关系的操作单元，保存步骤、疑点与帧引用后继续。
- 每次记录当前对象、变化、确认/取消、证据和待核对项。待辨认值写 null，并按疑点补查。
- 上下文压缩或任务续接后，先读 `status`、`intervals`、`candidates --pending`，重新打开当前步骤所需证据；查看计数按源帧去重。
- 工具支持顺序执行及获准的多审阅者协作。自审与独立复核使用各自状态登记。

CLI 与 v1/v2/v3 数据库兼容性由脚本回归检查；实际模型试用结果见 [validation.md](validation.md)。
