import json
import os
from pathlib import Path


def load_coverage(module_dir: Path) -> dict:
    coverage_path = module_dir / "coverage.json"
    with open(coverage_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_coverage(module_dir: Path, coverage: dict) -> None:
    coverage_path = module_dir / "coverage.json"
    tmp = coverage_path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(coverage, f, indent=2, ensure_ascii=False)
    os.replace(tmp, coverage_path)
