"""Shared local configuration for agent and judge; local .env stays outside Git."""
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / '.env', override=False)

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"

def workspace_dir():
    return Path(os.environ.get('BENCH_WORKSPACE') or Path(__file__).resolve().parents[3] / 'anotation_path')

def api_key():
    value = os.environ.get("BIGMODEL_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not value:
        raise RuntimeError("Set BIGMODEL_API_KEY in the project .env file or environment before calling a model.")
    return value

def base_url():
    return os.environ.get("BIGMODEL_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL

def model_name():
    value = os.environ.get("BIGMODEL_MODEL")
    if not value:
        raise RuntimeError("Set BIGMODEL_MODEL in .env or the environment to a model ID available to your account.")
    return value

def judge_runs():
    value = int(os.environ.get('BENCH_JUDGE_RUNS', '5'))
    if value != 5:
        raise ValueError('This project uses exactly 5 judge attempts per trajectory; set BENCH_JUDGE_RUNS=5.')
    return value
