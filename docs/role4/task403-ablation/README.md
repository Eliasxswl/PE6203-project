# Task 403 unchanged-memory ablation

Status: **prepared and offline-tested; no live ablation result yet**. This work is separate from the main three-strategy experiment and does not alter its records or configuration.

## Intervention

The source is `results/20261026T084527.010290Z_Kevin/`, Full Rewrite repeat 0, Middle-to-Late transition, task 403. Both conditions use exactly the same task, Late tool knowledge, model settings, prompt timestamp, and provider account. Both use the **same already-rebuilt affected-tool experience records**. The only intervention is on five unaffected experience records:

| Condition | Experience attached to unchanged tools |
| --- | --- |
| `rewrite_unchanged` | Archived Full Rewrite Late records |
| `preserve_unchanged` | The same episode's archived Middle records, before this Late rewrite |

The two affected experience entries stay identical across conditions; the five unaffected entries are restored only in the control. This targets one transition. It is not No Update of the entire harness, not memory removal, and not a replay of the entire benchmark. Archived update outputs are reused, so there are **zero new updater calls**. Repeating evaluation measures Agent/Judge variability for fixed snapshots; it does not measure update-generation variability.

The standalone script deep-copies both states and records checksum, exact modified entry IDs, fixed provenance and source hashes. It rebases dependency checkpoints against the same Late tool catalog. The live runner invokes the existing `run_trajectory` and `LiveRuntime` only; it does not change `core.py`, `runtime.py` or the strategies.

## Offline preparation (no model requests)

From the repository root:

```text
python scripts/role4/task403_ablation.py prepare
python scripts/role4/task403_ablation.py preflight
python -m unittest discover -s tests -p test_role4_task403_ablation.py -v
```

Outputs go under ignored `.runtime/role4-task403-ablation/`. `plan.json` freezes both states; a changed plan is rejected instead of silently overwritten. `preflight.json` reports missing resources, without printing credential values. The plan fingerprint for this source is `6b65d658805334fc44a79321c7b50dd0bff2c1adf56d1cb9c6dc4f69c80f6236`.

Five offline regression tests verify selective restoration, defensive copying, provenance/identity rejection, immutable plan hashes, missing-pair handling, and retention of outcomes unfavorable to the hypothesis. Preparation against the actual archive found **five unaffected** and **two affected** experience entries. This is preparation evidence, not simulated scientific performance.

## Live execution on an already prepared machine

Use the team's tested runtime environment and locally prepared server files. First pull/merge this branch, run the preparation/preflight commands above, and review the two arm snapshots. When all prerequisites are present, explicitly start:

```text
python scripts/role4/task403_ablation.py run --execute-live --repeats 3
```

This creates six Agent trajectories and 30 judge slots (Agent trajectories can make multiple requests). It alternates AB/BA order, executes serially, disables shared-baseline reuse, and uses one frozen account for both conditions (source task 403/repeat 0 maps to `BIGMODEL_API_KEY_4` in the archived five-account configuration). Set credentials only in the local ignored `.env` or environment, never in committed files.

Each trial uses a fresh copied fixture workspace, private task-source state, fresh MCP processes, and an available localhost port through the existing runtime. This is the existing reviewed process/workspace isolation, **not** a new container or an operating-system security sandbox. Named resource locks and model admission control remain active. Catalog drift is rejected; memory validation runs before inference. Code, fixture, Late config and plan fingerprints are checked around trials; changed inputs invalidate scores. Do not edit these inputs while running.

Each invocation writes a new `live-<timestamp>/` folder with `experiment.json`, durable per-event `records.json` and `summary.json`. The manifest includes source revision and dirty-source status. Interrupted requests are not replayed or silently converted to successes; reruns use new directories and must be described as new runs, not merged repeats.

## Current machine readiness

The prepared archive/plan and unit tests are available locally. Static preflight reports missing Python runtime dependencies (`mcp`, `openai`, `httpx`, `langchain`, `langchain_openai`, `jsonschema`, `psutil`, `dotenv`), `.runtime/node_modules/@1mcp/agent/build/index.js`, `config/local/iter5.json` with frozen executables, and `BIGMODEL_API_KEY_4`. No key was read out or requested in chat. No model requests or MCP processes were started. Role 2's already prepared experiment machine is the shortest execution path; rebuilding this workstation would additionally require installing dependencies and downloading/configuring servers.

## Interpreting the result

Primary comparison: paired TF difference `rewrite_unchanged − preserve_unchanged`, plus coverage, PE, schema-error calls, stop reasons and the actual tool-call chain. Negative differences support detrimental rewriting for these frozen contexts; zero or positive differences do not support that explanation and must be reported. A single changed outcome is not a deterministic causal proof with stochastic models. Inspect unsupported `tags` calls to `plan_task`, failed recovery, and whether the memory intervention is actually visible.

Do not assume this will produce the desired case. Preserve all three paired repeats, including missing scores and failures. Do not choose the best seed after looking at outcomes. The aggregate summary is not a substitute for checking traces. Keep this supplemental result separate from the original main metric tables.

## English group update (accurate current status)

I’ve prepared the task-403 ablation on a separate branch and passed the offline tests. Both conditions keep the Late tool knowledge and affected experience fixed; only the five unchanged experience records differ. The runner reuses our isolated runtime and archived update outputs, so no new updater calls are needed. My machine does not yet have the server setup and runtime credentials, so there are no live results yet. Could we run the provided three-pair command on the existing experiment machine? I can analyze the outputs afterward.

## 中文翻译

我已在独立分支准备好任务403的消融，并通过离线测试。两组固定Late工具知识和受影响经验，只改变五条未变化经验。入口复用现有隔离运行环境和已保存更新结果，不需要新增更新器调用。我的机器尚未配置服务器环境和运行凭据，所以还没有真实结果。能否在现有实验机器上运行提供的三组配对命令？之后我可以负责分析输出。
