# 三策略结果解读与组内交接

分析对象：`20261026T084527.010290Z_Kevin`，17个任务、三个版本、三次重复。全部统计均来自该运行，不混合之前试跑。

## 主要结论

Selective Patch的配对ECS为8.547，No Update为8.371，Full Rewrite为7.939。这里只能说本次固定子集上描述性排序更好，不能宣称统计显著或在整个基准上普遍更好。

Middle TF均分分别为：No Update 8.530，Full Rewrite 9.055，Selective Patch 9.161。Late共同有效样本的TF均分为8.776、8.202、8.784。Late的Selective Patch与No Update平均TF非常接近，不能包装成大幅提升。

在四个受影响任务上，Full Rewrite恢复更强：Middle相对No Update增加2.171分，Selective Patch增加1.521分；Late分别增加1.618和0.964分。

在13个对照任务上，Selective Patch的保留表现更好：Late平均TF差为−0.268，Full Rewrite为−1.208。但Selective Patch仍有退化，不能说完全无损。

更新开销：Full Rewrite共42次更新模型调用，费用0.018229775美元；Selective Patch共12次，费用0.004193390美元，约降低77.0%。更新步骤累计时长约229.43秒与76.26秒，约降低66.8%。这些是6次版本更新的累计成本，不是整场实验总费用，也不是单个任务费用。Agent/Judge的token单独报告，未凭空估计其美元费用。

## 已完成的证据核对

- 459条逻辑轨迹含102条共享Early副本，实际357次执行；其中355次有分数。
- 1737个评分位置完成，38个评分失败，10个因执行失败未评分。不能把共享行当额外评分。
- 两个执行失败已保留：Full Rewrite/Late/任务9/重复0为MCP启动超时；Selective Patch/Late/任务278/重复0为API超时。
- 所有有效轨迹的710个TF/PE均值已与评分明细核对；配对ECS与官方计算及保存聚合值一致；更新费用与budget日志核对一致。
- 源码zip的SHA-256与清单一致。但dirty_source=true仍然不等于满足旧协议的干净提交条件，报告已如实披露。
- Selective Patch的42个经验条目转换中，12个依赖变化条目均重建，30个未受影响条目完全保留。没有观察到选择范围上的漏改或多改，但这不能证明文本语义和Agent行为完全正确。

## 失败分析的实际进度

已确认一个No Update使用旧schema的更新不足案例；已记录Full Rewrite重写未变化经验、并出现对照任务退化的疑似过度更新案例。后者缺少反事实证据，不能宣称已证明因果。另有两条Selective Patch低分轨迹表明：即使知识正确保留，Agent仍可能加错参数或忽视长度限制。完整调用与错误见CASES.md。

因此，你的Role 4主体数值分析、图表和真实轨迹整理已经完成。尚需团队确认的是最终实验口径与“已确认过度更新”的证据是否足够；这些应明确交接，不能靠编造补齐。

## English message for the group

I have completed the Role 4 analysis for run `20261026T084527.010290Z_Kevin`, including matched TF/PE/ECS, recovery/retention, update costs, figures, and trajectory-based failure reviews. Selective Patch has the highest paired ECS (8.547) and about 77% lower update spend than Full Rewrite, although Full Rewrite shows stronger recovery on the changed tasks. The report accounts for shared Early results, incomplete judge slots and the two execution failures.

Two qualifications remain: the run has `dirty_source=true` despite a verified archived source snapshot, and the over-update example is a candidate rather than a confirmed causal case. Please review these points when integrating the final report. The analysis did not launch additional model calls or change the original results.

## 中文翻译

我已完成这组运行的Role 4分析，包括配对TF/PE/ECS、恢复与保留、更新成本、图表和基于轨迹的失败审阅。Selective Patch的配对ECS最高（8.547），更新费用比Full Rewrite低约77%，不过Full Rewrite在受影响任务上的恢复更强。报告已考虑共享Early结果、部分无效评分及两次执行失败。

仍需注意两点：虽然源码快照校验通过，运行仍标为dirty_source=true；过度更新案例目前是候选，尚未证实因果。整合最终报告时请审阅这两点。本分析没有发起额外模型调用，也没有修改原始结果。
