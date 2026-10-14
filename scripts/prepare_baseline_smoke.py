"""Compatibility wrapper: validate the common pipeline instead of preparing a second runner."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from custom.experiment.__main__ import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deprecated smoke preparation; validate the common experiment")
    parser.add_argument("--config", default="config/experiment.json")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    command = ["validate", "--config", args.config]
    if args.offline:
        command.append("--offline")
    raise SystemExit(main(command))
