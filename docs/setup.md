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

Copy `.env.example` to `.env` and fill in the three independent account keys:

```ini
BIGMODEL_API_KEY=your-first-account-key
BIGMODEL_API_KEY_2=your-second-account-key
BIGMODEL_API_KEY_3=your-third-account-key
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
| `judge_output_mode` | `json_object` requests JSON and validates the six-field output locally; `text` preserves the legacy parser |
| `agent_repeats`, temperatures, token limits | Experiment parameters, fixed across compared strategies |
| `providers.agent`, `providers.judge` | Account pools using environment variable names and public quota-group labels |
| `request_policy` | Per-account/model concurrency, dispatch spacing, and overload cooldown |

The current profile uses `glm-4-flash-250414` for both roles across three independent accounts. Each account allows two simultaneous requests, including long contexts; six workers can therefore use up to six in total. A 0.2-second dispatch interval smooths requests without sleeping after every response. HTTP 429 reduces capacity and adds shared cooldown. Calls are never retried or judge slots topped up.

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
python -m custom.experiment run --config config/experiment.json --parallel --workers 6
```

- `validate` checks configuration without model requests and reports dirty source, pending classifications, archive presence and backend-policy warnings. It does not approve a formal experiment or prove backend availability.
- `check` starts private tools and verifies model tool calling, tool feedback, and scoring JSON. Successful model checking uses three requests and currently checks the first provider in each role. Check added account keys separately before a full run. Use `--skip-models`, `--server <name>`, or `--stage original` to narrow diagnostics.
- `run` owns tool startup, task execution, and scoring. No separate server or scoring script is needed. Omit `--parallel --workers 6` for serial execution.

All 17 selected tasks passed the [local preflight](../results/verification/role3-preflight-20261017T063246.892278Z_Kevin.json) checks applicable to their dependencies, and both model accounts passed synthetic tool-calling and scoring checks. Passing preflight does not establish whole-task completion. Recheck dependencies on the intended host before running.

The current configuration compares `no_update`, `full_rewrite`, and `selective_patch` on 17 tasks with one repeat: **153 logical conditions, 119 actual trajectories and 595 judge slots**. Early is executed once per task/repeat with five judge slots; all strategies reference that same result. With S strategies, N tasks and R repeats, actual trajectories = `(1 + 2S) × N × R`; judge slots = five times that count. Three strategies therefore need seven actual trajectories per task/repeat. Repeats remain independent: three repeats require three Early executions per task. Role 1's plugin is registered via `strategy_plugins`. Preflight does not start this experiment. For the six-task integration trial (9, 24, 117, 416, 273, 403), use `python -m custom.experiment run --config config/strategy-smoke.json --parallel --workers 6`: 42 actual trajectories and 210 judge slots. The frozen 17-task selection is unchanged.

For an explicit scoring compatibility check, choose a completed Agent trajectory key from an archived `records.json`:

```text
python -m custom.experiment judge-check --config config/experiment.json --experiment results/<id> --trajectory no_update/original/9/0 --attempts 1 --provider-index 0
```

This makes one Judge request by default (up to five when explicitly selected), starts no tools and never changes the archived experiment. It uses the current branch's formal Judge prompt/request/parser and current Judge configuration. Raw replies, usage and source/request protocols are saved under ignored `.runtime/experiments/checks/`. Provider index selects the configured Judge account; check each account separately. Passing confirms request/format compatibility, not semantic grading accuracy. Failed diagnostic attempts are not replaced.

The current GLM endpoint accepted a `json_schema` request but returned fields that violated its required fields and enums in a synthetic capability probe. Therefore the configured mode is explicitly **JSON-object output plus local Schema validation**, not strict server-side Schema enforcement. The Schema requires the original three integer scores (1–10) and three reasoning strings, rejects extra/missing fields, and retains the original integer-only rule. Duplicate keys, malformed JSON, refusals and incomplete responses are rejected without repair, fallback or extra calls. The request appends a serialization-only contract to the unchanged upstream rubric. New manifests and Judge attempts record the mode and Schema hash; diagnostics hash the actual sent prompt. JSON validity does not certify grading accuracy.

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
python -m custom.experiment run --config config/experiment.json --offline --parallel --workers 6
python -m unittest discover -s tests -v
```

Offline execution uses fake models/tools and writes under `.runtime/experiments/offline-results/`; it is not benchmark evidence.

**Role 1:** register `update(knowledge, old_tools, new_tools, context) -> UpdateResult` through `custom.experiment.adapters.register`, then list the module in `strategy_plugins`. Knowledge is keyed by `server::tool`; descriptions/schemas are separate from routes. Inputs are defensive copies; context supplies stage/repeat. The pipeline measures elapsed time. Plugins additionally report `api_calls` (dispatched requests, including failed calls), `input_tokens`, `output_tokens`, `api_cost`, `cost_currency` and `cost_basis`. Use actual provider usage and a stated pricing/invoice basis; leave unavailable values `None`. Positive money amounts require a currency; free calls may report zero with an explicit basis. Old plugins remain compatible but unreported usage stays unknown. Both deterministic baselines report zero model usage. Agent/Judge usage is separate and never substitutes for update cost.

**Backend isolation:** parallel policies declare `concurrency: private`, `readonly`, or `exclusive`. Exclusive resources require common `shared_resources` names such as `tcp:3000`; OS locks serialize access. Workspace state may be redirected through `env_paths`. Mutable remote services require an implemented reset/private namespace and are otherwise rejected. These controls are not a security sandbox for arbitrary commands.

See [fixed-plan.md](fixed-plan.md) for protocol decisions and validation history. Default documentation is maintained here and in the root README.

New runs use `shared_early_json_v1`: JSON-object Judge output and local Schema validation alongside shared Early executions, classification relative to Early, and same-version comparisons against No Update. Existing execution repairs remain: nonempty text without tool calls ends the Agent turn; a finish marker never suppresses structured tool calls. Tool results retain MCP content, structured data, and error flags; Agent-visible results have an explicit 32,000-character limit with truncation metadata, while raw results remain complete. Provider/runtime failures remain execution failures. The upstream rubric, scoring rules, five attempts, TF/PE/ECS formulas, models and repeats are unchanged; the Judge request adds output-format instructions and a response-format parameter. The current selection is Role 3's frozen 17-task core set. Old runs cannot resume under changed source fingerprints; historical scores and independent Early executions are preserved. Scores from different protocols must not be pooled. Experimental Judge changes and ten-task pilots remain on `harness-repair`.

Selective Patch compares adjacent catalogs and patches changed fields locally, without model calls. With complete initial catalog knowledge and exact deterministic updates, its resulting knowledge equals Full Rewrite; observed score differences between them cannot establish an adaptation-method advantage. Patch audit work and unchanged-field preservation can still be inspected.

## Optional LangMem diagnostic

The `langmem-adaptation` branch uses the official [LangMem memory manager](https://langchain-ai.github.io/langmem/reference/memory/) to extract and update tool knowledge. Isolated server/workflow namespaces receive raw independent practice traces; previous handwritten guidance and official task answers are excluded. Install `requirements-memory.txt` in a separate virtual environment rather than combining it with `requirements-api.txt`.

```text
python -m pip install -r requirements-memory.txt
python -m custom.experiment memory-check --config config/langmem-diagnostic.json
python -m custom.experiment prepare-memory --config config/langmem-diagnostic.json
python -m custom.experiment memory-ablation --config config/langmem-diagnostic.json --task-id 9 --task-id 24 --task-id 117 --task-id 267 --task-id 273 --parallel --workers 10
```

Use the existing Python import-path setup. Preparation requires LangMem; executing a frozen artifact also works in the original API environment. `memory.model` selects the builder; Agent and Judge settings are unchanged. Artifacts are immutable, so a rebuild requires a new filename. Each extraction permits at most six dispatched requests including upstream format repairs; API failures are not retried. LangSmith tracing is not required.

This is an Early-only with/without-memory comparison: three executions per task, five Judge slots per execution, with no online learning or shared scores. `memory-ablation.json` reports actual exposure and paired scores. It does not implement a three-strategy evolution experiment; formal `run` rejects memory settings. Generated knowledge can be incorrect; valid memory objects and Judge scores do not certify correctness.

`python -m custom.experiment memory-causal-check --config config/langmem-diagnostic.json --workers 10` runs a separate synthetic file-recovery diagnostic. Real MCP practice must demonstrate a failed path/lookup, successful discovery, and an exact-content read before the builder derives a structured procedure. Three held-out nested-file cases compare no rule, a verified reference rule, generated knowledge, and an irrelevant reference; each condition runs three times. Success requires the correct target to be read through the tool with exact expected contents. There are no Judge calls or official task changes. All artifacts and per-trial journals are saved together in a new result directory; the irrelevant reference matches generated-reference character length, not token count.

## Minimal official agent integration

`config/langchain-minimal.json` selects `agent_backend: langchain`. The model/tool loop uses LangChain's official `create_agent`; the existing experiment entry point, reset/isolation, stages, fixed request limits, Judge and records remain in place. Install the separate pinned `requirements-memory.txt` environment for this optional backend. Omit `agent_backend` to retain the original backend. No Deep Agents built-in filesystem, shell or planning tools are added, so benchmark operations continue through the selected MCP server version.

The causal check's v2 builder uses one JSON-object request with strict local Schema and evidence validation. This avoids depending on forced function-call output, which the current GLM endpoint did not reliably return in the earlier probes. Invalid or empty knowledge is rejected and its condition is explicitly not attempted; valid control conditions can still complete. No model scoring, output repair, automatic API retry or replacement trial is used.

Selective Patch remains the project's own registered implementation. No third-party knowledge-update or patch-selection method substitutes for it. The v2 causal diagnostic forms initial knowledge with one model request and local validation; it does not use LangMem extraction or an off-the-shelf update algorithm. This preparation is separate from the experimental adaptation strategy. To use the official loop in the causal check, run `python -m custom.experiment memory-causal-check --config config/langchain-minimal.json --workers 10`.

Verified recovery comparison: `python -m custom.experiment prepare-recovery-memory --config config/recovery-ablation.json` collects independent task-tool repairs and imports the frozen file-recovery rule. Only actual error plus program-verified correction evidence is accepted; invalid generations are recorded without retries. Artifact paths must be new. Then run `python -m custom.experiment memory-ablation --config config/recovery-ablation.json --all-selected --parallel --workers 10`. The 17 selected Early tasks run three times per condition with five Judge slots each (102 executions / 510 slots). Both conditions use the official loop and the same catalog, accounts and settings; only frozen knowledge exposure differs. Reports include paired score differences, exposure, tool errors and failures. Evaluation never changes the knowledge library.

Expanded independent transfer check: `python -m custom.experiment memory-causal-check --config config/langchain-minimal.json --suite transfer --workers 10`. Three practice cases cover keyword placement, unknown extensions, and a known-path boundary. One model request derives a frozen candidate. Eight unseen cases compare no rule, the previous rule, the new rule and a matched irrelevant reference, each repeated three times (96 trajectories, no Judge). Evaluation uses the production memory renderer and requires both a real correct-file read and the payload in the final answer. Provider failures are reported separately. The candidate K0 preserves unrelated entries and is archived before validation; it is not automatically promoted to the official-task configuration. No benchmark tasks or historical scores are changed.

Use `--suite transfer-templates` to retain the same frozen summary while retaining successful call templates from program-verified traces. Admission requires exact provenance and physical replay on the two unknown-path practice cases. This suite uses fresh held-out names and payloads, compares no knowledge / summary only / summary plus templates / irrelevant reference, and retains the same 96-trajectory plan. Test Agents choose their own calls; template replay is an admission check only. Rejected retention or replay stops before held-out evaluation.

`python -m custom.experiment expand-memory --config config/recovery-ablation.json --workers 10` collects independent repairs for analysis inputs, nested task dependencies, task-source setup/add, and returned request IDs. Each family requires two actual failed-then-corrected practice cases, program verification, and physical replay of retained call templates. A failed family is excluded, with its evidence preserved. Accepted procedures are frozen before fresh recovery and clean-operation checks (two cases, three repeats, with/without memory). These checks use objective tool/state outcomes and no Judge. Provider failures are separate from operation failures; neither is retried. The existing file procedure is retained verbatim. Synthetic practice does not change the official task set.

Point `memory.artifact` and `memory.source` to the accepted run's `candidate-k0.json` and `candidate-evidence.json`, then run `python -m custom.experiment memory-ablation --config config/recovery-ablation.json --all-selected --parallel --workers 10`. Keep `config/subsets/selected_tasks.json` unchanged: the original 17 tasks, two Early-only conditions, three Agent repeats, and five Judge slots give 102 planned trajectories / 510 slots. The model chooses its calls; template replay is restricted to practice admission. No online learning, strategy replacement, or benchmark answer changes are involved.

For the research gate, run `recovery-check --config config/recovery-ablation.json --workers 10` through the same module entry point. Eight real-tool regression trials compare file-only and triggered profiles on recovery/clean operations; these reuse fixed practice cases and do not claim fresh held-out usefulness. Run `memory-ablation --config config/recovery-ablation.json --all-selected --three-arm --parallel --workers 10` after acceptance. All three conditions use the same frozen artifact, 17 tasks, model, budgets and isolation. The file rule remains proactive. New source/ID references appear only after the matching observed error and last for the next model request. No extra model request or automatic repair call is made; raw tool responses and the Judge rubric are unchanged. Activations record the failed call, response hash, exact reference and selected IDs.

Three-arm results use identical scored task/repeat triples for primary means, plus pairwise comparisons and a sensitivity table requiring all five Judge slots in every condition. Missing executions/scores remain visible and are never replaced. `memory-ablation.json` contains the comparisons; `records.json` contains `memory_activations`. This is a knowledge-use experiment, not the Early/Middle/Late Selective Patch evaluation.
