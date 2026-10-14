"""Offline checks for platform-specific launcher and dependency selection."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
# Reuse pip's bundled marker parser; no extra runtime dependency is needed.
from pip._vendor.packaging.requirements import Requirement
from scripts.prepare_local_config import executable_path

class PlatformSetupTests(unittest.TestCase):
    def test_venv_launcher_locations(self):
        root = Path(__file__).resolve().parents[1]
        log_root = root / 'logs'
        log_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=log_root) as directory:
            temporary_root = Path(directory).resolve()
            self.assertTrue(temporary_root.is_relative_to(log_root.resolve()))
            windows = temporary_root / '.venv/Scripts/uvx.exe'
            macos = temporary_root / '.venv/bin/uvx'
            for path in [windows, macos]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('test launcher', encoding='utf-8')
            self.assertEqual(executable_path('uvx', temporary_root, 'nt'), str(windows))
            self.assertEqual(executable_path('uvx', temporary_root, 'posix'), str(macos))

    def test_npm_launcher_suffix(self):
        with patch('scripts.prepare_local_config.shutil.which', side_effect=lambda name:name) as lookup:
            self.assertEqual(executable_path('npx', Path('.'), 'nt'), 'npx.cmd')
            self.assertEqual(executable_path('npx', Path('.'), 'posix'), 'npx')

    def test_windows_dependency_is_excluded_on_macos(self):
        root = Path(__file__).resolve().parents[1]
        lines = (root / 'requirements-api.txt').read_text(encoding='utf-8').splitlines()
        requirement = next(Requirement(line) for line in lines if line.startswith('pywin32'))
        self.assertTrue(requirement.marker.evaluate({'sys_platform':'win32'}))
        self.assertFalse(requirement.marker.evaluate({'sys_platform':'darwin'}))

if __name__ == '__main__':
    unittest.main()
