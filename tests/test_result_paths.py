from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from custom.utils.result_paths import run_directory, score_directory, PROJECT_ROOT

class ResultPathTests(unittest.TestCase):
    def test_repeat_and_stage_are_separate(self):
        self.assertEqual(run_directory(stage='iter3', run_id='run-2'), PROJECT_ROOT/'results/baseline/iter3/run-2')
        self.assertNotEqual(run_directory(run_id='run-1'), run_directory(run_id='run-2'))

    def test_scores_are_beside_answers(self):
        self.assertEqual(score_directory('results/run-1/answers'), Path('results/run-1/scores'))
        self.assertEqual(score_directory('old/ANSWER-model'), Path('old/EVAL-model'))

    def test_reject_parent_traversal(self):
        with self.assertRaises(ValueError):
            run_directory(run_id='../run-2')

if __name__ == '__main__':
    unittest.main()
