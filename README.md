# PE6203 Project 4

Compare **No Update**, **Full Rewrite**, and **Selective Patch** across Early, Middle, and Late tool environments.

Forked from [Octobrist/MCPEvol-Bench](https://github.com/Octobrist/MCPEvol-Bench), starting at `888c779a0fe735f612ca62bdd1fdd7c9e6bf8701`. See the [upstream README](https://github.com/Octobrist/MCPEvol-Bench/blob/888c779a0fe735f612ca62bdd1fdd7c9e6bf8701/README.md) for benchmark details.

## Setup

Use **Python 3.12 and Node.js 24**. Create a virtual environment once; activate it in every terminal used below. Skip creation if `.venv` already exists.

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

The remaining commands are shared; run them from the repository root unless stated otherwise:

```text
python -m pip install -r requirements-api.txt
npm install --prefix .runtime @1mcp/agent@0.39.1
```

Copy `.env.example` to `.env` once, then edit:

```ini
BIGMODEL_API_KEY=your-key
BIGMODEL_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
BIGMODEL_MODEL=glm-4-flash-250414
BIGMODEL_JUDGE_MODEL=
BENCH_JUDGE_RUNS=5
```

Python entry points load `.env` automatically; existing environment variables take precedence. A blank judge model uses the agent model. Keep settings fixed across strategies. Do not commit `.env`.

**Dependencies:** install `requirements-api.txt` for our API-based workflow. `requirements.txt` is the upstream full/local-model environment, retained for reference; do not install both. Windows-only packages use platform markers. Windows has been smoke-tested; macOS commands and path resolution are provided but not yet tested on a Mac. Some downloaded tools may need OS-specific dependencies.

## Tasks and tools

| Location | Contents |
| --- | --- |
| `src/custom/data/test_cases/test_cases.json` | Task records; start with a small development subset |
| `src/custom/data/test_cases/chosen_idx.json` | 201 candidate IDs; confirm the final subset |
| `anotation_path/` | Task workspace and input files |
| `servers/1mcp_config/{original,iter3,iter5}/mcp.json` | Upstream server templates |
| `config/local/` | Generated paths for your own machine; excluded from Git |
| `config/experiment.json` | 3 agent runs and 5 judge attempts per trajectory |

Download `original_servers.zip`, `iter3_servers.zip`, and `iter5_servers.zip` from [the tool bundles](https://huggingface.co/datasets/anonymous2233/evol-servers/tree/main) into `servers/downloads/`, then run:

```text
python scripts/extract_servers.py original
python scripts/extract_servers.py iter3
python scripts/extract_servers.py iter5
python scripts/prepare_local_config.py
```

`original` = Early, `iter3` = Middle, `iter5` = Late. Downloads and extracted tools are local dependencies, not committed. Regenerate configs on each machine.

## Start and run

With the virtual environment active, verify one real tool server without calling a model:

```text
# Terminal 1, repository root; keep running
node .runtime/node_modules/@1mcp/agent/build/index.js serve --host 127.0.0.1 --port 3050 --config config/local/smoke.json --config-dir config/local
# Terminal 2, repository root
python scripts/probe_mcp.py
```

Use `smoke-iter3.json` / port `3053` or `smoke-iter5.json` / port `3055` for another stage, and pass the matching `--url` to the probe. Test stages sequentially when using the same config directory. Stop the server with Ctrl+C. Smoke configurations expose one server, not a full task environment.

For a real task, create `src/custom/data/test_cases/dev-subset.json` from task records and keep only its required servers in `config/local/original.json`. Restart terminal 1 with `--config config/local/original.json`. In terminal 2:

```text
cd src
python -m custom.real_mcp.tool_level_test --step 3 --test_case_file custom/data/test_cases/dev-subset.json --output_path custom/data/local_output --mcp_server_url http://127.0.0.1:3050/mcp
```

This calls the model. Results go to `src/custom/data/local_output/<model>/ANSWER/`. Middle/Late runs use `--step 4` and a verified `--mutation_path`; check stage/task mappings first. PowerShell convenience wrappers remain available in `scripts/` but are optional.

## Integration and evaluation

- Agent loop: [`SimpleOpenAIAgent.py`](src/custom/agents/SimpleOpenAIAgent.py), `ChatModel.run_with_server()`.
- Task loading/tool metadata: [`tool_level_test.py`](src/custom/real_mcp/tool_level_test.py).
- Strategy integration to implement: update persistent tool knowledge and inject it into the Agent before execution. No stable adapter interface exists yet.
- Scoring: [`evaluation.py`](src/custom/analysis/answer/evaluation.py), fixed **5 attempts per trajectory**, no failure top-up. Use `python -m custom.analysis.answer.evaluation` from `src/`; supply `--answer_path` and `--task_selection`. Selection JSON: `{"samples":[{"idx":42}]}`.
- ECS: [`evolutionary_volatility.py`](src/custom/analysis/answer/evolutionary_volatility.py).

Automatic 3-run scheduling, workspace reset, adaptation strategies, and cost aggregation remain to be implemented. Model-backed benchmark execution is not yet validated.

Offline tests, from the repository root:

```text
python -m unittest discover -s tests -v
```

See [Windows setup notes](SETUP-WINDOWS.md) for previous local checks and [submission scope](SUBMISSION-SCOPE.md) for deliverables.

See [group changes](GROUP-CHANGES.md) for a summary of differences from upstream.
