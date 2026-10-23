"""Score validity, missing-data and ECS regression checks (no network/model calls)."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('role4_analysis',
    Path(__file__).resolve().parents[1] / 'scripts/role4/analyze_pilots.py')
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class Role4AnalysisTests(unittest.TestCase):
    def test_missing_and_invalid_scores_are_not_zero(self):
        for score in (None, {}, {'tf': True}, {'tf': float('nan')}, {'tf': 0}, {'tf': 11}):
            self.assertIsNone(analysis.finite_score(score, 'tf'))
        self.assertEqual(analysis.finite_score({'tf': 1.75}, 'tf'), 1.75)

    def test_ecs_population_sd(self):
        self.assertEqual(analysis.ecs([9, 9, 9]), 9)
        self.assertAlmostEqual(analysis.ecs([9, 5, 9]), 5.78104858350254)

    def test_empty_and_zero_usage_are_distinct(self):
        self.assertIsNone(analysis.token_totals([])['total_tokens'])
        self.assertEqual(analysis.token_totals([{'total_tokens': 0}])['total_tokens'], 0)
        mixed = analysis.token_totals([{'total_tokens': 8}, {}])
        self.assertEqual(mixed['total_tokens'], 8)
        self.assertEqual(mixed['total_tokens_missing_calls'], 1)


if __name__ == '__main__':
    unittest.main()
