from pathlib import Path


def read_resolved(module_dir: Path, func_name: str) -> str | None:
    fpath = module_dir / "resolved_funcs" / f"{func_name}.c"
    if not fpath.exists():
        return None
    with open(fpath, "r", encoding="utf-8") as f:
        return f.read()


def write_resolved(module_dir: Path, func_name: str, code: str) -> None:
    fpath = module_dir / "resolved_funcs" / f"{func_name}.c"
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(code)


def read_raw(module_dir: Path, func_name: str) -> str | None:
    fpath = module_dir / "raw_funcs" / f"{func_name}.c"
    if not fpath.exists():
        return None
    with open(fpath, "r", encoding="utf-8") as f:
        return f.read()
