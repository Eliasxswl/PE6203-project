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

## Integration and status

- Agent: `src/custom/agents/SimpleOpenAIAgent.py`.
- Runner: `src/custom/real_mcp/tool_level_test.py`.
- Judge: `src/custom/analysis/answer/evaluation.py`.
- Protocol: `config/experiment.json` specifies 3 Agent runs and 5 judge attempts per trajectory.

API text/function checks and a task-9 pilot with 3 Agent trajectories and 15 judge attempts have completed on Windows. The pilot exposed routing and search failures; it is development evidence, not a valid strategy comparison. All three required tools passed separate direct checks. The default judge uses the Agent model.

Outputs: `results/baseline/<stage>/<run-id>/answers/<task-id>.json` and sibling `scores/<task-id>.json`. Results stay local by default. See the setup guide for isolated task-9 preparation and execution.

Persistent tool knowledge, the three adaptation strategies, repeat scheduling, general state reset, and full cost aggregation are pending.

Offline tests: `python -m unittest discover -s tests -v`.
