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

Copy `.env.example` to `.env`, then fill in the key and model settings. `.env` loads automatically and stays out of Git. `requirements.txt` is the upstream full environment; our API workflow uses only `requirements-api.txt`.

## Tasks and tools

- Tasks: `src/custom/data/test_cases/test_cases.json`; candidate IDs: `chosen_idx.json` in the same directory.
- Input files/workspace: `anotation_path/`.
- Download the three archives from [the tool bundles](https://huggingface.co/datasets/anonymous2233/evol-servers/tree/main) into `servers/downloads/`.
- Extract using `python scripts/extract_servers.py original` (repeat for `iter3` and `iter5`), then run `python scripts/prepare_local_config.py`.
- Generated server configurations: `config/local/`. Prepare these separately on every machine.

## Start a smoke check

Keep terminal 1 running; terminal 2 discovers tools without calling a model:

```text
# Terminal 1, repository root
python scripts/start_mcp.py --stage smoke
# Terminal 2, repository root
python scripts/probe_mcp.py
```

For real task runs, subset selection, scoring commands, and result paths, follow [the setup guide](docs/setup.md). Windows smoke checks passed; macOS still needs a teammate's real-machine check.

## Experiment pipeline

The ten-task ID list is frozen in `config/subsets/selected_tasks.json`. Start from the repository root:

```text
python -m custom.experiment validate --config config/experiment.json --offline
python -m custom.experiment run --config config/experiment.json --offline
python -m custom.experiment run --config config/experiment.json --offline --parallel --workers 2
```

Offline runs use deterministic providers and write under `.runtime/experiments/offline-results/`; they are development evidence, not benchmark results. The live protocol compares `no_update` and `full_rewrite`: 10 tasks, 3 versions, 3 repeats, and 5 judge attempts per trajectory (180 trajectories / 900 planned judge attempts). After implementation review, explicit authorization, and verification of server isolation and current stage catalogs, omit `--offline` for model-backed execution.

Live output: `results/<experiment-id>/{experiment.json,records.json}`. Use `run --resume <experiment-directory>` with the same configuration/mode to continue unstarted work, and `summarize --experiment <experiment-directory>` to aggregate it. Completed, failed, and ambiguous requests are not replayed.

Run `python -m custom.experiment check --config config/experiment.json` for separate connectivity evidence under the ignored runtime directory; it is not a strategy or formal result.

The common pipeline supplies `no_update` and `full_rewrite`; Role 1 must register `selective_patch` through the adapter contract. Unsupported strategies fail validation. Unknown backends fail execution until their state isolation is reviewed and implemented. Windows spawn is tested offline; a real macOS check remains pending.

See [docs/fixed-plan.md](docs/fixed-plan.md) for protocol, justified changes, and validation evidence; [docs/setup.md](docs/setup.md) covers detailed usage.

Offline tests: `python -m unittest discover -s tests -v`. Commit or push only when explicitly instructed.
