import json
from pathlib import Path


def load_manifest(module_dir: Path) -> dict:
    manifest_path = module_dir / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)
