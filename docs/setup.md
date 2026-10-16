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

Role 3 edits the ID list, optional classifications in that same file, and matching `task_count` before a new experiment. Keep original tasks and inputs unchanged. The current dependency-screened selection is **9, 24, 117, 273, 403**; it is not a representative random sample.

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

Transition names are destinations: `iter3` means Early → Middle; `iter5` means Middle → Late. For affected tasks use `cohort: changed` and the observed `change_types` (`tool`, `parameter`, `description`; multiple labels allowed). Confirmation requires `status: confirmed`, `reviewed_by: <name>`, and a rationale for each transition. Labels stay outside Agent inputs. Unconfirmed, unavailable or conflicting evidence is excluded from cohort comparisons with a reason. Selection quotas and protocol approval remain Role 3 decisions.

## 4. Validate and run

```text
python -m custom.experiment validate --config config/experiment.json
python -m custom.experiment check --config config/experiment.json
python -m custom.experiment run --config config/experiment.json --parallel --workers 4
```

- `validate` checks configuration without model requests and reports dirty source, pending classifications, archive presence and backend-policy warnings. It does not approve a formal experiment or prove backend availability.
- `check` starts private tools and verifies model tool calling, tool feedback, and scoring JSON. Successful model checking uses three requests and currently checks the first provider in each role. Check added account keys separately before a full run. Use `--skip-models`, `--server <name>`, or `--stage original` to narrow diagnostics.
- `run` owns tool startup, task execution, and scoring. No separate server or scoring script is needed. Omit `--parallel --workers 4` for serial execution.

The current pilot compares `no_update` and `full_rewrite`: **5 tasks × 3 versions × 1 repeat = 30 trajectories**, each with **5 judge slots = 150 planned slots**. Adding Selective Patch requires Role 1's registered implementation.

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

The manifest preserves settings, source/code fingerprints, task definitions/classifications, actual Python/Node/platform versions and SHA-256 hashes of available bundle archives. Missing archives are explicit. Archive hashes identify downloaded bytes; they do not certify extraction equivalence. Local tool entry files remain fingerprinted separately. Records contain trajectories, raw tool traces, knowledge updates, attempt statuses, usage, timings, scores, and failures. Diagnostics stay under ignored `.runtime/experiments/checks/`.

```text
python -m custom.experiment run --config config/experiment.json --resume <experiment-directory>
python -m custom.experiment summarize --experiment <experiment-directory>
```

Resume preserves the original mode/worker count and continues only unstarted work. Completed, failed, or ambiguous requests are not replayed. Environment/provider failures skip scoring; operational Agent mistakes remain scored. Failed judge slots consume their slot without replacement; averages use valid scores and report coverage.

`aggregate.ecs` retains per-strategy ECS. Compare strategies with `aggregate.paired_ecs`: its task/repeat pairs have valid scores for every compared strategy and all three versions. Per-version comparisons remain under `paired`. Excluded common-ECS pairs list missing conditions and reasons. Recovery/retention compares current TF minus previous-version TF on common valid pairs with confirmed, catalog-consistent classifications; `not_configured` or `pending` is not a zero score. Update costs are counted once per episode transition under `update_costs`, with reported/unreported counts and currency separation.

`completion` reports operational status and coverage. Run exit codes: **0** = all trajectories scored (possibly `completed_with_warnings` for invalid Judge slots); **3** = incomplete work or trajectories without usable scores; **2** = error/invalidation; **130** = interruption. Existing five-slot averaging remains unchanged. Formal acceptance is always `not_assessed`: the group must approve its protocol and coverage policy. `summarize` explicitly rewrites the aggregate in `records.json`; use a copy when inspecting an immutable archive. Older manifests lack new provenance/classifications and are not retroactively certified.

Before a formal run, freeze code/configuration in an authorized commit, resolve Role 3 preparation items, check the selected tools on the target machine, and run the explicit Judge compatibility check. Diagnostic pilots may use dirty source; preserve that fact. Do not edit old manifests to turn a pilot into a clean run. Current macOS/Linux runtime checks remain pending.

Keep each manifest and records file together. Upload completed result directories separately from code; avoid concurrent edits to the same run. Credentials, local configs, downloads, runtime logs, and temporary state stay ignored. Commit or push only when authorized.

## 6. Development and member interfaces

```text
python -m custom.experiment run --config config/experiment.json --offline --parallel --workers 4
python -m unittest discover -s tests -v
```

Offline execution uses fake models/tools and writes under `.runtime/experiments/offline-results/`; it is not benchmark evidence.

**Role 1:** register `update(knowledge, old_tools, new_tools, context) -> UpdateResult` through `custom.experiment.adapters.register`, then list the module in `strategy_plugins`. Knowledge is keyed by `server::tool`; descriptions/schemas are separate from routes. Inputs are defensive copies; context supplies stage/repeat. The pipeline measures elapsed time. Plugins additionally report `api_calls` (dispatched requests, including failed calls), `input_tokens`, `output_tokens`, `api_cost`, `cost_currency` and `cost_basis`. Use actual provider usage and a stated pricing/invoice basis; leave unavailable values `None`. Positive money amounts require a currency; free calls may report zero with an explicit basis. Old plugins remain compatible but unreported usage stays unknown. Both deterministic baselines report zero model usage. Agent/Judge usage is separate and never substitutes for update cost.

**Backend isolation:** parallel policies declare `concurrency: private`, `readonly`, or `exclusive`. Exclusive resources require common `shared_resources` names such as `tcp:3000`; OS locks serialize access. Workspace state may be redirected through `env_paths`. Mutable remote services require an implemented reset/private namespace and are otherwise rejected. These controls are not a security sandbox for arbitrary commands.

See [fixed-plan.md](fixed-plan.md) for protocol decisions and validation history. Default documentation is maintained here and in the root README.

Execution repair: new runs use `execution_repair_v1`. Nonempty text without tool calls ends the Agent turn; a finish marker never suppresses structured tool calls. Tool results retain MCP content, structured data, and error flags; Agent-visible results have an explicit 32,000-character limit with truncation metadata, while raw results remain complete. Provider/runtime failures remain execution failures. This preparation repair keeps the Judge prompt, scoring rules, five attempts, TF/PE/ECS formulas and five-task default selection unchanged; it adds cost/provenance information and paired comparisons. Old runs cannot resume under changed source fingerprints, and scores from different execution protocols must not be pooled. Experimental Judge changes and ten-task pilots remain on `harness-repair`.
