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

Offline runs use deterministic providers and write under `.runtime/experiments/offline-results/`; they are development evidence. The current configuration compares `no_update` and `full_rewrite`: 17 tasks, 3 versions, 1 repeat. Early is executed and judged once per task/repeat, shared across strategies: **102 logical conditions, 85 actual trajectories, 425 judge slots**. Task count and repeats are configurable. This dependency-screened selection does not represent a random benchmark sample; integration and preflight do not certify task completion or formal protocol approval.

Optional parallel execution uses the same entry point:

```text
python -m custom.experiment run --config config/experiment.json --parallel --workers 4
```

Workers run independent tasks within each version, then queue scoring jobs. Knowledge updates keep Early -> Middle -> Late order. A shared account/model request gate currently allows two in-flight requests, including estimated long contexts, and a 0.2-second dispatch interval. There is no fixed wait after successful responses. Overload reduces concurrency and adds shared cooldown; requests are never retried or judge slots topped up.

Agent and judge models are independent fields in `config/experiment.json`. For a separate judge key, set it in `.env` and change the judge provider entries to reference that environment variable; explicit provider entries take precedence over fallback judge variables. `providers.agent.quota_group` and `providers.judge.quota_group` must match for the same account, even with different keys. Use distinct groups only for confirmed separate accounts. Different models have separate gates. The current profile uses both keys for Agent and judge, with stable task assignment across the two accounts. Four workers can therefore use up to two requests per account. For one-account use, replace each provider list with its first entry. See the setup guide. Extra keys do not guarantee availability during platform overload.

Live output: `results/<experiment-id>/{experiment.json,records.json}`. Use `run --config config/experiment.json --resume <experiment-directory>` with the same configuration/mode to continue unstarted work, and `summarize --experiment <experiment-directory>` to aggregate it. Completed, failed, and ambiguous requests are not replayed. Keep code, configuration, selection, and inputs unchanged while running.

New manifests freeze runtime versions, bundle archive hashes and optional Role 3 classifications from the selection file. Classifications compare each evolved version against Early; recovery/retention uses same-version TF minus No Update TF. Results include update costs and common-sample ECS (`paired_ecs`). Shared Early rows use `shared_from`; follow that key for traces and usage, and count the source only once. Missing update usage stays unknown. Exit code 0 means operational completion, 3 means partial/unscored trajectories, and 2 means failure or invalidation; none grants formal acceptance. Invalid judge slots with usable trajectory scores are reported as warnings. See the setup guide for the member contracts.

Completed pilot results are archived under `results/`, including provider-failure runs. Keep code commits separate from result commits; upload finished experiments and stage explicit paths rather than the entire repository. Credentials, downloaded tools, local configurations, and runtime logs stay ignored.

The common pipeline supplies `no_update` and `full_rewrite`; Role 1 must register `selective_patch` through the adapter contract. Unsupported strategies fail validation. Unknown backends fail execution until their state isolation is reviewed and implemented. Four-worker spawn and four concurrent local MCP runtimes were tested; real macOS/Linux checks remain pending.

See [docs/fixed-plan.md](docs/fixed-plan.md) for protocol, justified changes, and validation evidence; [docs/setup.md](docs/setup.md) covers detailed usage.

Offline tests: `python -m unittest discover -s tests -v`. Commit or push only when explicitly instructed.
