# Final failure cases and supplemental evidence

## Under-update: stale request_planning contract

Formal knowledge run `20261026T084527.010290Z_Kevin`, key `no_update/iter5/416/0`: TF=1.0, PE=4.6. The Early request-planning schema requires `originalRequest` and `tasks`. Middle adds required `splitDetails`; Late also requires `priority` and `tags`. No Update retains Early knowledge. Its actual request omits new required arguments, receives `schema_input_invalid`, and asks the user to adjust inputs instead of recovering. This is direct evidence of stale-contract under-update in the baseline, not proof of a Selective Patch detector omission.

## Over-update: Task 9 complete-library context intervention

Supplemental run: `20261029T113248.805747Z_Kevin`; original task 9, Late, fixed Full Rewrite snapshot repeat 2. Source: `task-9-confirmation-review.json`, `records.json`, `experiment.json`, and `inputs/counterfactual-snapshots.json` in that folder.

The original user asks to locate yesterday's log, read it, and set up a structured analysis/reporting plan. The primary diagnostic endpoint is narrower: the requested file's actual contents must be returned by a real `read_text_file` call. A response claiming success, a Judge score, or reading a different file is insufficient.

The ten groups compare these three conditions:

| Arm | Memory intervention | Actual log read |
| --- | --- | --- |
| `fr_all` | Full Rewrite's complete saved knowledge | 3/10 |
| `fr_changed_only` | Same affected records; restore five unchanged-tool records from original K0 | 10/10 |
| `fr_order_only` | Full Rewrite's same semantic values, reversed JSON object-key presentation | 0/10 |

All seven memory records remain visible. The five restored records refer to tools unavailable to this task and cannot directly supply an extra callable tool. The two affected records—including the file-search guidance and its recursive call template—are byte-identical between FR and restoration. Initial requests have equal callable tools, non-memory input, model and decoding settings within each group. Tool knowledge is not switched to No Update.

### Representative paired trace (group 0)

- `fr_all/iter5/9/0` calls `search_files` with `*yesterday*`, receives `No matches found`, and does not read the log.
- `fr_changed_only/iter5/9/0` calls `search_files` with `**/*yesterday*`, obtains the actual log path, calls `read_text_file` and receives the fixture contents: service start, low disk space, failed database connection and user login. It subsequently creates a task plan using `request_planning`.
- `fr_order_only/iter5/9/0` uses the nonrecursive pattern and fails the reading endpoint.

The analyzer rechecks every group from the raw tool trace, rather than copying the final answer. All thirty Agent executions complete without infrastructure failures. The planning endpoint is separately reported as 3/10, 10/10 and 0/10; this is not a replacement for original TF labels or proof that all requested analysis/reporting work is complete.

### Strength and limits of the claim

Restoration wins in seven discordant paired groups; no group favors FR alone. The exact two-sided paired binary p-value is 0.015625 for this fixed confirmation comparison. This is not corrected for prior exploratory selection, is not a whole-benchmark significance claim, and should not be the main slide headline.

The result supports a detrimental effect of unnecessary knowledge rewriting on behavior under complete-library injection **for this original task and frozen snapshot**. Since affected tool guidance and callable tools are fixed, the remaining prompt intervention is on unrelated experience. However, its wording, character length and formatting change together: no individual harmful fact or deleted search instruction is identified. The affected file-search template still contains recursive search in both conditions. JSON object-key order alone also changes outcomes, showing presentation sensitivity; that control changes formatting of affected as well as unaffected records.

Task 9 and this source snapshot were chosen after exploratory screening, including an unhelpful task-403 route. The ten-group retained confirmation was fixed before dispatch, with no replacement or early stopping, but remains a selected case study. Do not omit the selection disclosure, claim the original experiment was rerun unchanged, or generalize to all tasks.

## What this supersedes

The previous task-403 candidate was not the successful supplementary case. Its preparation PR is historical. This task-9 intervention supplies stronger evidence than merely observing a control-task score drop, but still does not localize a particular sentence or prove a universal advantage for Selective Patch.

中文：最终案例使用任务9，不再使用任务403作为成功证据。3/10、10/10、0/10是实际日志读取成功率，不是TF。恢复五条原始经验、固定两条受影响经验和可调用工具后，读取表现改善，支持全库注入时存在上下文干扰风险；但任务与快照经过探索筛选，文字、长度、呈现共同变化，不能指认某句知识有害，也不能推广到所有任务。
