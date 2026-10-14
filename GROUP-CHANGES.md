# Group changes relative to upstream

Base: Octobrist/MCPEvol-Bench at 888c779a0fe735f612ca62bdd1fdd7c9e6bf8701.

| Area | Changes and purpose |
| --- | --- |
| Local configuration | Added .env.example and model_config.py. Agent and judge read local credentials and model IDs consistently; environment overrides remain possible. |
| API-mode compatibility | Deferred FastChat imports, removed an unused Unix-only pty import, used the configured API endpoint and compatible token-limit parameter, and supplied an absolute task-workspace path. |
| Judge pipeline | Replaced a missing parser import with an existing parser, delayed MCP connection until execution, made task selection explicit instead of referencing missing real.json, validated score fields, and fixed scoring to 5 attempts without extra retries or failure top-up. Failed attempts remain recorded on resume. |
| Runtime setup | Added tool extraction, machine-specific config generation, MCP probing, and optional PowerShell wrappers. Config generation handles Windows Scripts/.exe/.cmd and macOS bin launchers. |
| Dependencies | requirements-api.txt pins the smaller API-mode dependency set with Windows platform markers. Upstream requirements.txt is retained unchanged; the separate Windows freeze file was consolidated. |
| Experiment protocol | config/experiment.json records 3 agent repeats, 5 judge attempts, the three stages/strategies, and the intended agent model. It is not yet an implemented experiment scheduler. |
| Documentation and checks | Replaced the copied README with a team guide, added setup/submission notes, ignore rules for local files, and offline tests for configuration and bounded scoring. |

Not implemented: persistent tool knowledge, three adaptation strategies, independent workspace reset, repeated-run orchestration, and full cost/result aggregation.

No model-backed benchmark results have been produced. We have verified Windows setup and a small real-tool MCP smoke path across the three downloaded stages; macOS remains to be tested by a teammate.
