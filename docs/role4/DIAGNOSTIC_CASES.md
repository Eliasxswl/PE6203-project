# Diagnostic cases / 诊断案例

Source commit: 291e1e998c7e81fa369cd195e3180cc9465764bd

These are pilot diagnostics. They do not establish selective_patch under-update or over-update failures. The current registered strategies are only no_update and full_rewrite. Raw evidence is preserved in diagnostic_case_evidence.json and the pinned source snapshot.

以下仅为试跑诊断。尚无 Selective Patch 轨迹，不能用这些案例替代作业要求的补丁更新不足/过度更新案例。

## Case A: high TF with an empty final answer / 空回答却获高分

Run: 20261015T045814.065101Z_Kevin

Identity: no_update/original/117/0

- TF = 10.0; PE = 9.4; stop_reason = empty_response; final answer is empty.
- Saved tool-call sequence: plan_task → analyze_task → reflect_task (message indices 2, 6, 10).
- One saved judge response says three requirements were met (real-time data, AI algorithms and user-friendly interface) and assigns 10.
- This is a validity-review flag: an empty final answer does not by itself prove that no work was done, but planning/reflection calls and a high score do not demonstrate a completed application either. Review raw tool responses and produced artifacts against every task requirement before accepting the judge claim.
- Do not rewrite the official score. Report the saved score and the evidence-based limitation separately. Five similar judge scores cannot remove a shared validity problem.

中文：轨迹以空回答结束，调用主要是规划、分析和反思，但 judge 认为所有需求已完成。需要查工具返回和实际产物，不能只因分数高就认定任务成功，也不能擅自修改官方分数。

## Case B: failure on an unchanged control / 未变化任务上的失败

Run: 20261015T045814.065101Z_Kevin

Identity: no_update/iter3/403/0

- Role 3 labels task 403 as a control whose required tools are unchanged.
- TF = 1.0; PE = 10.0; stop_reason = three_text_responses.
- Saved tool-call sequence contains plan_task; the final answer says the model cannot directly interact with external tools and asks for further input.
- One saved judge response says none of the requested log-analysis/root-cause/fix requirements was fulfilled.
- Interpretation: this is evidence of a refusal/non-completion behavior in that run. It is not evidence of over-update: the strategy is no_update, and no unrelated knowledge edit has been identified.
- This illustrates why retention analysis needs paired task scores plus trajectories, and why PE alone is not a task-success measure.

中文：工具没有变化，Agent 却在规划后声称不能使用工具，没有完成任务。这是执行/模型行为的诊断案例；No Update 没有改知识，不能把它归因为过度更新。

## Case C: invalid task identity and exhausted budget / 无效任务标识与预算耗尽

Run: 20261015T045814.065101Z_Kevin

Identity: full_rewrite/iter5/117/0

- TF = 1.75; PE = 3.25; stop_reason = request_budget_exhausted; final answer empty.
- Calls: plan_task → plan_task → analyze_task → reflect_task → execute_task → execute_task → execute_task.
- Four of five judge slots completed. One judge explains execute_task could not find the supplied task ID and the agent did not recover.
- Compare the actual execute_task responses and arguments in the raw trace before assigning root cause. Repeated invalid IDs may be a reasoning/state-management issue; they are not sufficient evidence of an omitted schema patch.

中文：重复执行调用、judge 提到任务ID找不到、最后预算耗尽。已有证据可用于描述失败过程，但还不能证明是工具知识更新错误。

## Evidence needed for final under-update / over-update cases

For each final selective_patch case preserve: task requirement; original/new live tool catalog; actual patch manifest and before/after knowledge; failing call and tool response; final artifact/answer; comparator on the same task/version; judge reasoning. Treat low scores as candidates for investigation, not causal labels.
