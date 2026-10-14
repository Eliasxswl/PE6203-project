"""Small spawn supervisor with durable event acknowledgements and owned workers."""
from collections import deque
import multiprocessing as mp
from multiprocessing.connection import wait
import os
import time

from .core import run_episode
from .errors import Cancelled, CheckpointFailure
from .results import episode_id, safe_error
from .runtime import OwnedJob, reap_orphans


def episode_worker(spec, connection, cancel, ready):
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
        run_episode(spec, emit, cancel)
        connection.send(("done", None))
    except Cancelled:
        connection.send(("cancelled", None))
    except BaseException as exc:
        try:
            connection.send(("failed", safe_error(exc)))
        except (EOFError, OSError):
            pass
    finally:
        connection.close()


def supervise(specs, store, workers, shutdown_timeout):
    context = mp.get_context("spawn")
    pending, active = deque(specs), {}
    cancel = context.Event()
    stopped = None

    def launch(spec):
        parent, child = context.Pipe()
        ready = context.Event()
        process = context.Process(target=episode_worker, args=(spec, child, cancel, ready))
        job = OwnedJob()
        try:
            process.start()
            child.close()
            job.assign(process.pid)
            active[parent] = {"process": process, "job": job, "spec": spec, "done": False}
            ready.set()
        except BaseException:
            if process.pid:
                process.terminate()
                process.join(5)
            job.close()
            parent.close()
            child.close()
            raise

    def handle(connection):
        item = active[connection]
        try:
            kind, data = connection.recv()
        except EOFError:
            item["eof"] = True
            return
        eid = episode_id(item["spec"]["strategy"], item["spec"]["repeat"])
        if kind == "event":
            store.apply(data)
            connection.send("saved")
        elif kind == "done":
            item["done"] = True
        else:
            item["done"] = True
            store.event("worker_cancelled" if kind == "cancelled" else "worker_failed", episode=eid, error=data)
            store.recover(eid, reason="worker_cancelled" if kind == "cancelled" else "worker_failed")
            store.records["episodes"][eid]["status"] = "interrupted" if kind == "cancelled" else "failed"
            store.save()

    try:
        while pending or active:
            while pending and len(active) < workers:
                launch(pending.popleft())
            for connection in wait(list(active), timeout=.2):
                handle(connection)
            for connection, item in list(active.items()):
                process = item["process"]
                if process.exitcode is None:
                    continue
                # Drain the terminal event before classifying a normal process exit as a crash.
                while not item.get("eof") and connection.poll():
                    try:
                        handle(connection)
                    except (EOFError, OSError):
                        break
                    if item["done"]:
                        break
                if not item["done"]:
                    eid = episode_id(item["spec"]["strategy"], item["spec"]["repeat"])
                    store.event("worker_crash", episode=eid, exit_code=process.exitcode)
                    store.recover(eid, reason="worker_crash")
                    store.records["episodes"][eid]["status"] = "failed"
                    store.save()
                process.join()
                item["job"].close()
                reap_orphans(store.records["events"], episode_id(item["spec"]["strategy"], item["spec"]["repeat"]))
                connection.close()
                del active[connection]
    except BaseException as exc:
        stopped = exc
        cancel.set()
        deadline = time.monotonic() + shutdown_timeout
        # Drain and acknowledge already issued requests during cooperative shutdown.
        while active and time.monotonic() < deadline:
            for connection in wait(list(active), timeout=.1):
                try:
                    handle(connection)
                except (EOFError, OSError):
                    pass
            for connection, item in list(active.items()):
                if item["process"].exitcode is not None:
                    item["process"].join()
                    item["job"].close()
                    connection.close()
                    del active[connection]
        raise
    finally:
        cancel.set()
        for connection, item in active.items():
            process = item["process"]
            if process.is_alive():
                process.terminate()
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
            item["job"].close()
            reap_orphans(store.records["events"], episode_id(item["spec"]["strategy"], item["spec"]["repeat"]))
            connection.close()
