"""
ida_dump.py — Dump all decompiled functions from IDA Pro MCP server.

Usage:
    python ida_dump.py --port 13337 --module mylib --output dump
    python ida_dump.py --port 13338 --module myapp --output dump
"""

import argparse
import json
import os
import sys
import time

import requests

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_PORT = 13337
DEFAULT_MODULE = "algorithm"
DEFAULT_OUTPUT = "dump"
DEFAULT_DELAY = 0.05        # seconds between MCP calls
DEFAULT_BATCH_SIZE = 50     # functions per func_query page
DEFAULT_ADDRS_BATCH = 20    # addresses per callees batch
DEFAULT_XREFS_BATCH = 5     # addresses per xrefs batch (smaller due to truncation)

# ---------------------------------------------------------------------------
# CRT / skip detection
# ---------------------------------------------------------------------------
CRT_NAMES = {
    "_start", "__start", "start",
    "DllEntryPoint", "DllMain",
    "_DllMainCRTStartup", "__DllMainCRTStartup",
    "WinMain", "wWinMain",
    "_initterm", "_initterm_e", "initterm",
    "__security_init_cookie", "__security_check_cookie",
    "__report_rangecheckfailure",
    "_onexit", "_atexit", "atexit",
    "_cexit", "_c_exit", "cexit",
    "_amsg_exit", "amsg_exit",
    "_exit", "exit",
    "malloc", "free", "realloc", "calloc",
    "_malloc", "_free", "_realloc",
    "memcpy", "memset", "memmove", "memcmp",
    "strlen", "strcpy", "strcat", "strcmp", "strncmp",
    "sprintf", "printf", "fprintf", "sscanf",
    "_purecall", "__purecall",
    "nullsub_1",
}

CRT_PREFIXES = ("_", "j_", "__", "??", "?")


def is_crt_function(name: str) -> bool:
    if name in CRT_NAMES:
        return True
    if name.startswith("sub_"):
        return False
    for prefix in CRT_PREFIXES:
        if name.startswith(prefix):
            return True
    return False


# ---------------------------------------------------------------------------
# MCP Client
# ---------------------------------------------------------------------------
class MCPError(Exception):
    def __init__(self, tool, detail):
        self.tool = tool
        self.detail = detail
        super().__init__(f"MCP error in {tool}: {detail}")


class MCPClient:
    def __init__(self, host: str, port: int, delay: float):
        self.url = f"http://{host}:{port}/mcp"
        self.delay = delay
        self.session = requests.Session()
        self.session.proxies = {"http": "", "https": ""}
        self.session.trust_env = False
        self._req_id = 0

    def call(self, tool_name: str, arguments: dict):
        self._req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        time.sleep(self.delay)
        resp = self.session.post(self.url, json=payload, timeout=120)
        resp.raise_for_status()
        body = resp.json()
        if body.get("result", {}).get("isError"):
            err = body["result"].get("content", [{}])[0].get("text", "unknown")
            raise MCPError(tool_name, err)
        return self._extract(body)

    @staticmethod
    def _extract(body: dict):
        result = body.get("result", {})
        # prefer structuredContent if available
        sc = result.get("structuredContent")
        if sc is not None:
            # structuredContent may wrap in "result" key or be direct
            if isinstance(sc, dict) and "result" in sc:
                return sc["result"]
            return sc
        # fallback: parse text content
        for item in result.get("content", []):
            if item.get("type") == "text":
                try:
                    return json.loads(item["text"])
                except (json.JSONDecodeError, TypeError):
                    return item["text"]
        return result


# ---------------------------------------------------------------------------
# API wrappers
# ---------------------------------------------------------------------------
def fetch_all_functions(client: MCPClient, batch_size: int) -> list:
    all_funcs = []
    offset = 0
    while True:
        result = client.call("func_query", {
            "queries": [{"offset": offset, "count": batch_size}]
        })
        data = result[0]["data"]
        all_funcs.extend(data)
        next_offset = result[0].get("next_offset")
        print(f"  Fetched {len(all_funcs)} functions (offset={offset})")
        if next_offset is None or len(data) < batch_size:
            break
        offset = next_offset
    return all_funcs


def fetch_callees_batch(client: MCPClient, addrs: list) -> dict:
    """Returns {addr: [{addr, name, type}, ...]}"""
    try:
        result = client.call("callees", {"addrs": addrs})
        out = {}
        for item in result:
            if "addr" not in item:
                continue
            out[item["addr"]] = item.get("callees", [])
        # fill missing addrs with empty lists
        for a in addrs:
            if a not in out:
                out[a] = []
        return out
    except Exception as e:
        print(f"    WARNING: callees batch failed: {e}")
        return {a: [] for a in addrs}


def fetch_xrefs_batch(client: MCPClient, addrs: list) -> dict:
    """Returns {addr: [{addr, type, fn}, ...]}
    Handles MCP truncation by re-fetching missed addresses with smaller batches.
    """
    out = {}
    try:
        result = client.call("xrefs_to", {"addrs": addrs})
        for item in result:
            if "_truncated" in item:
                break
            if "addr" not in item:
                continue
            out[item["addr"]] = item.get("xrefs", [])
    except Exception as e:
        print(f"    WARNING: xrefs batch failed: {e}")
        return {a: [] for a in addrs}

    # re-fetch missed addresses individually
    missed = [a for a in addrs if a not in out]
    for addr in missed:
        try:
            result = client.call("xrefs_to", {"addrs": [addr]})
            for item in result:
                if "_truncated" not in item and "addr" in item:
                    out[item["addr"]] = item.get("xrefs", [])
        except Exception:
            out[addr] = []
    return out


def fetch_decompile(client: MCPClient, addr: str):
    try:
        result = client.call("decompile", {"addr": addr})
        return result.get("code")
    except Exception as e:
        return None


def fetch_survey(client: MCPClient) -> dict:
    try:
        return client.call("survey_binary", {})
    except Exception:
        return {}


def fetch_all_imports(client: MCPClient) -> list:
    all_imports = []
    offset = 0
    while True:
        try:
            result = client.call("imports", {"offset": offset, "count": 200})
            data = result.get("data", [])
            all_imports.extend(data)
            next_offset = result.get("next_offset")
            if next_offset is None or len(data) < 200:
                break
            offset = next_offset
        except Exception:
            break
    return all_imports


def fetch_all_globals(client: MCPClient) -> list:
    all_globals = []
    offset = 0
    while True:
        try:
            result = client.call("list_globals", {
                "queries": [{"offset": offset, "count": 200}]
            })
            data = result[0]["data"]
            all_globals.extend(data)
            next_offset = result[0].get("next_offset")
            if next_offset is None or len(data) < 200:
                break
            offset = next_offset
        except Exception:
            break
    return all_globals


# ---------------------------------------------------------------------------
# State manager
# ---------------------------------------------------------------------------
class StateManager:
    def __init__(self, output_dir: str, module: str):
        self.base_dir = os.path.join(output_dir, module)
        self.raw_dir = os.path.join(self.base_dir, "raw_funcs")
        self.resolved_dir = os.path.join(self.base_dir, "resolved_funcs")
        self.procon_dir = os.path.join(self.base_dir, "procon")
        self.progress_file = os.path.join(self.base_dir, ".progress.json")
        self.manifest_path = os.path.join(self.base_dir, "manifest.json")
        self.coverage_path = os.path.join(self.base_dir, "coverage.json")

    def ensure_dirs(self):
        os.makedirs(self.raw_dir, exist_ok=True)
        os.makedirs(self.resolved_dir, exist_ok=True)
        os.makedirs(self.procon_dir, exist_ok=True)

    def func_path(self, name: str) -> str:
        return os.path.join(self.raw_dir, f"{name}.c")

    def is_dumped(self, name: str) -> bool:
        return os.path.exists(self.func_path(name))

    def load_progress(self) -> dict:
        if os.path.exists(self.progress_file):
            with open(self.progress_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_progress(self, progress: dict):
        tmp = self.progress_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(progress, f)
        os.replace(tmp, self.progress_file)


# ---------------------------------------------------------------------------
# Header builder
# ---------------------------------------------------------------------------
def build_header(addr: str, size: str, module: str,
                 callees: list, xrefs: list) -> str:
    if callees:
        callee_strs = [f"{c.get('name', c.get('addr','?'))} ({c.get('type','?')})"
                       for c in callees]
        callees_line = ", ".join(callee_strs)
    else:
        callees_line = "none"

    if xrefs:
        xref_strs = []
        for x in xrefs:
            fn = x.get("fn")
            if fn:
                xref_strs.append(f"{fn} ({x.get('type','?')})")
            else:
                xref_strs.append(f"{x.get('addr','?')} ({x.get('type','?')})")
        xrefs_line = ", ".join(xref_strs)
    else:
        xrefs_line = "none"

    return (
        f"// addr: {addr}\n"
        f"// size: {size}\n"
        f"// module: {module}\n"
        f"// callees: {callees_line}\n"
        f"// xrefs_from: {xrefs_line}\n"
        f"\n"
    )


# ---------------------------------------------------------------------------
# Phase executors
# ---------------------------------------------------------------------------
def phase1_functions(client: MCPClient, state: StateManager,
                     progress: dict, batch_size: int) -> list:
    if progress.get("phase1_done") and progress.get("functions"):
        print(f"[Phase 1] Cached: {len(progress['functions'])} functions")
        return progress["functions"]

    print("[Phase 1] Fetching function list...")
    funcs = fetch_all_functions(client, batch_size)
    print(f"[Phase 1] Total: {len(funcs)} functions")
    progress["functions"] = funcs
    progress["phase1_done"] = True
    state.save_progress(progress)
    return funcs


def phase2_refs(client: MCPClient, state: StateManager,
                progress: dict, funcs: list,
                addrs_batch: int, xrefs_batch: int):
    callees_cache = progress.get("callees", {})
    xrefs_cache = progress.get("xrefs", {})

    # Callees
    remaining_callees = [f["addr"] for f in funcs if f["addr"] not in callees_cache]
    if remaining_callees:
        total = len(remaining_callees)
        print(f"[Phase 2a] Fetching callees for {total} functions...")
        for i in range(0, total, addrs_batch):
            batch = remaining_callees[i:i + addrs_batch]
            callees_result = fetch_callees_batch(client, batch)
            for addr in batch:
                callees_cache[addr] = callees_result.get(addr, [])
            done = min(i + addrs_batch, total)
            if done % 100 == 0 or done == total:
                print(f"  Callees: {done}/{total}")
                progress["callees"] = callees_cache
                state.save_progress(progress)
    else:
        print("[Phase 2a] Callees cached")

    # Xrefs (separate loop, smaller batch)
    remaining_xrefs = [f["addr"] for f in funcs if f["addr"] not in xrefs_cache]
    if remaining_xrefs:
        total = len(remaining_xrefs)
        print(f"[Phase 2b] Fetching xrefs for {total} functions...")
        for i in range(0, total, xrefs_batch):
            batch = remaining_xrefs[i:i + xrefs_batch]
            xrefs_result = fetch_xrefs_batch(client, batch)
            for addr in batch:
                xrefs_cache[addr] = xrefs_result.get(addr, [])
            done = min(i + xrefs_batch, total)
            if done % 200 == 0 or done == total:
                print(f"  Xrefs: {done}/{total}")
                progress["xrefs"] = xrefs_cache
                state.save_progress(progress)
    else:
        print("[Phase 2b] Xrefs cached")

    progress["callees"] = callees_cache
    progress["xrefs"] = xrefs_cache
    progress["phase2_done"] = True
    state.save_progress(progress)


def phase3_decompile(client: MCPClient, state: StateManager,
                     progress: dict, funcs: list, module: str):
    callees_cache = progress.get("callees", {})
    xrefs_cache = progress.get("xrefs", {})
    errors = []

    total = len(funcs)
    skipped = 0
    decompiled = 0

    print(f"[Phase 3] Decompiling {total} functions...")

    for i, func in enumerate(funcs):
        name = func["name"]
        addr = func["addr"]

        if state.is_dumped(name):
            skipped += 1
            continue

        code = fetch_decompile(client, addr)
        if code is None:
            errors.append({"addr": addr, "name": name})
            print(f"  ERROR: {i+1}/{total} {name} ({addr}) — decompile failed")
            continue

        callees = callees_cache.get(addr, [])
        xrefs = xrefs_cache.get(addr, [])
        header = build_header(addr, func["size"], module, callees, xrefs)

        with open(state.func_path(name), "w", encoding="utf-8") as f:
            f.write(header)
            f.write(code)
            f.write("\n")

        decompiled += 1
        if decompiled % 100 == 0:
            print(f"  Phase 3: decompiled {decompiled}, skipped {skipped}, "
                  f"errors {len(errors)} (at {i+1}/{total})")

    print(f"[Phase 3] Done: {decompiled} decompiled, {skipped} skipped, "
          f"{len(errors)} errors")

    if errors:
        err_path = os.path.join(state.base_dir, "errors.json")
        with open(err_path, "w", encoding="utf-8") as f:
            json.dump(errors, f, indent=2)
        print(f"  Errors saved to {err_path}")


def phase4_metadata(client: MCPClient, state: StateManager, progress: dict):
    if progress.get("phase4_done"):
        print("[Phase 4] Metadata cached")
        return

    print("[Phase 4] Fetching metadata...")

    print("  survey_binary...")
    progress["survey"] = fetch_survey(client)

    print("  imports...")
    progress["imports"] = fetch_all_imports(client)
    print(f"    {len(progress['imports'])} imports")

    print("  globals...")
    progress["globals"] = fetch_all_globals(client)
    print(f"    {len(progress['globals'])} globals")

    progress["phase4_done"] = True
    state.save_progress(progress)


def phase3_update_headers(state: StateManager, progress: dict,
                          funcs: list, module: str):
    """Update only headers in existing .c files without re-decompiling."""
    callees_cache = progress.get("callees", {})
    xrefs_cache = progress.get("xrefs", {})
    updated = 0

    print(f"[Phase 3 update] Updating headers in .c files...")

    for func in funcs:
        name = func["name"]
        addr = func["addr"]
        filepath = state.func_path(name)

        if not os.path.exists(filepath):
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # find where header ends (empty line before code)
        parts = content.split("\n\n", 1)
        if len(parts) < 2:
            continue

        code_part = parts[1]
        callees = callees_cache.get(addr, [])
        xrefs = xrefs_cache.get(addr, [])
        new_header = build_header(addr, func["size"], module, callees, xrefs)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_header)
            f.write(code_part)

        updated += 1

    print(f"  Updated {updated} files")


def phase5_manifest(state: StateManager, progress: dict,
                    funcs: list, module: str):
    print("[Phase 5] Writing manifest.json...")

    callees_cache = progress.get("callees", {})
    xrefs_cache = progress.get("xrefs", {})
    survey = progress.get("survey", {})

    # extract metadata from survey
    meta = survey.get("metadata", survey)

    functions_map = {}
    for func in funcs:
        addr = func["addr"]
        name = func["name"]
        functions_map[addr] = {
            "name": name,
            "size": func["size"],
            "has_type": func.get("has_type", False),
            "file": f"raw_funcs/{name}.c",
            "callees": callees_cache.get(addr, []),
            "xrefs_to": xrefs_cache.get(addr, []),
            "skip": is_crt_function(name),
        }

    manifest = {
        "module": meta.get("module", f"{module}.dll"),
        "path": meta.get("path", ""),
        "arch": meta.get("arch", ""),
        "base_address": meta.get("base_address", ""),
        "total_functions": len(funcs),
        "functions": functions_map,
        "imports": progress.get("imports", []),
        "globals": progress.get("globals", []),
    }

    with open(state.manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"  Written: {state.manifest_path}")
    print(f"  {len(functions_map)} functions in manifest")
    skip_count = sum(1 for v in functions_map.values() if v["skip"])
    print(f"  {skip_count} marked as CRT/skip")


# ---------------------------------------------------------------------------
# Phase 6: Prepare workspace (coverage.json + resolved_funcs)
# ---------------------------------------------------------------------------
def phase6_prepare_workspace(state: StateManager):
    """Create coverage.json from manifest and copy raw_funcs to resolved_funcs."""
    import shutil

    # --- coverage.json ---
    if os.path.exists(state.coverage_path):
        print("[Phase 6] coverage.json already exists, skipping")
    else:
        print("[Phase 6] Creating coverage.json...")
        manifest = json.load(open(state.manifest_path, "r", encoding="utf-8"))
        coverage = {"nodes": {}}
        for addr, f in manifest["functions"].items():
            name = f["name"]
            size_bytes = int(f.get("size", "0x0"), 16)
            lines = max(size_bytes // 4, 1)
            is_skip = f.get("skip", False)
            if is_skip:
                size_class = "micro"
                status = "skip"
            elif lines <= 10:
                size_class = "micro"
                status = "uncovered"
            elif lines > 200:
                size_class = "precontour"
                status = "uncovered"
            else:
                size_class = "func"
                status = "uncovered"
            coverage["nodes"][name] = {
                "status": status,
                "size": size_class,
                "lines": lines,
                "partof": [],
            }
        with open(state.coverage_path, "w", encoding="utf-8") as f:
            json.dump(coverage, f, indent=2)
        total = len(coverage["nodes"])
        skip_count = sum(1 for v in coverage["nodes"].values() if v["status"] == "skip")
        print(f"  {total} nodes, {skip_count} skip, {total - skip_count} uncovered")

    # --- resolved_funcs (copy from raw_funcs) ---
    existing = set(os.listdir(state.resolved_dir)) if os.path.exists(state.resolved_dir) else set()
    raw_files = set(os.listdir(state.raw_dir))
    to_copy = raw_files - existing
    if not to_copy:
        print(f"[Phase 6] resolved_funcs already populated ({len(existing)} files)")
    else:
        print(f"[Phase 6] Copying {len(to_copy)} files to resolved_funcs...")
        for fname in to_copy:
            shutil.copy2(os.path.join(state.raw_dir, fname), os.path.join(state.resolved_dir, fname))
        print(f"  Done: {len(to_copy)} copied, {len(existing)} already existed")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Dump decompiled functions from IDA Pro MCP server"
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--module", type=str, default=DEFAULT_MODULE)
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--addrs-batch", type=int, default=DEFAULT_ADDRS_BATCH)
    parser.add_argument("--xrefs-batch", type=int, default=DEFAULT_XREFS_BATCH)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--reset-xrefs", action="store_true",
                        help="Clear cached xrefs and re-fetch them")
    parser.add_argument("--update-headers", action="store_true",
                        help="Update .c file headers from cached data (no MCP calls)")
    args = parser.parse_args()

    print(f"=== ida_dump: {args.module} @ port {args.port} ===")
    print(f"Output: {args.output}/{args.module}/")
    print()

    client = MCPClient("127.0.0.1", args.port, args.delay)
    state = StateManager(args.output, args.module)
    state.ensure_dirs()

    progress = {} if args.no_resume else state.load_progress()

    if args.reset_xrefs:
        print("Resetting xrefs cache...")
        progress.pop("xrefs", None)
        progress["phase2_done"] = False
        state.save_progress(progress)

    # Phase 1
    funcs = phase1_functions(client, state, progress, args.batch_size)

    # Phase 2
    phase2_refs(client, state, progress, funcs, args.addrs_batch, args.xrefs_batch)

    if args.update_headers:
        # Update headers only, skip decompile
        phase3_update_headers(state, progress, funcs, args.module)
    else:
        # Phase 3
        phase3_decompile(client, state, progress, funcs, args.module)

    # Phase 4
    phase4_metadata(client, state, progress)

    # Phase 5
    phase5_manifest(state, progress, funcs, args.module)

    # Phase 6
    phase6_prepare_workspace(state)

    print()
    print("Done!")


if __name__ == "__main__":
    main()
