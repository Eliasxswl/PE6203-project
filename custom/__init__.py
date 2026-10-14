"""Expose the existing src/custom namespace from the repository root."""
from pathlib import Path

__path__.append(str(Path(__file__).resolve().parents[1] / "src" / "custom"))
