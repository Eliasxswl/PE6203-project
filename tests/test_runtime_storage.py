"""Disposable runtime cleanup preserves evidence, isolation and original inputs."""
from contextlib import nullcontext
from copy import deepcopy
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from custom.experiment.errors import ExecutionFailure
from custom.experiment.runtime import LiveRuntime, cleanup_runtime_data
from custom.experiment.selection import ROOT, load_config
from custom.experiment.results import atomic_json


class RuntimeStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".runtime")
        self.directory = Path(self.temp.name)
        self.root_patch = patch("custom.experiment.runtime.ROOT", self.directory)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(self.temp.cleanup)
        self.config = load_config(ROOT / "config/experiment.json")
        self.runtime_root = self.directory / ".runtime/r"
        self.runtime_root.mkdir(parents=True)
        self.original = self.directory / "official-fixtures"
        self.original.mkdir()
        (self.original / "original.txt").write_text("original", encoding="utf-8")

    def runtime(self):
        runtime = LiveRuntime(self.config, "original", [])
        runtime.directory.mkdir()
        for name in ("workspace", "home", "tmp"):
            (runtime.directory / name).mkdir()
            (runtime.directory / name / "state.txt").write_text("private state", encoding="utf-8")
        (runtime.directory / "mcp.json").write_text("{}", encoding="utf-8")
        (runtime.directory / "service.log").write_text("diagnostic evidence", encoding="utf-8")
        return runtime

    def test_normal_exit_removes_only_disposable_state_and_is_idempotent(self):
        runtime = self.runtime()
        runtime.__exit__(None, None, None)
        for name in ("workspace", "home", "tmp"):
            self.assertFalse((runtime.directory / name).exists())
        self.assertEqual((runtime.directory / "service.log").read_text(), "diagnostic evidence")
        self.assertTrue((runtime.directory / "mcp.json").is_file())
        self.assertEqual((self.original / "original.txt").read_text(), "original")
        self.assertEqual(cleanup_runtime_data(runtime.directory), [])

    def test_debug_option_preserves_all_state(self):
        runtime = self.runtime()
        runtime.config = deepcopy(self.config)
        runtime.config["runtime"]["keep_workspaces"] = True
        runtime.__exit__(None, None, None)
        self.assertTrue((runtime.directory / "workspace/state.txt").exists())

    def test_startup_failure_also_cleans_partial_fixture_copy(self):
        runtime = LiveRuntime(self.config, "original", [])
        def fail_prepare(*args):
            workspace = runtime.directory / "workspace"
            workspace.mkdir()
            (workspace / "partial.txt").write_text("partial", encoding="utf-8")
            raise ExecutionFailure("Injected fixture preparation failure")
        with patch("custom.experiment.isolation.resource_locks", return_value=nullcontext()), \
             patch("custom.experiment.runtime.prepare_config", side_effect=fail_prepare):
            with self.assertRaisesRegex(ExecutionFailure, "Injected"):
                runtime.__enter__()
        self.assertFalse((runtime.directory / "workspace").exists())
        self.assertIsNone(runtime.resource_guard)

    def test_cleanup_runs_even_if_stopped_event_writer_fails(self):
        runtime = self.runtime()
        runtime.registered = True
        runtime.owner_callback = Mock(side_effect=RuntimeError("writer unavailable"))
        with self.assertRaisesRegex(RuntimeError, "writer unavailable"):
            runtime.__exit__(None, None, None)
        self.assertFalse((runtime.directory / "workspace").exists())

    def test_service_is_waited_before_deleting_its_workspace(self):
        runtime = self.runtime()
        runtime.proc, runtime.job = Mock(), Mock()
        runtime.proc.pid = 12345
        def wait(**kwargs):
            self.assertTrue((runtime.directory / "workspace").exists())
            return 0
        runtime.proc.wait.side_effect = wait
        with patch("custom.experiment.runtime.os.killpg", create=True):
            runtime.__exit__(None, None, None)
        runtime.proc.wait.assert_called_once()
        self.assertFalse((runtime.directory / "workspace").exists())

    def test_unconfirmed_shutdown_keeps_workspace(self):
        runtime = self.runtime()
        runtime.proc, runtime.job = Mock(), Mock()
        runtime.proc.pid = 12345
        runtime.proc.wait.side_effect = subprocess.TimeoutExpired("owned-service", 1)
        with patch("custom.experiment.runtime.os.killpg", create=True):
            with self.assertRaises(subprocess.TimeoutExpired):
                runtime.__exit__(None, None, None)
        self.assertTrue((runtime.directory / "workspace").exists())

    def test_cleanup_error_is_logged_and_guards_still_release(self):
        runtime = self.runtime()
        runtime.resource_guard = guard = MagicMock()
        with patch("custom.experiment.runtime.shutil.rmtree", side_effect=OSError("locked state")), \
             self.assertLogs("custom.experiment.runtime", level="WARNING") as logged:
            runtime.__exit__(ValueError, ValueError("original failure"), None)
        self.assertIn("cleanup deferred", logged.output[0])
        guard.__exit__.assert_called_once()
        self.assertIsNone(runtime.resource_guard)
        self.assertTrue((runtime.directory / "workspace").exists())

    def test_refuses_unowned_paths_or_runtime_root(self):
        for path in (self.original, self.runtime_root, self.runtime_root / "../official-fixtures",
                     self.runtime_root / "not-an-owned-id"):
            with self.assertRaises(ValueError):
                cleanup_runtime_data(path)
        self.assertTrue((self.original / "original.txt").exists())

    def test_readonly_files_can_be_removed(self):
        runtime = self.runtime()
        path = runtime.directory / "workspace/state.txt"
        path.chmod(stat.S_IREAD)
        try:
            cleanup_runtime_data(runtime.directory)
            self.assertFalse(path.exists())
        finally:
            if path.exists():
                path.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_redirected_state_never_deletes_original_fixture(self):
        runtime = LiveRuntime(self.config, "original", [])
        runtime.directory.mkdir()
        try:
            os.symlink(self.original, runtime.directory / "workspace", target_is_directory=True)
        except OSError:
            self.skipTest("Creating a directory symlink is not permitted")
        with self.assertRaises(ValueError):
            cleanup_runtime_data(runtime.directory)
        self.assertTrue((self.original / "original.txt").exists())

    @unittest.skipUnless(os.name == "nt", "Windows transient sharing violation")
    def test_windows_cleanup_retries_only_the_same_private_tree(self):
        runtime = self.runtime()
        from shutil import rmtree
        error = PermissionError("Transient sharing violation")
        error.winerror = 32
        calls = []
        def remove(path, **kwargs):
            calls.append(path)
            if len(calls) == 1:
                raise error
            return rmtree(path, **kwargs)
        with patch("custom.experiment.runtime.shutil.rmtree", side_effect=remove), \
             patch("custom.experiment.runtime.time.sleep"):
            cleanup_runtime_data(runtime.directory)
        self.assertEqual(calls[0], calls[1])
        self.assertFalse((runtime.directory / "workspace").exists())

    def test_keep_workspaces_requires_an_explicit_boolean(self):
        config_path = self.directory / "config.json"
        for value in (False, True, "false", 0, None):
            config = deepcopy(self.config)
            config["runtime"]["keep_workspaces"] = value
            atomic_json(config_path, config)
            if type(value) is bool:
                self.assertEqual(load_config(config_path)["runtime"]["keep_workspaces"], value)
            else:
                with self.assertRaisesRegex(ValueError, "keep_workspaces"):
                    load_config(config_path)


if __name__ == "__main__":
    unittest.main()
