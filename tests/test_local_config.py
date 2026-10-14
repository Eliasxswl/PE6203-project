"""Check local-file configuration without reading or printing a real key."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from custom.utils import model_config

class LocalConfigTests(unittest.TestCase):
    def test_file_config_and_environment_override(self):
        log_root = Path(__file__).resolve().parents[1] / 'logs'
        log_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=log_root) as directory:
            self.assertTrue(Path(directory).resolve().is_relative_to(log_root.resolve()))
            config = Path(directory) / 'test.env'
            config.write_text('BIGMODEL_API_KEY=offline-placeholder\nBIGMODEL_MODEL=test-model\n', encoding='utf-8')
            with patch.dict(os.environ, {}, clear=True):
                model_config.load_dotenv(config, override=False)
                self.assertEqual(model_config.api_key(), 'offline-placeholder')
                self.assertEqual(model_config.model_name(), 'test-model')
                os.environ['BIGMODEL_MODEL'] = 'override-model'
                model_config.load_dotenv(config, override=False)
                self.assertEqual(model_config.model_name(), 'override-model')

if __name__ == '__main__':
    unittest.main()
