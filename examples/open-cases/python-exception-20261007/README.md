# Python 异常处理：新来源完整编辑与运行案例

本例从完整可见的既有 Python 脚本开始，修改两个异常处理分支，随后运行两组输入并显示结果。录屏为 Adam Gaweda 的 *Parsing Exceptions in Python with the as Keyword*，153.581 秒、4606 帧，CC BY 3.0。见[固定来源与许可](source.json)和[机器可读结果](results.json)。

源片：[Wikimedia Commons 固定页面](https://commons.wikimedia.org/w/index.php?title=File:Parsing_Exceptions_in_Python_with_the_as_Keyword.webm&oldid=1187855979)。原片未裁切、未重编码；本目录只分发验证摘要，完整视频、账本、图片和工具记录保留在项目外。

## 实际执行与冻结

1. 新上下文代理从原视频生成交付，完整计算 4606 帧、实际查看 82 张原图，记录 5 个区间、4 个步骤和 15 个风险／随机样本。第一次交付的 227 个文件先冻结；自审阶段为 `valid=true`、`review_complete=false`。
2. 另一名新上下文代理只拿说明、初始脚本和交付附件，从初始状态依次修改代码，在 Python 3.12.10 分两次运行：依次输入 `10`、`a`，再依次输入 `10`、`0`。两次退出码均为 0，标准错误为空。首次结果的 39 个文件冻结后才打开封存参考；代码结构和输出一致。它没有用最终脚本代替编辑过程，也没有访问原视频或封存预期。
3. 再由独立视觉审阅者实际查看同一批 82 张原图，在独立副本登记本人证据、核对当前快照并导出。最终 `valid=true`、`review_complete=true`；首次交付保持不变，独立副本的 315 个文件另行冻结。

主审使用冻结的早期本地候选，独立复核使用最终纠错候选；本例没有退休步骤，两者的内容快照一致。每个库始终只有一个活动记录者。主审与独立复核的原图输入各为 82，不能相加为 164 个不同源帧，也不能把区间覆盖当成逐帧看过。

## 结论范围

这次结果支持所交付脚本修改与两次异常处理运行的可复现性。视频从已有脚本开始，没有展示安装或新建文件；明确保存动作、精确复制粘贴按键及旁白仍未验证。照做采用普通 Python 进程，不证明 Spyder 界面点击的复现。

封存参考来自素材筛选代理的画面转录和本地代码核对，不是作者另附的答案或真人金标准。独立视觉审阅者曾意外看到非本片的公开产品验证摘要，该暴露已记录；其未看本片封存参考、筛选截图或照做结果。

单次照做的准备、任务、取证阶段分别为 127.275、41.617、122.427 秒，最初读任务的时间未测。这些数字不代表全视频审阅耗时，不用于宣称省时、真人可靠性、泛化或语义零遗漏。

## English scope

This CC BY 3.0 recording provides an editing-and-execution chain from a fully visible existing script. A fresh agent authored and froze a delivery; a separate fresh agent followed it before the reference was unsealed. Two real Python 3.12 runs and the transcribed code match the source-screening reference. A separate visual reviewer inspected all 82 used native frames and passed the current layered gate in a copy. Installation, file creation, explicit saving, narration, and native Spyder UI replay are outside the verified scope. Agent checks are not human ground truth or a time-saving claim.
