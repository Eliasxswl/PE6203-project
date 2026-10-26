# Failure evidence and causal limits

Run: `20261026T084527.010290Z_Kevin`. Pointers below refer to keys in `records.json`. The analyzer exports focused evidence to `.runtime/role4-three-strategy/case_evidence.json`. Scores are preserved as saved, not rejudged.

## Under-update: confirmed stale contract in the No Update baseline

Identity: `no_update/iter5/416/0`; TF 1.0, PE 4.6.

The Early `@kazuph/mcp-taskmanager::request_planning` schema requires `originalRequest` and `tasks`. Middle additionally requires `splitDetails`; Late additionally requires `priority` and `tags`, as well as stronger length constraints. No Update retains the Early tool knowledge by design.

At message 2 the Agent calls `request_planning` with `originalRequest` and a task list, omitting the newly required fields. Message 3 returns `schema_input_invalid` with `isError=true`. The final answer requests that the user adjust inputs rather than completing the task. One saved judge result says 0 of 6 requirements were met. The old knowledge, actual missing arguments, target schema and observed error form direct evidence of under-updating in this baseline.

This is not a discovered omission in Selective Patch. The dependency audit of Selective Patch found all 12 affected memory-entry transitions selected for rebuilding. Rebuilt text can still contain semantic errors; the selection audit alone does not prove otherwise.

## Over-update candidate: unchanged knowledge rewritten with a control regression

Identity: `full_rewrite/iter5/403/0`; TF 1.0, PE 7.5. The matched No Update trajectory has TF 10.0, giving ΔTF = −9.0.

Role 3 classifies task 403 as an unchanged control. Full Rewrite rebuilds all seven experience entries per transition, including five whose dependencies are unchanged. Across six transitions, this yields 30 unaffected entry rebuilds, compared with zero under Selective Patch. For example, the unchanged execution-guidance entry `2322985788659b3487d3b0ff` originally states that the execution tool moves a task from pending to in progress; the Full Rewrite Late repeat-0 content removes that explicit state-transition statement. This demonstrates unnecessary semantic editing, but does not by itself establish the cause of task 403's failure.

In the actual task-403 trajectory, message 2 calls `plan_task` with an unsupported `tags` field. Message 3 returns `schema_input_invalid`; structured feedback specifies `additionalProperties=false` and that `tags` was unexpected. The Agent then asks the user for the correct input format rather than repairing the call. One saved judge result says no requirements were met.

**Causal status: suspected, not confirmed.** The log shows unchanged-knowledge rebuilding and a paired regression, but does not connect the specific prose edit above to the invalid `plan_task` call. Model sampling, differing full memory context and judging are alternative explanations. There is no frozen-memory counterfactual replay in the supplied run. Report this as an over-update-risk case, not proven causal damage.

## Selective Patch residual failure: wrong call despite correctly retained knowledge

Identity: `selective_patch/iter5/389/0`; TF 1.0, PE 10.0, versus No Update TF 10.0. Task 389 is an unchanged control.

The Agent calls `analyze_task` with a Chinese `initialConcept` shorter than 50 characters. The tool returns `schema_input_invalid` and structured feedback identifying `minLength=50`. The Agent asks the user for more detail instead of expanding its technical concept and retrying. The associated unchanged memory entry `ffd1b8e05692d9370b52ed48` already explicitly says to provide at least 50 characters, and remains byte-identical under Selective Patch.

This is evidence against labeling every regression as over-update: the relevant knowledge was preserved, but not followed. A high PE score also does not establish successful task completion or recovery.

## Selective Patch residual failure on a changed task

Identity: `selective_patch/iter5/117/1`; TF 2.0, PE 5.5, versus No Update TF 9.8. The Agent supplies unsupported `tags` to `plan_task`, receives `additionalProperties` feedback, and requests user confirmation instead of correcting the call. Task 117's changed required tool is `sequentialthinking`; the failing `plan_task` tool is on an unchanged server. Thus the broad task-level changed label cannot itself attribute this call failure to the patch.

## Assignment coverage and what remains unproven

There is a verified baseline under-update case, an evidence-backed but unconfirmed over-update candidate, and two residual Selective Patch failures. We cannot honestly claim a causally confirmed over-update case or a selective-patching omission from this run. If the assignment requires confirmed causal cases, targeted unchanged-memory counterfactual evidence is still needed; do not fabricate the missing claim or run additional paid experiments without coordinating with the team.

中文说明：已确认 No Update 使用旧参数要求而失败的更新不足案例；Full Rewrite 存在无关知识重写与对照任务退化，但具体因果关系尚未证实。Selective Patch 的部分低分来自明知约束却没有遵守，不能直接贴上更新不足或过度更新标签。最终报告应保留这些证据等级，不能把“疑似”写成“确定”。
