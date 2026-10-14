"""Shared result layout; evolution metadata is never an output directory."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

def run_directory(output_path=None, stage='original', run_id='run-1'):
    if output_path:
        return Path(output_path).resolve()
    if stage not in ('original', 'iter3', 'iter5'):
        raise ValueError('Unknown server stage')
    if Path(run_id).name != run_id or run_id in ('.', '..'):
        raise ValueError('run_id must be a single directory name')
    return PROJECT_ROOT / 'results' / 'baseline' / stage / run_id

def score_directory(answer_path):
    answer_path = Path(answer_path)
    if answer_path.name == 'answers':
        return answer_path.parent / 'scores'
    # Read older upstream output layouts if explicitly supplied.
    if answer_path.name.startswith('ANSWER'):
        return answer_path.with_name(answer_path.name.replace('ANSWER', 'EVAL', 1))
    raise ValueError('Expected an answers directory (or legacy ANSWER directory).')
