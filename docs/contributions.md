# Code ownership and interfaces

Moved out of the README so the repository front page stays a report and reproduction guide.

- **Role 1:** catalog strategy plugin in `src/custom/experiment/selective_patch.py`; strategy-owned knowledge updates in `experience_state.py` use the same builder/validator for FR and SP.
- **Role 3:** select original IDs and maintain classifications in `config/subsets/selected_tasks.json`. Original tasks and 201 candidate IDs are in `src/custom/data/test_cases/`; fixture inputs are in `anotation_path/`. Do not rewrite task content.
- **Experiment settings:** edit the selected `config/*.json` profile. Models, repeats, provider pools and isolation policies are configuration fields. Formal profiles use `glm-4-flash-250414` for Actor/Judge and `openai/gpt-6-luna` for knowledge updates.
- **Tools:** `servers/{original,iter3,iter5}_servers/`; machine-specific routes are generated under `config/local/` and remain ignored.
- **Results:** start with [../results/index.json](../results/index.json). Each retained run contains its manifest, raw records and provenance. Historical committed archives remain available; formal scores are unchanged.
