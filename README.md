# PE6203 Project 4

Tool-harness adaptation: compare **No Update**, **Full Rewrite**, and **Selective Patch** across Early, Middle, and Late tool environments.

Forked from [Octobrist/MCPEvol-Bench](https://github.com/Octobrist/MCPEvol-Bench), starting at commit `888c779a0fe735f612ca62bdd1fdd7c9e6bf8701`. See the [upstream README](https://github.com/Octobrist/MCPEvol-Bench/blob/888c779a0fe735f612ca62bdd1fdd7c9e6bf8701/README.md) for benchmark details.

## Setup

Use **Windows PowerShell, Python 3.12, and Node.js 24**. Run setup commands from the repository root. Skip the environment creation step if `.venv` already exists.

```powershell
py -3.12 -m venv .venv
& .venv\Scripts\python.exe -m pip install -r requirements-api.lock.txt
npm.cmd install --prefix .runtime @1mcp/agent@0.39.1
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Edit `.env` once; Python entry points load it automatically. Existing environment variables take precedence.

```ini
BIGMODEL_API_KEY=your-key
BIGMODEL_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
BIGMODEL_MODEL=glm-4-flash-250414
BIGMODEL_JUDGE_MODEL=
BENCH_JUDGE_RUNS=5
```

The judge model defaults to the agent model when left blank. Keep model settings fixed across strategies. `.env`, downloaded tools, and local runtime files are excluded from Git.

## Tasks and tools

| Location | Contents |
| --- | --- |
| `src/custom/data/test_cases/test_cases.json` | Task records; select a small development subset first |
| `src/custom/data/test_cases/chosen_idx.json` | 201 candidate task IDs; confirm the final experimental subset |
| `anotation_path/` | Task workspace and input files |
| `servers/1mcp_config/{original,iter3,iter5}/mcp.json` | Upstream server configuration templates |
| `config/local/` | Generated machine-specific server configurations |
| `config/experiment.json` | Protocol: 3 agent runs, 5 judge attempts per trajectory |

Download `original_servers.zip`, `iter3_servers.zip`, and `iter5_servers.zip` from [the upstream tool bundles](https://huggingface.co/datasets/anonymous2233/evol-servers/tree/main) into `servers/downloads/`, then prepare the local environments:

```powershell
& .venv\Scripts\python.exe scripts\extract_servers.py original
& .venv\Scripts\python.exe scripts\extract_servers.py iter3
& .venv\Scripts\python.exe scripts\extract_servers.py iter5
& .venv\Scripts\python.exe scripts\prepare_local_config.py
```

`original` = Early, `iter3` = Middle, `iter5` = Late. Bundles are already prepared on the current development machine.

## Start and run

First verify MCP connectivity without using a model. Keep terminal 1 running:

```powershell
# Terminal 1, repository root
& .\scripts\start_mcp.ps1 -Stage smoke -Port 3050
# Terminal 2, repository root
& .venv\Scripts\python.exe scripts\probe_mcp.py
```

Use `smoke-iter3` / port `3053` or `smoke-iter5` / port `3055` for other stages. Smoke configurations expose only one server, not a full task environment. Stop a server with Ctrl+C.

To run a benchmark task, select records into `src/custom/data/test_cases/dev-subset.json` and retain only their required servers in `config/local/original.json`. Start with one task:

```powershell
# Terminal 1: stop the smoke server first
& .\scripts\start_mcp.ps1 -Stage original -Port 3050
# Terminal 2, repository root; this command calls the model
& .\scripts\run_agent.ps1 -TaskFile 'custom/data/test_cases/dev-subset.json' -Stage original
```

Results go to `src/custom/data/local_output/<model>/ANSWER/`. Middle/Late runs also require a verified `-MutationPath`; check version and task mappings before running them.

## Integration and evaluation

- Agent loop: [`SimpleOpenAIAgent.py`](src/custom/agents/SimpleOpenAIAgent.py), `ChatModel.run_with_server()`.
- Task loading and tool metadata: [`tool_level_test.py`](src/custom/real_mcp/tool_level_test.py).
- Planned strategy integration: update persistent tool knowledge, then inject the resulting knowledge into the Agent before execution. The knowledge format and adapter interface are **not implemented yet**.
- Scoring: [`evaluation.py`](src/custom/analysis/answer/evaluation.py), fixed **5 attempts per trajectory**, with no failure top-up. Pass `--task_selection` explicitly using a JSON file shaped as `{"samples":[{"idx":42}]}`.
- Cross-version ECS: [`evolutionary_volatility.py`](src/custom/analysis/answer/evolutionary_volatility.py).

The protocol specifies **3 independent agent runs**; automatic repeat scheduling, workspace reset, strategy integration, and cost aggregation remain to be implemented. Model-backed benchmark execution is not yet validated. Do not treat smoke checks as experiment results.

Offline checks, from the repository root:

```powershell
& .venv\Scripts\python.exe -m unittest discover -s tests -v
```

For detailed commands, see [Windows setup](SETUP-WINDOWS.md); for deliverables and remaining work, see [submission scope](SUBMISSION-SCOPE.md).
