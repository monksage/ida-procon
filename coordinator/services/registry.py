"""
Registry: holds all modules' manifest and coverage data in memory.
Loaded once at startup, coverage updated via write queue.
"""

import os
from pathlib import Path

from storage.manifest_io import load_manifest
from storage.coverage_io import load_coverage


class ModuleData:
    def __init__(self, name: str, path: Path, manifest: dict, coverage: dict):
        self.name = name
        self.path = path
        self.manifest = manifest
        self.coverage = coverage

        # build addr->name and name->addr lookups from manifest
        self.addr_to_func: dict[str, dict] = {}
        self.name_to_addr: dict[str, str] = {}
        for addr, func in manifest.get("functions", {}).items():
            self.addr_to_func[addr] = func
            self.name_to_addr[func["name"]] = addr

    def get_func_meta(self, name: str) -> dict | None:
        addr = self.name_to_addr.get(name)
        if addr is None:
            return None
        return self.addr_to_func.get(addr)

    def get_coverage_node(self, name: str) -> dict | None:
        return self.coverage.get("nodes", {}).get(name)

    def list_contours(self) -> list[str]:
        procon_dir = self.path / "procon"
        if not procon_dir.exists():
            return []
        return [d.name for d in procon_dir.iterdir() if d.is_dir()]


class Registry:
    def __init__(self, dump_dir: Path):
        self.dump_dir = dump_dir
        self.modules: dict[str, ModuleData] = {}
        self._load_all()

    def _load_all(self):
        for entry in self.dump_dir.iterdir():
            if entry.is_dir() and (entry / "manifest.json").exists():
                name = entry.name
                manifest = load_manifest(entry)
                coverage = load_coverage(entry)
                self.modules[name] = ModuleData(name, entry, manifest, coverage)
                func_count = len(manifest.get("functions", {}))
                print(f"  Loaded module: {name} ({func_count} functions)")

    def get_module(self, name: str) -> ModuleData | None:
        return self.modules.get(name)

    def list_modules(self) -> list[str]:
        return list(self.modules.keys())
