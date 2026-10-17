# Setup and execution

Run commands from the repository root. Use Python 3.11+ and Node.js 24. Windows has been tested; real macOS/Linux checks remain pending.

## 1. Install dependencies

Create and activate a virtual environment using your installed Python command (`python`, `python3`, or Windows `py`).

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Once activated, use `python` on all platforms:

```text
python -m pip install -r requirements-api.txt
npm install --prefix .runtime @1mcp/agent@0.39.1
```

Skip creation if `.venv` already exists. `requirements.txt` is the larger upstream environment; our API workflow uses `requirements-api.txt`.

## 2. Configure API access

Copy `.env.example` to `.env` and fill in the two account keys:

```ini
BIGMODEL_API_KEY=your-first-account-key
BIGMODEL_API_KEY_2=your-second-account-key
BIGMODEL_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
BIGMODEL_MODEL=glm-4-flash-250414
BIGMODEL_JUDGE_MODEL=
BENCH_JUDGE_RUNS=5
PYTHONUTF8=1
```

`.env` loads automatically and stays out of Git. Quotes are optional; existing environment variables take precedence.

Formal settings come from `config/experiment.json`:

| Setting | Purpose |
| --- | --- |
| `agent_model`, `judge_model` | Execution and scoring models; a blank judge model uses the Agent model |
| `agent_repeats`, temperatures, token limits | Experiment parameters, fixed across compared strategies |
| `providers.agent`, `providers.judge` | Account pools using environment variable names and public quota-group labels |
| `request_policy` | Per-account/model concurrency, dispatch spacing, and overload cooldown |

The current profile uses `glm-4-flash-250414` for both roles and both accounts. Each account allows two simultaneous requests, including long contexts; four workers can therefore use up to four in total. A 0.2-second dispatch interval smooths requests without sleeping after every response. HTTP 429 reduces capacity and adds shared cooldown. Calls are never retried or judge slots topped up.

The same account must always use the same `quota_group`, even across different keys or roles. Tasks are assigned by frozen list position/repeat, preserving the account across strategies and versions. For one-account use, replace both provider lists with their first entry. For a separate judge account, change the judge provider entries to reference its key variable and quota group. Explicit `api_key_env`/`base_url_env` entries override fallback judge variables. Model variables in `.env` apply to standalone diagnostics, not formal runs.

Check your account's [model limits](https://bigmodel.cn/usercenter/proj-mgmt/rate-limits) before changing models. More keys do not guarantee availability during platform overload.

## 3. Prepare tasks and tools

| Location | Contents |
| --- | --- |
| `src/custom/data/test_cases/test_cases.json` | Official tasks |
| `src/custom/data/test_cases/chosen_idx.json` | Candidate task IDs |
| `config/subsets/selected_tasks.json` | The single frozen task selection |
| `anotation_path/` | Original task inputs |
| `config/experiment.json` | Experiment configuration |
| `config/local/` | Generated machine-specific MCP configurations |

Download `original_servers.zip`, `iter3_servers.zip`, and `iter5_servers.zip` from [the upstream tool bundles](https://huggingface.co/datasets/anonymous2233/evol-servers/tree/main) into `servers/downloads/`, then run:

```text
python scripts/extract_servers.py original
python scripts/extract_servers.py iter3
python scripts/extract_servers.py iter5
python scripts/prepare_local_config.py
```

These versions correspond to Early, Middle, and Late. Every teammate generates local configs on their own machine. Downloads, extracted tools, and local configs stay ignored. Selected servers must use frozen local executables; downloading launchers such as npx/uvx are rejected. Other tasks may need additional services or OS dependencies.

Role 3 edits the ID list, optional classifications in that same file, and matching `task_count` before a new experiment. Keep original tasks and inputs unchanged. The current selection is Role 3's frozen **17-task core set**, with confirmed classifications; it is not a representative random sample. Keep the frozen selection bytes unchanged; Role 3 records its SHA-256 in the task list and protocol. Tasks 29 and 157 remain in the archived 19-task pilot only. A selection change does not alter archived runs.

Read actual saved catalog differences without changing an experiment:

```text
python -m custom.experiment catalog-diff --experiment results/<id>
```

Evidence separates tool additions/removals, structural parameter changes and description changes, including nested schemas. Per-task evidence covers required tools. Unchanged definitions do not certify unchanged behavior; catalog failures never count as retention evidence. Role 3 can add this optional object to an existing `samples` entry (illustrative candidate, not an approved control):

```json
{
  "idx": 273,
  "classification": {
    "status": "draft",
    "transitions": {
      "iter3": {"cohort": "retention", "change_types": [], "rationale": "Candidate; behavior review pending"},
      "iter5": {"cohort": "retention", "change_types": [], "rationale": "Candidate; behavior review pending"}
    }
  }
}
```

Classification names are destinations relative to Early: `iter3` means Early → Middle; `iter5` means Early → Late. For affected tasks use `cohort: changed` and the observed `change_types` (`tool`, `parameter`, `description`; multiple labels allowed). Confirmation requires `status: confirmed`, `reviewed_by: <name>`, and a rationale for each comparison. Labels stay outside Agent inputs. Unconfirmed, unavailable or conflicting evidence is excluded from cohort comparisons with a reason. Strategy updates still compare adjacent catalogs (Early → Middle → Late). Selection quotas and protocol approval remain Role 3 decisions.

## 4. Validate and run

```text
python -m custom.experiment validate --config config/experiment.json
python -m custom.experiment check --config config/experiment.json
python -m custom.experiment run --config config/experiment.json --parallel --workers 4
```

- `validate` checks configuration without model requests and reports dirty source, pending classifications, archive presence and backend-policy warnings. It does not approve a formal experiment or prove backend availability.
- `check` starts private tools and verifies model tool calling, tool feedback, and scoring JSON. Successful model checking uses three requests and currently checks the first provider in each role. Check added account keys separately before a full run. Use `--skip-models`, `--server <name>`, or `--stage original` to narrow diagnostics.
- `run` owns tool startup, task execution, and scoring. No separate server or scoring script is needed. Omit `--parallel --workers 4` for serial execution.

All 17 selected tasks passed the [local preflight](../results/verification/role3-preflight-20261017T063246.892278Z_Kevin.json) checks applicable to their dependencies, and both model accounts passed synthetic tool-calling and scoring checks. Passing preflight does not establish whole-task completion. Recheck dependencies on the intended host before running.

The current configuration compares `no_update` and `full_rewrite` on 17 tasks with one repeat: **102 logical conditions, 85 actual trajectories and 425 judge slots**. Early is executed once per task/repeat with five judge slots; all strategies reference that same result. With S strategies, N tasks and R repeats, actual trajectories = `(1 + 2S) × N × R`; judge slots = five times that count. Three strategies therefore need seven actual trajectories per task/repeat. Repeats remain independent: three repeats require three Early executions per task. Adding Selective Patch requires Role 1's registered implementation. Preflight does not start this experiment.

For an explicit scoring compatibility check, choose a completed Agent trajectory key from an archived `records.json`:

```text
python -m custom.experiment judge-check --config config/experiment.json --experiment results/<id> --trajectory no_update/original/9/0 --attempts 1 --provider-index 0
```

This makes one Judge request by default (up to five when explicitly selected), starts no tools and never changes the archived experiment. It uses the current branch's formal Judge prompt/request/parser and current Judge configuration. Raw replies, usage and source/request protocols are saved under ignored `.runtime/experiments/checks/`. Provider index selects the configured Judge account; check each account separately. Passing confirms request/format compatibility, not semantic grading accuracy. Failed diagnostic attempts are not replaced.

Workers execute independent tasks within a version, then queue scoring jobs in the same bounded pool. Agent turns and tool calls remain sequential within each trajectory. Every version finishes before the next knowledge update. Each trajectory receives fresh inputs, backend state, services, and conversation; one parent writes checkpoints.

Do not edit code, configuration, task selection, inputs, or generated local configs while running. Changes require a new experiment; source drift invalidates scores. Live catalogs from the three supplied tool snapshots are used; unverified mutation overlays are not applied.

## 5. Results and recovery

```text
results/<UTC-microseconds>_<git-user-name>/
    experiment.json
    records.json
```

The manifest preserves settings, source/code fingerprints, task definitions/classifications, actual Python/Node/platform versions and SHA-256 hashes of available bundle archives. Missing archives are explicit. Archive hashes identify downloaded bytes; they do not certify extraction equivalence. Local tool entry files remain fingerprinted separately. Records contain trajectories, raw tool traces, knowledge updates, attempt statuses, usage, timings, scores, and failures. `planned_jobs` lists actual executions; `logical_conditions` includes shared Early references. Diagnostics stay under ignored `.runtime/experiments/checks/`.

Early's source owner is `no_update` when selected, otherwise the first configured strategy. Its episodes run first in serial and parallel modes. Other Early rows contain `shared_from` with the source trajectory key, synchronized scores/status and empty attempt lists; inspect the source for traces, failed slots, usage and timing. These rows are references, not independent samples. Failure or resume never creates replacement Early executions or extra judge slots. `completion` counts actual trajectories/slots and reports logical conditions separately; per-strategy tables include the common Early score.

```text
python -m custom.experiment run --config config/experiment.json --resume <experiment-directory>
python -m custom.experiment summarize --experiment <experiment-directory>
```

Resume preserves the original mode/worker count and continues only unstarted work. Completed, failed, or ambiguous requests are not replayed. Environment/provider failures skip scoring; operational Agent mistakes remain scored. Failed judge slots consume their slot without replacement; averages use valid scores and report coverage.

`aggregate.ecs` retains per-strategy ECS. Compare strategies with `aggregate.paired_ecs`: its task/repeat pairs have valid scores for every compared strategy and all three versions. Per-version comparisons remain under `paired`. Excluded common-ECS pairs list missing conditions and reasons. Recovery/retention requires confirmed, catalog-consistent labels relative to Early and valid same-version scores for every compared strategy. `mean_tf_delta_vs_no_update` is the mean of paired `TF_strategy − TF_NoUpdate`: on changed tasks it measures adaptation benefit; on retention tasks a negative value indicates harm. It is a TF-point difference, not a success rate. No normalized recovery ratio is required or generated. Missing labels, evidence, scores or No Update are reported explicitly; `not_configured` or `pending` is not a zero score. Update costs are counted once per episode transition under `update_costs`, with reported/unreported counts and currency separation.

`completion` reports operational status and coverage. Run exit codes: **0** = all trajectories scored (possibly `completed_with_warnings` for invalid Judge slots); **3** = incomplete work or trajectories without usable scores; **2** = error/invalidation; **130** = interruption. Existing five-slot averaging remains unchanged. Formal acceptance is always `not_assessed`: the group must approve its protocol and coverage policy. `summarize` explicitly rewrites the aggregate in `records.json`; use a copy when inspecting an immutable archive. Older manifests lack new provenance/classifications and are not retroactively certified.

Before a formal run, freeze code/configuration in an authorized commit, resolve Role 3 preparation items, check the selected tools on the target machine, and run the explicit Judge compatibility check. Diagnostic pilots may use dirty source; preserve that fact. Do not edit old manifests to turn a pilot into a clean run. Current macOS/Linux runtime checks remain pending.

Keep each manifest and records file together. Upload completed result directories separately from code; avoid concurrent edits to the same run. Credentials, local configs, downloads, runtime logs, and temporary state stay ignored. Commit or push only when authorized.

Stopped tool runtimes automatically remove their copied `workspace`, private `home` and `tmp`; small service logs and generated configurations remain under `.runtime/r/`. This also applies to startup failures. For file-state debugging, explicitly add `"keep_workspaces": true` inside the experiment's `runtime` settings before starting a new run. Cleanup errors are logged without changing scores. Hard-killed processes can leave copies behind; inspect only after the relevant experiment has stopped. Original fixtures, tool bundles and archived results are unaffected.

## 6. Development and member interfaces

```text
python -m custom.experiment run --config config/experiment.json --offline --parallel --workers 4
python -m unittest discover -s tests -v
```

Offline execution uses fake models/tools and writes under `.runtime/experiments/offline-results/`; it is not benchmark evidence.

**Role 1:** register `update(knowledge, old_tools, new_tools, context) -> UpdateResult` through `custom.experiment.adapters.register`, then list the module in `strategy_plugins`. Knowledge is keyed by `server::tool`; descriptions/schemas are separate from routes. Inputs are defensive copies; context supplies stage/repeat. The pipeline measures elapsed time. Plugins additionally report `api_calls` (dispatched requests, including failed calls), `input_tokens`, `output_tokens`, `api_cost`, `cost_currency` and `cost_basis`. Use actual provider usage and a stated pricing/invoice basis; leave unavailable values `None`. Positive money amounts require a currency; free calls may report zero with an explicit basis. Old plugins remain compatible but unreported usage stays unknown. Both deterministic baselines report zero model usage. Agent/Judge usage is separate and never substitutes for update cost.

**Backend isolation:** parallel policies declare `concurrency: private`, `readonly`, or `exclusive`. Exclusive resources require common `shared_resources` names such as `tcp:3000`; OS locks serialize access. Workspace state may be redirected through `env_paths`. Mutable remote services require an implemented reset/private namespace and are otherwise rejected. These controls are not a security sandbox for arbitrary commands.

See [fixed-plan.md](fixed-plan.md) for protocol decisions and validation history. Default documentation is maintained here and in the root README.

New runs use `shared_early_v1`: shared Early executions, classification relative to Early, and same-version comparisons against No Update. Existing execution repairs remain: nonempty text without tool calls ends the Agent turn; a finish marker never suppresses structured tool calls. Tool results retain MCP content, structured data, and error flags; Agent-visible results have an explicit 32,000-character limit with truncation metadata, while raw results remain complete. Provider/runtime failures remain execution failures. The Judge prompt, scoring rules, five attempts, TF/PE/ECS formulas, models and repeats are unchanged. The current selection is Role 3's frozen 17-task core set. Old runs cannot resume under changed source fingerprints; historical independent Early executions are not retroactively shared. Scores from different protocols must not be pooled. Experimental Judge changes and ten-task pilots remain on `harness-repair`.
