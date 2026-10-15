"""Cross-process resource ownership for declared local shared resources."""
from contextlib import ExitStack, contextmanager

from .rate_limit import RequestGate
from .selection import ROOT, digest


@contextmanager
def resource_locks(names, cancel=None):
    # Globally ordered acquisition prevents deadlocks across multi-server tasks.
    with ExitStack() as stack:
        for name in sorted(set(names)):
            gate = RequestGate(ROOT / ".runtime/experiments/resources" / (digest(name) + ".json"),
                               {}, cancel=cancel)
            stack.enter_context(gate.lock())
        yield
