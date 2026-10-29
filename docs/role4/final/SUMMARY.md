# 最终分析摘要与汇报口径

## 两轮正式实验分开呈现

两轮都使用原定17个任务、三个版本、三次执行重复、每轨迹五个评分位置；执行温度0.2、评分温度0。每轮459条逻辑记录含102条共享Early引用，实际执行357条，不能把引用当额外实验或额外费用。

| 轮次 | No Update配对ECS | Full Rewrite配对ECS | Selective Patch配对ECS | 共同任务/重复配对数 |
| --- | --- | --- | --- | --- |
| 工具目录基线轮 | 8.135 | 8.161 | 8.233 | 51 |
| 自维护经验知识轮 | 8.371 | 7.939 | 8.547 | 49 |

第一轮全部357次执行有分数；第二轮355次有分数，两次基础设施失败分别为MCP启动超时和API超时。各轮的有效样本、评分缺失与排除原因见RESULTS.md和analysis.json。

不能把两轮合成六次重复：第一轮采用目录级确定性更新及旧Agent，第二轮接入LangChain、自维护经验和统一更新模型/校验。它们是不同系统条件，跨轮差异不能全部归功于Selective Patch。

## 性能、保留与成本

第二轮中，Selective Patch配对ECS最高，但并非所有方面都最好。在四个受影响任务上，Full Rewrite的恢复更强：Middle相对No Update平均TF提高2.171，Selective Patch提高1.521；Late分别提高1.618和0.964。

在未变化任务上，Selective Patch保留更好：Late相对No Update平均TF差为−0.268，Full Rewrite为−1.208。因此合适的论点是成本和能力保留之间的权衡，不是全面优越、完全无损或统计显著提升。

第一轮更新不调用模型，三策略更新API费用均为0。第二轮Full Rewrite更新调用42次，费用0.018229775美元；Selective Patch调用12次，费用0.004193390美元，约降低77%。这些是六次版本更新的累计费用，不是整场实验总费用。Agent/Judge的token另行记录，未知美元费用没有填成0。

## 最终过度更新案例改用任务9

以results/index.json中的task9_over_update_case为准。原始任务9、Full Rewrite重复2的固定知识快照、十组对照、共三十次执行。没有调用Judge，没有新增付费知识更新；不修改正式实验历史成绩。

| 条件 | 实际读取目标日志 |
| --- | --- |
| Full Rewrite完整经验 | 3/10 |
| 固定受影响经验，恢复五条未变化工具的原始K0经验 | 10/10 |
| Full Rewrite语义不变、仅改JSON对象键呈现顺序 | 0/10 |

三组仍然注入全部七条经验，绝不是删除五条或只注入两条。可调用工具和两条受影响经验一致；五条被恢复经验对应的工具在此任务不可调用。因此恢复并未给Agent增加工具，结果支持全库上下文中的无关经验重写可能影响行为。

原始轨迹显示典型差异：失败组用`*yesterday*`搜索后没有匹配，未读取日志；恢复组用`**/*yesterday*`找到文件，实际读到日志内容并创建计划。两组的受影响文件搜索模板本来就保留递归结构，不能说某条搜索规则被Full Rewrite删掉。

## 必须保留的限制

- 任务9与该快照是在探索筛选后选出的。十组确认执行在发出前固定，但不是随机挑出的独立基准样本。
- 恢复五条记录同时改变文字、长度和呈现，没有定位到某句有害知识。
- 键顺序对照也改变受影响经验的呈现，不仅仅改变五条无关经验；0/10表明格式敏感，不能据此断言唯一机制。
- 3/10、10/10、0/10是实际日志读取成功率，不是TF、整体任务完成率或全基准成绩。
- 第二轮及消融清单仍有dirty_source=true。归档源码校验通过意味着可追溯，不应宣称完全满足此前的干净提交要求。

## 交给Role 5的建议讲法

在这17个任务中，选择性更新在配对ECS和更新费用上表现较好，同时避免了部分不必要重写；但全量更新在变化任务上的恢复更强。任务9的固定快照对照进一步表明，即使可调用工具和相关知识保持一致，无关知识的重写与呈现变化仍可能影响Agent行为。结论限定于当前系统、子集和案例。

## English group update

I’ve updated Role 4 using the active runs in `results/index.json`. The report now presents the two formal rounds separately and replaces the task-403 candidate with the task-9 ten-group confirmation. I independently checked the 30 raw traces and reproduced the actual log-read outcomes of 3/10, 10/10 and 0/10, along with the fixed inputs and memory interventions.

These are behavioral read-success rates, not TF or overall task completion. The report retains the exploratory task/snapshot selection disclosure and the limitations of the JSON-order control. The main experiment scores remain unchanged. Please use `docs/role4/final/` for final report and slide integration.

## 中文翻译

我已根据results/index.json中的有效运行更新Role 4。报告现在分别呈现两轮正式实验，并用任务9的十组确认消融替换任务403候选。我已独立检查三十条原始轨迹，复算3/10、10/10、0/10的实际日志读取结果，并核对固定输入与知识干预。

这些是行为读取成功率，不是TF或整体任务完成率。报告保留了任务/快照经过探索筛选的披露和JSON顺序对照的限制，主实验分数没有修改。最终报告和幻灯片整合请使用docs/role4/final/目录。
