"""The sole formal experiment entry point; importing this module starts no work."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

from . import adapters
from .core import initial_snapshot, run_episode
from .errors import Cancelled, CheckpointFailure
from .results import Store, create, episode_id, safe_error, writer_lock
from .runtime import ALIASES, policy_for, reap_orphans
from .selection import ROOT, STAGES, fingerprints, load_config, provider_options, read_json, select, tasks


def validate(config):
    adapters.load_plugins(config)
    from custom.utils import model_config
    model_config.judge_runs()  # The reused judge formatter imports this legacy fixed-five setting.
    task_list = tasks(config)
    warnings = []
    if config.get("mode", "live") == "live":
        runtime = config["runtime"]
        mapping = runtime.get("evolution_files", {})
        overlay = runtime.get("catalog_source", "evolution_overlay") == "evolution_overlay"
        if set(mapping) != set(STAGES) or (overlay and runtime.get("metadata_verified") is not True):
            raise ValueError("Live execution requires a verified, explicit stage/evolution mapping")
        if mapping["original"] or (overlay and any(not mapping[stage] for stage in ("iter3", "iter5"))):
            raise ValueError("Early uses no overlays; provide ordered evolution files for Middle and Late")
        for stage, paths in mapping.items():
            if not isinstance(paths, list) or len(set(paths)) != len(paths):
                raise ValueError("Evolution files must be ordered lists without duplicates")
            for path in paths:
                if not (ROOT / path).is_file():
                    raise ValueError(f"Missing evolution metadata for {stage}")
        for role in ("agent", "judge"):
            for provider in provider_options(config, role):
                model_config.role_api_key(role, provider)
        if set(config["runtime"].get("configs", {})) != set(STAGES):
            raise ValueError("Provide a local configuration for every stage")
        for stage, name in config["runtime"]["configs"].items():
            local = read_json(ROOT / name)
            if not isinstance(local.get("mcpServers"), dict):
                raise ValueError(f"Invalid local server configuration: {stage}")
        servers = sorted({ALIASES.get(s, s) for t in task_list for s in t["servers"]})
        for server in servers:
            try:
                policy_for(server, config)
            except Exception as exc:
                warnings.append(str(exc))
    return task_list, warnings


def specifications(store, config, task_list):
    from custom.utils.test_utils import offset_date
    prompt_time = store.manifest.get("prompt_time")
    if prompt_time is None:
        from .results import atomic_json
        store.manifest["prompt_time"] = prompt_time = str(offset_date(0))
        atomic_json(store.path / "experiment.json", store.manifest)
    if not store.records.get("initial_snapshot") or store.records["initial_snapshot"]["status"] != "ready":
        initial_snapshot(config, task_list, store.apply)
    specs = []
    owner = store.manifest.get("shared_early", {}).get("owner_strategy")
    ordered = sorted(config["strategies"], key=lambda strategy: strategy != owner)
    for strategy in ordered:
        for repeat in range(config["agent_repeats"]):
            eid = episode_id(strategy, repeat)
            rows = {key: row for key, row in store.records["trajectories"].items()
                    if row["identity"]["strategy"] == strategy and row["identity"]["repeat"] == repeat}
            if not any(row["status"] in ("pending", "running") for row in rows.values()):
                continue
            specs.append({"config": config, "tasks": task_list, "strategy": strategy, "repeat": repeat,
                          "episode": store.records["episodes"][eid], "records": rows, "prompt_time": prompt_time,
                          "initial_snapshot": store.records["initial_snapshot"]})
    return specs


def execute(config, task_list, experiment=None, parallel=False, workers=1, warnings=None):
    if parallel and config.get("mode", "live") == "live":
        for server in {ALIASES.get(s, s) for task in task_list for s in task["servers"]}:
            policy = policy_for(server, config)
            if policy.get("concurrency") not in ("private", "readonly", "exclusive"):
                raise ValueError(f"Parallel isolation is not declared for {server}")
            if policy["concurrency"] == "exclusive" and not policy.get("shared_resources"):
                raise ValueError(f"Exclusive backend requires shared_resources: {server}")
    expected = fingerprints(config)
    if experiment is None:
        experiment = create(config, task_list, expected, parallel, workers, warnings)
    experiment = Path(experiment).resolve()
    with writer_lock(experiment):
        store = Store(experiment)
        if store.manifest["fingerprints"] != expected:
            raise ValueError("Code/config/data fingerprints changed; create a new experiment")
        if store.manifest["execution"] != {"parallel": parallel, "workers": workers}:
            raise ValueError("Resume must preserve the original execution mode and workers")
        if store.records["status"] == "running":
            store.event("unclean_stop_detected", detail="Previous writer did not record a final stop")
        reap_orphans(store.records["events"])
        store.recover(reason="unclean_stop")
        store.records["status"] = "running"
        resumed = any(e["kind"] == "experiment_started" for e in store.records["events"])
        store.event("experiment_started", resumed=resumed, warnings=warnings or [], writer_pid=os.getpid())
        print(f"Experiment: {experiment}", flush=True)
        try:
            specs = specifications(store, config, task_list)
            if parallel:
                from .parallel import supervise
                supervise(specs, store, workers, config["runtime"]["shutdown_timeout"])
            else:
                for spec in specs:
                    run_episode(spec, store.apply)
        except (KeyboardInterrupt, Cancelled) as exc:
            store.records["status"] = "interrupted"
            store.event("user_termination" if isinstance(exc, KeyboardInterrupt) else "cooperative_cancellation")
            store.recover(reason="user_termination" if isinstance(exc, KeyboardInterrupt) else "cooperative_cancellation")
            store.summarize()
            raise
        except BaseException as exc:
            store.records["status"] = "failed"
            store.event("experiment_fatal_error", error=safe_error(exc))
            store.recover(reason="experiment_fatal_error")
            store.summarize()
            raise
        finally:
            reap_orphans(store.records["events"])
        pending = any(row["status"] in ("pending", "running") for row in store.records["trajectories"].values())
        if fingerprints(config) != expected:
            store.records["status"] = "invalidated"
            store.event("source_drift_detected", detail="Code/config/data changed during execution; scores excluded")
            for row in store.records["trajectories"].values():
                row.update(score=None, score_exclusion_reason="experimental_inputs_changed")
            return experiment, store.summarize()
        failures = any(row["status"] != "completed" or row.get("score") is None for row in store.records["trajectories"].values())
        judge_warnings = any(a["status"] != "completed" for row in store.records["trajectories"].values()
                             for a in row["judge_attempts"])
        store.records["status"] = ("partial" if pending else "completed_with_failures" if failures
                                   else "completed_with_warnings" if judge_warnings else "completed")
        store.event("experiment_stopped", status=store.records["status"])
        return experiment, store.summarize()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the fixed MCPEvol experiment protocol")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("select", "validate", "check", "run", "memory-check", "prepare-memory", "prepare-recovery-memory", "memory-ablation", "memory-causal-check", "expand-memory"):
        command = subparsers.add_parser(name)
        command.add_argument("--config", default="config/experiment.json")
        command.add_argument("--offline", action="store_true", help="Use deterministic providers without network/model calls")
        if name == 'expand-memory':
            command.add_argument('--workers', type=int, default=10)
        if name == 'memory-ablation':
            group = command.add_mutually_exclusive_group(required=True)
            group.add_argument('--task-id', type=int, action='append')
            group.add_argument('--all-selected', action='store_true', help='Use every task in the frozen selection')
            command.add_argument('--parallel', action='store_true', default=False)
            command.add_argument('--workers', type=int, default=1)
        if name == 'memory-causal-check':
            command.add_argument('--workers', type=int, default=1)
            command.add_argument('--suite', choices=['original', 'transfer', 'transfer-templates'], default='original')
        if name == "check":
            command.add_argument("--server", action="append", help="Check selected backends only; repeatable")
            command.add_argument("--stage", choices=STAGES)
            command.add_argument("--skip-models", action="store_true", help="Only check local backends; no model requests")
        if name == "run":
            command.add_argument("--resume", type=Path, help="Continue unstarted work in an existing experiment")
            command.add_argument("--parallel", action="store_true", default=None)
            command.add_argument("--workers", type=int)
    summarize = subparsers.add_parser("summarize")
    summarize.add_argument("--experiment", type=Path, required=True)
    diff = subparsers.add_parser("catalog-diff", help="Read saved catalogs; no network or result changes")
    diff.add_argument("--experiment", type=Path, required=True)
    judge = subparsers.add_parser("judge-check", help="Explicit real-trajectory scoring diagnostic; no tools")
    judge.add_argument("--config", default="config/experiment.json")
    judge.add_argument("--experiment", type=Path, required=True)
    judge.add_argument("--trajectory", required=True, help="strategy/stage/task/repeat from records.json")
    judge.add_argument("--attempts", type=int, default=1, choices=range(1, 6))
    judge.add_argument("--provider-index", type=int, default=0)
    judge.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog-diff":
            from .evidence import archived_tasks, catalog_evidence
            store = Store(args.experiment)
            print(json.dumps(catalog_evidence(store.records, archived_tasks(store.manifest)), indent=2))
            return 0
        if args.command == "summarize":
            with writer_lock(args.experiment):
                result = Store(args.experiment).summarize()
            print(json.dumps(result, indent=2))
            return 0
        config = load_config(ROOT / args.config)
        if args.offline:
            config["mode"] = "offline"
        if args.command == 'expand-memory':
            from .skills import run as expand_memory
            validate(config)
            path, result = expand_memory(config, args.workers)
            print(json.dumps({'experiment': str(path), 'result': result}, indent=2))
            return 0 if result['status'] == 'completed' else 2
        if args.command == 'memory-causal-check':
            if args.suite.startswith('transfer'):
                from .transfer import run as causal_check
                path, result = causal_check(config, args.workers, template_mode=args.suite == 'transfer-templates')
            else:
                from .causal import run as causal_check
                path, result = causal_check(config, args.workers)
            print(json.dumps({'experiment': str(path), 'result': result}, indent=2))
            return 0 if result['status'] == 'completed' else 2
        if args.command == 'run' and 'memory' in config:
            raise ValueError('LangMem is currently a usefulness diagnostic only; use memory-ablation, not a formal evolution run')
        if args.command == 'prepare-recovery-memory':
            if config.get('mode') == 'offline' or config.get('agent_backend') != 'langchain':
                raise ValueError('Verified recovery practice requires the live official agent backend')
            from .recovery_memory import prepare as prepare_recovery
            task_list, warnings = validate(config)
            result = prepare_recovery(config, task_list)
            print(json.dumps({'protocol': result['protocol'], 'memory_sha256': result['memory_sha256'],
                             'memories': len(result['memories']), 'builds': result['builds']}, indent=2))
            return 0
        if args.command in ('memory-check', 'prepare-memory'):
            from .memory import check as memory_check, prepare as prepare_memory
            if config.get('mode') == 'offline':
                raise ValueError('Official memory extraction requires a real model; no simulated success')
            result = memory_check(config) if args.command == 'memory-check' else prepare_memory(config)
            output = result if args.command == 'memory-check' else {key: result[key] for key in
                ('protocol', 'memory_sha256', 'builds', 'versions')}
            if args.command == 'prepare-memory':
                output['memories'] = len(result['memories'])
            print(json.dumps(output, indent=2))
            return 0
        if args.command == "judge-check":
            from .checks import check_judge
            result = check_judge(config, args.experiment, args.trajectory, args.attempts, args.provider_index)
            print(json.dumps(result, indent=2))
            return 0 if result["status"] == "passed" else 2
        if args.command == "select":
            print(json.dumps({"selected_ids": select(config)}))
            return 0
        task_list, warnings = validate(config)
        if args.command == 'memory-ablation':
            from .memory_ablation import run as memory_ablation
            task_ids = [t['idx'] for t in task_list] if args.all_selected else args.task_id
            path, report = memory_ablation(config, task_list, task_ids, args.parallel, args.workers)
            print(json.dumps({'experiment': str(path), 'report': report}, indent=2))
            return 0 if report['status'] == 'completed' else 2
        if args.command == "validate":
            from .readiness import preparation
            fingerprints(config)
            print(json.dumps({"status": "valid", "mode": config["mode"], "tasks": len(task_list),
                              "strategies": config["strategies"], "warnings": warnings,
                              "preparation": preparation(config, warnings)}, indent=2))
            return 0
        if args.command == "check":
            from .checks import check
            result = check(config, task_list, args.server, args.stage, args.skip_models)
            print(json.dumps(result, indent=2))
            return 0 if result["status"] == "passed" else 2
        if args.resume:
            manifest = read_json(args.resume / "experiment.json")
            parallel = manifest["execution"]["parallel"] if args.parallel is None else args.parallel
            workers = manifest["execution"]["workers"] if args.workers is None else args.workers
        else:
            parallel = bool(args.parallel)
            workers = (args.workers or 2) if parallel else 1
            if args.workers is not None and not parallel:
                raise ValueError("--workers requires --parallel")
        if type(workers) is not int or not 1 <= workers <= 32:
            raise ValueError("workers must be between 1 and 32")
        path, aggregate = execute(config, task_list, args.resume, parallel, workers, warnings)
        print(json.dumps({"experiment": str(path), "groups": aggregate["groups"],
                          "completion": aggregate["completion"]}, indent=2))
        return aggregate["completion"]["exit_code"]
    except (ValueError, RuntimeError, OSError, KeyError, CheckpointFailure) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, Cancelled):
        print("Experiment interrupted; unfinished requests will not be replayed.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
