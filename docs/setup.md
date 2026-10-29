# Setup and execution

Run commands from the repository root. Use Python 3.11+ and Node.js 24. Windows is tested; real macOS/Linux tool-runtime checks remain pending.

## 1. Environment

Create `.venv` using your installed command (`python`, `python3`, or Windows `py`). Activate it with `.\.venv\Scripts\Activate.ps1` on PowerShell or `source .venv/bin/activate` on macOS/Linux. Use `python` after activation.

Choose one dependency profile per environment:

| Profile | Dependencies | Configuration |
| --- | --- | --- |
| Current knowledge experiment | `requirements-memory.txt` | `config/knowledge-evolution-formal.json` |
| Catalog-only pipeline | `requirements-api.txt` | `config/experiment.json` |
| Original upstream environment | `requirements.txt` | See upstream instructions |

The memory environment is standalone and pins a different OpenAI SDK. Do not install it over the API environment.

```text
python -m pip install -r requirements-memory.txt
npm install --prefix .runtime @1mcp/agent@0.39.1
```

Copy `.env.example` to `.env`; it loads automatically and is ignored by Git. Fill the credential variables referenced by the selected profile. The current formal knowledge profile references five independent BigModel accounts (`BIGMODEL_API_KEY` through `_5`). Multiple keys from one account share its quota. Reduce both provider lists for fewer accounts and preserve the same `quota_group` for the same account.

BigModel uses `BIGMODEL_BASE_URL=https://open.bigmodel.cn/api/paas/v4/`. Model IDs in the JSON profile control formal runs; standalone `.env` model variables do not override them. Actor and Judge default to `glm-4-flash-250414`. An empty configured Judge model uses the Actor model.

Knowledge generation uses `OPENROUTE_API_KEY`, `OPENROUTE_BASE_URL=https://openrouter.ai/api/v1`, and the configured `memory.model`. Both FR and SP use `openai/gpt-6-luna` with the same builder and a $1 update budget per experiment. Credential checks still follow the selected profile when replaying frozen knowledge, but the case command makes no update requests.

If Python does not inherit an existing Windows system proxy, set `HTTP_PROXY` and `HTTPS_PROXY` in the local environment or `.env`, with `NO_PROXY=localhost,127.0.0.1` for private tool services. Do not commit proxy credentials or disable certificate validation. There are no automatic model retries or Judge top-ups.

## 2. Tool bundles

Download `original_servers.zip`, `iter3_servers.zip` and `iter5_servers.zip` from the [tool bundle repository](https://huggingface.co/datasets/anonymous2233/evol-servers/tree/main) into `servers/downloads/`.

```text
python scripts/extract_servers.py original
python scripts/extract_servers.py iter3
python scripts/extract_servers.py iter5
python scripts/prepare_local_config.py
```

The extractor preserves the downloaded bundles and prepares portable local package paths. Generated `config/local/` files are machine-specific; generate them on each machine. Early maps to `original`, Middle to `iter3`, and Late to the supplied `iter5` snapshot. Use these actual snapshots rather than inferring additional mutations from the directory name.

Tasks are in `src/custom/data/test_cases/test_cases.json`; official candidate IDs are in `chosen_idx.json`. Role 3's frozen 17-task selection is `config/subsets/selected_tasks.json`; fixture files are in `anotation_path/`. Select IDs without changing original questions, inputs or labels.

## 3. Validate and run

```text
python -m custom.experiment validate --config config/knowledge-evolution-formal.json
python -m custom.experiment check --config config/knowledge-evolution-formal.json
python -m custom.experiment run --config config/knowledge-evolution-formal.json --parallel --workers 10
```

`validate` checks configuration and provenance without model calls. `check` tests the configured tools and models; use `--skip-models` for tool-only checks. The same `run` entry point supports serial execution by omitting `--parallel --workers 10`.

The formal knowledge profile fixes 17 tasks, three versions, three Agent repeats and five Judge slots. Early is executed once per task/repeat and shared by all strategies: **459 logical conditions, 357 actual trajectories, 1,785 planned Judge slots**. Each trajectory has fresh files, services, backend state and conversation. Unknown stateful backends require reviewed isolation/reset policies before execution.

One parent writes durable checkpoints while workers execute independent Agent and Judge jobs. Frozen snapshots use shared Early first, then independent Middle/Late jobs across strategies and repeats. Agent turns and tool calls remain sequential within one trajectory. Shared account/model gates control concurrency and overload cooldown; successful responses have no fixed post-response sleep.

Do not edit source, configurations, selected tasks, fixtures or local server routes while a run is active. Drift invalidates the result. Environment/provider failures and invalid Judge outputs remain missing rather than being repaired or silently replayed. Empty terminal provider responses are execution errors; original responses and any completed tool calls remain recorded.

The LangChain backend delegates the agent loop to official `create_agent`. Harness knowledge consists of tool contracts plus a frozen, independently practiced library. No Update retains it, FR rebuilds all records, and SP rebuilds records whose referenced tool contracts changed. FR/SP share the same update model, prompt format and validator. Updates see previous knowledge and old/new tool contracts, without benchmark questions, trajectories or scores. JSON validation checks syntax/contracts, not behavioral correctness.

The original Judge rubric and TF/PE/ECS calculations are retained. JSON-object output plus local Schema validation constrains the three scores and reasoning fields; it does not guarantee judging accuracy. Five attempts are averaged over valid outputs, with coverage reported. Shared Early references and common-sample comparisons must not be counted as independent executions.

## 4. Results and member interfaces

Use [../results/index.json](../results/index.json) for the final handoff entries:

- Catalog-only 17-task experiment: `results/20261019T234451.269257Z_Kevin`.
- Knowledge-strategy 17-task experiment and frozen donor: `results/20261026T084527.010290Z_Kevin`.
- Final Task 9 case: `results/20261029T113248.805747Z_Kevin`.

Each run preserves `experiment.json` and `records.json`; knowledge runs also freeze inputs and source archives. Keep these files together. Original absolute runtime paths describe the producing machine; use the repository-relative run paths above on another machine. Historical committed runs remain for provenance and existing member/test references. Superseded uncommitted probes and sentence-level attempts were removed; their selected-case history is disclosed in the final case review.

```text
python -m custom.experiment run --config config/knowledge-evolution-formal.json --resume <experiment-directory>
python -m custom.experiment summarize --experiment <experiment-directory>
python -m custom.experiment catalog-diff --experiment <experiment-directory>
```

Resume requires identical inputs/mode and continues only unstarted work. `summarize` rewrites aggregates, so inspect a copy of immutable archives. `aggregate.paired_ecs` compares common valid task/repeat pairs; coverage and excluded conditions remain explicit. Recovery/retention uses same-version paired TF differences against No Update, classified relative to Early. Completion status does not certify task completion or formal acceptance.

Role 1's catalog contract is `update(knowledge, old_tools, new_tools, context) -> UpdateResult`, registered in `custom.experiment.adapters` and listed under `strategy_plugins`. Inputs are defensive copies; context supplies stage/repeat. Report actual update calls, token usage, time and currency-qualified cost; missing usage stays unknown. Experience updates are implemented in `experience_state.py`. With exact complete catalog copying, deterministic FR/SP can yield identical catalog knowledge; the independently maintained library is the additional update surface.

Role 3 maintains selection/classifications in `config/subsets/selected_tasks.json`; [experimental_protocol.md](experimental_protocol.md) and [benchmark_task_list.md](benchmark_task_list.md) record the reviewed definitions. Keep questions and fixture inputs frozen.

## 5. Reproduce the final case

```text
python -m custom.experiment counterfactual-check --source-experiment results/20261026T084527.010290Z_Kevin --task-id 9 --snapshot-repeat 2 --repeats 10 --order-control
```

This optional Late-only diagnostic reuses the exact archived FR snapshot and the normal agent loop. It compares FR, FR with only five unchanged-tool records restored from K0, and an equal-length JSON key-order control. Affected records and callable contracts remain fixed. Each group uses matched visible paths and a completely reset private backend; paths differ across groups and leading conditions rotate. The batch clock is fixed. It makes no Judge or updater calls, and never replaces formal scores. Repeats may be 1, 3 or 10; use a fresh result for changed settings.

The retained batch has 30 valid executions at temperature 0.2: FR **3/10**, restoration **10/10**, and key-order control **0/10** for actual log reading and plan creation. Seven pairs improved under restoration and none reversed (two-sided paired exact p=0.015625). The interpretation is restricted to original Task 9, complete-library injection and this frozen snapshot. Task/snapshot selection followed exploratory screening; this is not benchmark-wide evidence or localization to a unique sentence. Log reading is the primary observable; backend plan creation is supplementary because a textual plan may satisfy the question. These are not replacement TF labels.

`task-9-confirmation-review.json` contains input checks, per-trial tool returns and limitations. `counterfactual.json` from a new run reports case-level observations; `records.json` retains complete requests, responses and workspace observations. Recorded source ZIPs preserve the code used at execution time, including retired diagnostic code; the maintained CLI exposes only the final case-level workflow.

The final case is byte-preserved through `.gitattributes`. Its review also records the donor's producer-byte, committed-blob and semantic hashes: the historical donor differs only by Git CRLF/LF normalization, without changing parsed content.

## 6. Development and maintenance

```text
python -m custom.experiment run --config config/experiment.json --offline --parallel --workers 2
python -m unittest discover -s tests -v
```

Offline providers are deterministic development fixtures, not benchmark evidence. Temporary state and logs stay under ignored `.runtime/` and `logs/`; completed JSON exports are self-contained. Stopped services remove copied workspaces, homes and temporary data. Set `runtime.keep_workspaces=true` before a new debugging run if file-state retention is needed.

Maintain English code/documentation. Original benchmark text, frozen knowledge, historical responses and exact tool-error matching retain their source languages to avoid changing the experimental inputs. Existing Role 3/Role 1 documents remain in place. Credentials, tools, generated routes and temporary checkpoints remain ignored. Commit or push only with explicit authorization.
