# PE6203 Project 4

Compare **No Update**, **Full Rewrite**, and **Selective Patch** under tool evolution.
Forked from [Octobrist/MCPEvol-Bench](https://github.com/Octobrist/MCPEvol-Bench) at `888c779a0fe735f612ca62bdd1fdd7c9e6bf8701`; see its [original README](https://github.com/Octobrist/MCPEvol-Bench/blob/888c779a0fe735f612ca62bdd1fdd7c9e6bf8701/README.md).

## Start

Use Python 3.11+ and Node.js 24. Create a virtual environment with your installed Python command (`python`, `python3`, or Windows `py`). Activate `.venv/Scripts/Activate.ps1` in PowerShell or `source .venv/bin/activate` on macOS/Linux. Then use `python` consistently.

For the current LangChain/knowledge experiment, install the standalone memory environment:

```text
python -m pip install -r requirements-memory.txt
npm install --prefix .runtime @1mcp/agent@0.39.1
```

Copy `.env.example` to `.env`, fill in the credentials referenced by the selected JSON profile, download/extract the three [tool bundles](https://huggingface.co/datasets/anonymous2233/evol-servers/tree/main), and generate local paths with `python scripts/prepare_local_config.py`. Full instructions: [docs/setup.md](docs/setup.md).

```text
python -m custom.experiment validate --config config/knowledge-evolution-formal.json
python -m custom.experiment check --config config/knowledge-evolution-formal.json
python -m custom.experiment run --config config/knowledge-evolution-formal.json --parallel --workers 10
```

The formal knowledge profile uses **17 tasks, three versions, three Agent repeats and five Judge attempts per trajectory**. Shared Early outcomes give 459 logical conditions, 357 actual trajectories and 1,785 planned Judge slots. The catalog-only profile is `config/experiment.json`, using a separate `requirements-api.txt` environment. The upstream full environment remains in `requirements.txt`.

## Member interfaces

- **Role 1:** catalog strategy plugin in `src/custom/experiment/selective_patch.py`; strategy-owned knowledge updates in `experience_state.py` use the same builder/validator for FR and SP.
- **Role 3:** select original IDs and maintain classifications in `config/subsets/selected_tasks.json`. Original tasks and 201 candidate IDs are in `src/custom/data/test_cases/`; fixture inputs are in `anotation_path/`. Do not rewrite task content.
- **Experiment settings:** edit the selected `config/*.json` profile. Models, repeats, provider pools and isolation policies are configuration fields. Formal profiles use `glm-4-flash-250414` for Actor/Judge and `openai/gpt-6-luna` for knowledge updates.
- **Tools:** `servers/{original,iter3,iter5}_servers/`; machine-specific routes are generated under `config/local/` and remain ignored.
- **Results:** start with [results/index.json](results/index.json). Each retained run contains its manifest, raw records and provenance. Historical committed archives remain available; formal scores are unchanged.

## Final case evidence

Original Task 9 is part of the frozen 17-task set. Its retained ten-group Late comparison uses temperature 0.2 and frozen FR snapshot repeat 2. Actual log reading and plan creation succeeded **3/10** with FR, **10/10** after restoring five unchanged-tool records, and **0/10** with an equal-length JSON key-order control. All 30 executions completed without infrastructure failures; no Judge or updater was called.

This is a local case under complete-library injection. It supports context-mediated regression from unnecessary rewriting, without identifying a unique sentence or establishing benchmark-wide superiority. Exact traces, input checks and limitations are in the [case review](results/20261029T113248.805747Z_Kevin/task-9-confirmation-review.json).

```text
python -m custom.experiment counterfactual-check --source-experiment results/20261026T084527.010290Z_Kevin --task-id 9 --snapshot-repeat 2 --repeats 10 --order-control
```

The case command uses the normal agent loop, fresh state per execution and matched paths within each group. It writes a separate result and leaves historical scores intact.

Tests: `python -m unittest discover -s tests -v`. Windows has been tested; real macOS/Linux tool-runtime validation remains pending. New maintained code and documentation are English; original benchmark data, frozen knowledge, tool-language matching and historical traces retain their original languages for reproducibility. Commit or push only when explicitly requested.
