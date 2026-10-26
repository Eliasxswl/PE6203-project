# PE6203 Project 4

Compare **No Update**, **Full Rewrite**, and **Selective Patch** across Early, Middle, and Late tool environments.

Forked from [Octobrist/MCPEvol-Bench](https://github.com/Octobrist/MCPEvol-Bench), starting at `888c779a0fe735f612ca62bdd1fdd7c9e6bf8701`. See the [upstream README](https://github.com/Octobrist/MCPEvol-Bench/blob/888c779a0fe735f612ca62bdd1fdd7c9e6bf8701/README.md) for benchmark details and [docs/setup.md](docs/setup.md) for our full setup and execution guide.

## Quick setup

Use your installed Python command (`python`, `python3`, or Windows `py`); the pinned API dependencies require Python 3.11+. There is no requirement to use exactly 3.12. Python 3.12 was tested locally.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

With the environment active, use `python` on both systems:

```text
python -m pip install -r requirements-api.txt
npm install --prefix .runtime @1mcp/agent@0.39.1
```

Copy `.env.example` to `.env` and fill in `BIGMODEL_API_KEY` and `BIGMODEL_API_KEY_2` for the current two-account profile. `.env` loads automatically and stays out of Git. Formal model and experiment settings come from `config/experiment.json`; the model variables in `.env` are for standalone diagnostics. `requirements.txt` is the upstream full environment; our API workflow uses only `requirements-api.txt`.

## Tasks and tools

- Tasks: `src/custom/data/test_cases/test_cases.json`; candidate IDs: `chosen_idx.json` in the same directory.
- Input files/workspace: `anotation_path/`.
- Download the three archives from [the tool bundles](https://huggingface.co/datasets/anonymous2233/evol-servers/tree/main) into `servers/downloads/`.
- Extract using `python scripts/extract_servers.py original` (repeat for `iter3` and `iter5`), then run `python scripts/prepare_local_config.py`.
- Generated server configurations: `config/local/`. Prepare these separately on every machine.

## Start the pipeline

Run from the repository root with the environment active:

```text
python -m custom.experiment validate --config config/experiment.json
python -m custom.experiment check --config config/experiment.json
python -m custom.experiment run --config config/experiment.json
```

`validate` checks configuration and reports preparation gaps without model calls. `check` discovers tool catalogs and makes three model requests on success; its output is diagnostic only. `run` starts private tool servers, runs tasks, and scores trajectories automatically. Use `check --skip-models` for tool-only diagnostics. The setup guide also covers `catalog-diff` (saved catalog evidence) and explicit `judge-check` (real-trajectory scoring compatibility).

## Experiment pipeline

Role 3's frozen 17-task core selection is in `config/subsets/selected_tasks.json`. All selected tasks have Role 3-confirmed classifications. The configured model is `glm-4-flash-250414` for Agent and judge. For development without model or tool-server calls:

```text
python -m custom.experiment validate --config config/experiment.json --offline
python -m custom.experiment run --config config/experiment.json --offline
python -m custom.experiment run --config config/experiment.json --offline --parallel --workers 2
```

Offline runs use deterministic providers and write under `.runtime/experiments/offline-results/`; they are development evidence. The current configuration compares `no_update`, `full_rewrite`, and `selective_patch`: 17 tasks, 3 versions, 1 repeat. Early is executed and judged once per task/repeat, shared across strategies: **153 logical conditions, 119 actual trajectories, 595 judge slots**. Task count and repeats are configurable. This dependency-screened selection does not represent a random benchmark sample; integration and preflight do not certify task completion or formal protocol approval.

Optional parallel execution uses the same entry point:

```text
python -m custom.experiment run --config config/experiment.json --parallel --workers 6
```

Workers run independent tasks within each version, then queue scoring jobs. Knowledge updates keep Early -> Middle -> Late order. A shared account/model request gate currently allows two in-flight requests, including estimated long contexts, and a 0.2-second dispatch interval. There is no fixed wait after successful responses. Overload reduces concurrency and adds shared cooldown; requests are never retried or judge slots topped up.

Agent and judge models are independent fields in `config/experiment.json`. For a separate judge key, set it in `.env` and change the judge provider entries to reference that environment variable; explicit provider entries take precedence over fallback judge variables. `providers.agent.quota_group` and `providers.judge.quota_group` must match for the same account, even with different keys. Use distinct groups only for confirmed separate accounts. Different models have separate gates. The current profile uses three independent account keys for Agent and judge, with stable task assignment. Six workers can therefore use up to two requests per account. For one-account use, replace each provider list with its first entry. See the setup guide. Extra keys do not guarantee availability during platform overload.

Judge output uses `judge_output_mode: json_object` plus local JSON Schema validation of the six rubric fields. Strict server-side Schema enforcement was not observed for this GLM model. The upstream rubric is unchanged; a serialization-only instruction is appended. Invalid replies consume their existing slot without repair or retry. New runs use `shared_early_json_v1`; historical scores are preserved.

Live output: `results/<experiment-id>/{experiment.json,records.json}`. Use `run --config config/experiment.json --resume <experiment-directory>` with the same configuration/mode to continue unstarted work, and `summarize --experiment <experiment-directory>` to aggregate it. Completed, failed, and ambiguous requests are not replayed. Keep code, configuration, selection, and inputs unchanged while running.

New manifests freeze runtime versions, bundle archive hashes and optional Role 3 classifications from the selection file. Classifications compare each evolved version against Early; recovery/retention uses same-version TF minus No Update TF. Results include update costs and common-sample ECS (`paired_ecs`). Shared Early rows use `shared_from`; follow that key for traces and usage, and count the source only once. Missing update usage stays unknown. Exit code 0 means operational completion, 3 means partial/unscored trajectories, and 2 means failure or invalidation; none grants formal acceptance. Invalid judge slots with usable trajectory scores are reported as warnings. See the setup guide for the member contracts.

Completed pilot results are archived under `results/`, including provider-failure runs. Keep code commits separate from result commits; upload finished experiments and stage explicit paths rather than the entire repository. Credentials, downloaded tools, local configurations, and runtime logs stay ignored.

The common pipeline supplies `no_update`, `full_rewrite`, and the registered `custom.experiment.selective_patch` plugin. Unsupported strategies fail validation. A six-task trial uses `config/strategy-smoke.json` through the same entry point. Unknown backends fail execution until their state isolation is reviewed and implemented. Four-worker spawn and four concurrent local MCP runtimes were tested; real macOS/Linux checks remain pending.

See [docs/fixed-plan.md](docs/fixed-plan.md) for protocol, justified changes, and validation evidence; [docs/setup.md](docs/setup.md) covers detailed usage.

Offline tests: `python -m unittest discover -s tests -v`. Commit or push only when explicitly instructed.

## Experience research branch

`langmem-adaptation` contains optional frozen-experience experiments, isolated from the core pipeline on `main`. Use a separate environment with `requirements-memory.txt`; see the final sections of [docs/setup.md](docs/setup.md). `config/recovery-ablation.json` keeps the original 17 tasks, three Agent repeats and five Judge slots. Archived results include independent practice evidence, frozen knowledge and paired with/without-experience comparisons. These diagnostics do not replace the three-strategy evolution experiment or establish an advantage for Selective Patch.

Current development check: `python -m custom.experiment memory-pilot --config config/recovery-ablation.json --parallel --workers 10`. It runs every original selected task once with the complete frozen experience library: 17 trajectories / 85 planned Judge slots. Request budgets are unchanged. Review every task in `task-review.json`; unavailable tool bindings are marked explicitly and no experience entry is silently filtered. `recovery-check` is an alias for this fixed-task check. Full experiments retain three repeats after adaptation is frozen; the research objective is comparing update strategies, not maximizing an experience/no-experience gap. Historical ablations remain archived.

Strategy comparison: `python -m custom.experiment run --config config/experience-evolution.json --parallel --workers 10`. This profile prepares independent catalog/experience checkpoints for No Update, Full Rewrite and Selective Patch before executing the original 17 tasks across all three versions. One repeat shares Early: 119 actual trajectories / 595 Judge slots. Knowledge updates use GPT-6 Luna through OpenRouter with a $1 per-run update budget; Actor/Judge keep GLM. See the setup guide for environment settings, snapshot semantics and update evidence.

Successful Shrimp knowledge: `prepare-knowledge` independently verifies tool workflows and adds procedures, constraints and effect boundaries without fabricating failures. The generated `config/knowledge-evolution.json` freezes a separate seven-entry candidate library. Use `memory-pilot` with that profile for the original 17-task check before another strategy comparison; see the setup guide for the commands and evidence rules.
