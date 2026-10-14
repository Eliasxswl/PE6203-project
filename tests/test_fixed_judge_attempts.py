"""Offline checks for bounded costs and resuming failed judge attempts."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from custom.analysis.answer import evaluation

GOOD = {'task_fulfillment': 8, 'grounding': 8, 'planning_and_efficiency': 7}

class FixedJudgeAttemptsTests(unittest.TestCase):
    def test_success_uses_exactly_five_attempts(self):
        with patch.object(evaluation, 'evaluate_one', return_value=GOOD) as judge:
            result = evaluation.evaluate_one_fixed_attempts({})
        self.assertEqual(judge.call_count, 5)
        self.assertEqual(result['aggregate']['total_runs'], 5)
        self.assertEqual(result['aggregate']['successful_runs'], 5)

    def test_failure_is_not_topped_up(self):
        with patch.object(evaluation, 'evaluate_one', side_effect=[{'error':'failed'}, GOOD, GOOD, GOOD, GOOD]) as judge:
            result = evaluation.evaluate_one_fixed_attempts({})
        self.assertEqual(judge.call_count, 5)
        self.assertEqual(result['aggregate']['successful_runs'], 4)

    def test_resume_does_not_repeat_failed_attempts(self):
        result = {'attempt_policy':'fixed_5_no_top_up', 'aggregate':{
            'total_runs':5, 'successful_runs':0,
            'task_fulfillment_mean':None, 'grounding_mean':None,
            'planning_and_efficiency_mean':None}, 'runs':[{'result':{'error':'failed'}}] * 5}
        case = {'idx':42}
        log_root = Path(__file__).resolve().parents[1] / 'logs'
        log_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=log_root) as directory:
            self.assertTrue(Path(directory).resolve().is_relative_to(log_root.resolve()))
            Path(directory, '42.json').write_text(json.dumps({'idx':42,'eval_result':result}), encoding='utf-8')
            with patch.object(evaluation, '_evaluate_case_task') as judge, contextlib.redirect_stdout(io.StringIO()):
                evaluation.evaluate_list({42:case}, save_dir=directory)
            judge.assert_not_called()

    def test_rejects_other_repeat_counts_before_request(self):
        with patch.object(evaluation, 'evaluate_one') as judge:
            with self.assertRaises(ValueError):
                evaluation.evaluate_one_fixed_attempts({}, num_runs=3)
            judge.assert_not_called()

if __name__ == '__main__':
    unittest.main()
