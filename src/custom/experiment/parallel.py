"""Bounded spawn pool, task isolation, durable acknowledgements, and stage barriers."""
from collections import deque
import multiprocessing as mp
from multiprocessing.connection import wait
import os
import time

from .core import run_episode, run_trajectory
from .errors import Cancelled, CheckpointFailure
from .results import episode_id, identity, safe_error
from .runtime import OwnedJob, reap_orphans
from .selection import STAGES


def episode_worker(connection, cancel, ready):
    if os.name != "nt":
        os.setsid()
    ready.wait()

    def emit(event):
        try:
            connection.send(("event", event))
            if connection.recv() != "saved":
                raise CheckpointFailure("Parent did not acknowledge a durable checkpoint")
        except (EOFError, OSError) as exc:
            raise CheckpointFailure("Parent writer disconnected") from exc

    try:
        while True:
            spec = connection.recv()
            if spec is None:
                return
            try:
                run_trajectory(spec, emit, cancel)
                connection.send(("done", None))
            except Cancelled:
                connection.send(("cancelled", None))
                return
            except BaseException as exc:
                connection.send(("failed", safe_error(exc)))
                return
    except (EOFError, OSError):
        return
    finally:
        connection.close()


def supervise(specs, store, workers, shutdown_timeout):
    if specs and all(all(spec['episode']['stages'].get(stage, {}).get('status') == 'ready'
                         for stage in STAGES) for spec in specs):
        return supervise_prepared(specs, store, workers, shutdown_timeout)
    for spec in specs:
        run_episode(spec, store.apply, dispatch=lambda jobs: supervise_stage(
            jobs, store, workers, shutdown_timeout))


def supervise_prepared(specs, store, workers, shutdown_timeout):
    """Frozen states need no trajectory-to-trajectory learning; only shared Early is a barrier."""
    early, evolved = [], []
    for spec in specs:
        eid = episode_id(spec['strategy'], spec['repeat'])
        store.apply({'kind': 'episode', 'episode': eid, 'status': 'running'})
        for stage in STAGES:
            snapshot = spec['episode']['stages'][stage]
            for task in spec['tasks']:
                key = identity(spec['strategy'], stage, task['idx'], spec['repeat'])
                if store.records['trajectories'][key].get('shared_from'):
                    continue
                job = {**spec, 'task': task, 'stage': stage, 'snapshot': snapshot,
                       'knowledge': snapshot['knowledge'],
                       'experience_state': snapshot.get('experience_state')}
                (early if stage == STAGES[0] else evolved).append(job)
    store.event('parallel_schedule', mode='frozen_snapshots_two_waves',
                early_jobs=len(early), evolved_jobs=len(evolved), workers=workers)
    supervise_stage(early, store, workers, shutdown_timeout)
    store.save()  # Publish the common Early outcomes before all independent evolved trajectories.
    supervise_stage(evolved, store, workers, shutdown_timeout)
    for spec in specs:
        store.apply({'kind': 'episode', 'episode': episode_id(spec['strategy'], spec['repeat']),
                     'status': 'completed'})


def supervise_stage(specs, store, workers, shutdown_timeout):
    """Only the parent writes; every Agent and scoring job owns one trajectory."""
    context = mp.get_context("spawn")
    pending, active = deque(), {}
    cancel = context.Event()
    for spec in specs:
        key = identity(spec["strategy"], spec["stage"], spec["task"]["idx"], spec["repeat"])
        row = store.records["trajectories"][key]
        if row["status"] in ("pending", "running"):
            pending.append({**spec, "key": key, "records": {key: row},
                            "phase": "judge" if row["agent_status"] == "completed" else "agent"})

    def assign(connection, spec):
        item = active[connection]
        item.update(spec=spec, events=[], retiring=False)
        connection.send(spec)

    def launch():
        parent, child = context.Pipe()
        ready = context.Event()
        process = context.Process(target=episode_worker, args=(child, cancel, ready))
        job = OwnedJob()
        try:
            process.start()
            child.close()
            job.assign(process.pid)
            active[parent] = {"process": process, "job": job, "spec": None,
                              "events": [], "retiring": False}
            ready.set()
            assign(parent, pending.popleft())
        except BaseException:
            if process.pid:
                process.terminate()
                process.join(5)
            job.close()
            parent.close()
            child.close()
            raise

    def recover(item, reason, error=None):
        spec = item["spec"]
        if spec is None:
            return
        eid = episode_id(spec["strategy"], spec["repeat"])
        store.event(reason, episode=eid, trajectory=spec["key"], error=error)
        store.recover(eid, reason=reason, trajectory=spec["key"])
        item["spec"] = None

    def handle(connection):
        item = active[connection]
        try:
            kind, data = connection.recv()
        except (EOFError, OSError):
            item["eof"] = True
            return
        if kind == "event":
            item["events"].append(data)
            store.apply(data)
            connection.send("saved")
            return
        if kind == "done":
            spec = item["spec"]
            row = store.records["trajectories"][spec["key"]]
            if spec["phase"] == "agent" and row["agent_status"] == "completed" and not spec.get('actor_only'):
                pending.append({**spec, "records": {spec["key"]: row}, "phase": "judge"})
            reap_orphans(item["events"])
            item["spec"] = None
        else:
            recover(item, "worker_cancelled" if kind == "cancelled" else "worker_failed", data)
            item["retiring"] = True

    def close(connection):
        item = active.pop(connection)
        item["process"].join()
        item["job"].close()
        reap_orphans(item["events"])
        connection.close()

    try:
        while pending or active:
            for connection, item in list(active.items()):
                if item["spec"] is None and not item["retiring"]:
                    if pending:
                        assign(connection, pending.popleft())
                    else:
                        connection.send(None)
                        item["retiring"] = True
            while pending and len(active) < workers:
                launch()
            if not active:
                break
            for connection in wait(list(active), timeout=.2):
                handle(connection)
            for connection, item in list(active.items()):
                process = item["process"]
                if process.exitcode is None:
                    continue
                while not item.get("eof"):
                    try:
                        if not connection.poll():
                            break
                    except (EOFError, OSError):
                        item["eof"] = True
                        break
                    handle(connection)
                if item["spec"] is not None:
                    recover(item, "worker_crash", {"exit_code": process.exitcode})
                close(connection)
    except BaseException:
        cancel.set()
        deadline = time.monotonic() + shutdown_timeout
        while active and time.monotonic() < deadline:
            for connection in wait(list(active), timeout=.1):
                try:
                    handle(connection)
                except (EOFError, OSError):
                    pass
            for connection, item in list(active.items()):
                if item["process"].exitcode is not None:
                    close(connection)
        raise
    finally:
        cancel.set()
        for connection, item in list(active.items()):
            process = item["process"]
            if process.is_alive():
                process.terminate()
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
            item["job"].close()
            reap_orphans(item["events"])
            connection.close()
