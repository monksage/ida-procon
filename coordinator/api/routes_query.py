"""
Query routes: read-only operations.
"""

from fastapi import APIRouter, HTTPException, Query

from models.function import FunctionEntry, FunctionStatus
from models.coverage import ModuleStatus

router = APIRouter()

# injected at startup
_registry = None
_claimer = None


def init(registry, claimer):
    global _registry, _claimer
    _registry = registry
    _claimer = claimer


@router.get("/status")
def status(module: str | None = None) -> list[ModuleStatus]:
    modules = [module] if module else _registry.list_modules()
    result = []
    for mod_name in modules:
        mod = _registry.get_module(mod_name)
        if mod is None:
            continue
        nodes = mod.coverage.get("nodes", {})
        result.append(ModuleStatus(
            module=mod_name,
            total=len(nodes),
            uncovered=sum(1 for v in nodes.values() if v.get("status") == "uncovered"),
            resolved=sum(1 for v in nodes.values() if v.get("status") == "resolved"),
            skip=sum(1 for v in nodes.values() if v.get("status") == "skip"),
            claimed=_claimer.claimed_count(mod_name),
            contours=len(mod.list_contours()),
        ))
    return result


@router.get("/next-entry")
def next_entry(
    module: str,
    size: str = Query("func", description="micro|func|precontour|any"),
    limit: int = Query(1, ge=1, le=50),
    allow_sub: bool = Query(False, description="Allow sub_ functions as entry points"),
) -> list[FunctionEntry]:
    mod = _registry.get_module(module)
    if mod is None:
        raise HTTPException(404, f"Module '{module}' not found")

    nodes = mod.coverage.get("nodes", {})
    candidates = []

    for name, node in nodes.items():
        if node.get("status") != "uncovered":
            continue
        if not allow_sub and name.startswith("sub_"):
            continue
        if size != "any" and node.get("size") != size:
            continue
        if _claimer.is_claimed(module, name):
            continue

        # get connection richness from manifest
        meta = mod.get_func_meta(name)
        if meta is None:
            continue

        callees = meta.get("callees", [])
        xrefs = meta.get("xrefs_to", [])
        internal_callees = [c for c in callees if c.get("type") == "internal"]

        # count how many callees are still uncovered
        uncovered_callees = 0
        for c in internal_callees:
            c_name = c.get("name", "")
            c_node = nodes.get(c_name, {})
            if c_node.get("status") == "uncovered":
                uncovered_callees += 1

        candidates.append(FunctionEntry(
            name=name,
            size=node.get("size", "func"),
            lines=node.get("lines", 0),
            callees_count=len(internal_callees),
            xrefs_count=len(xrefs),
            uncovered_callees=uncovered_callees,
        ))

    # sort by uncovered_callees descending (richest threads first)
    candidates.sort(key=lambda c: (c.uncovered_callees, c.callees_count), reverse=True)
    return candidates[:limit]


@router.get("/func-meta")
def func_meta(module: str, name: str) -> dict:
    mod = _registry.get_module(module)
    if mod is None:
        raise HTTPException(404, f"Module '{module}' not found")

    meta = mod.get_func_meta(name)
    if meta is None:
        raise HTTPException(404, f"Function '{name}' not found in {module}")

    cov = mod.get_coverage_node(name) or {}
    return {
        "name": name,
        "meta": meta,
        "coverage": cov,
    }


@router.get("/func-code")
def func_code(module: str, name: str, source: str = "resolved") -> dict:
    mod = _registry.get_module(module)
    if mod is None:
        raise HTTPException(404, f"Module '{module}' not found")

    from storage.func_io import read_resolved, read_raw
    if source == "raw":
        code = read_raw(mod.path, name)
    else:
        code = read_resolved(mod.path, name)

    if code is None:
        raise HTTPException(404, f"File not found for '{name}' in {module}")

    return {"name": name, "source": source, "code": code}


@router.get("/contour-code")
def contour_code(module: str, name: str) -> dict:
    mod = _registry.get_module(module)
    if mod is None:
        raise HTTPException(404, f"Module '{module}' not found")

    import json
    graph_path = mod.path / "procon" / name / "graph.json"
    if not graph_path.exists():
        raise HTTPException(404, f"Contour '{name}' not found in {module}")

    with open(graph_path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    from storage.func_io import read_resolved
    nodes = graph.get("nodes", {})
    entry = graph.get("entry", "")

    # order: entry first, then remaining by edges order
    ordered = []
    if entry in nodes:
        ordered.append(entry)
    for edge in graph.get("edges", []):
        for n in edge:
            if n not in ordered and n in nodes:
                ordered.append(n)
    # any remaining nodes not in edges
    for n in nodes:
        if n not in ordered:
            ordered.append(n)

    parts = []
    parts.append(f"// Contour: {graph.get('name', name)}")
    parts.append(f"// Module: {module}")
    parts.append(f"// Entry: {entry}")
    parts.append(f"// Summary: {graph.get('summary', '')}")
    parts.append(f"// External deps: {', '.join(d.get('name','') for d in graph.get('external_deps', []))}")
    parts.append("")

    for func_name in ordered:
        node_info = nodes[func_name]
        role = node_info.get("role", "")
        desc = node_info.get("description", "")
        code = read_resolved(mod.path, func_name)
        parts.append(f"// ===== [{role}] {func_name} =====")
        if desc:
            parts.append(f"// {desc}")
        if code:
            parts.append(code)
        else:
            parts.append(f"// (code not found)")
        parts.append("")

    return {
        "name": name,
        "module": module,
        "graph": graph,
        "code": "\n".join(parts),
    }


@router.get("/contours")
def list_contours(module: str | None = None) -> dict:
    import json
    result = {}
    modules = [module] if module else _registry.list_modules()
    for mod_name in modules:
        mod = _registry.get_module(mod_name)
        if mod is None:
            continue
        contours = []
        for cname in mod.list_contours():
            graph_path = mod.path / "procon" / cname / "graph.json"
            info = {"name": cname}
            if graph_path.exists():
                with open(graph_path, "r", encoding="utf-8") as f:
                    g = json.load(f)
                info["entry"] = g.get("entry", "")
                info["soldier"] = g.get("soldier", "")
                info["summary"] = g.get("summary", "")
                info["node_count"] = len(g.get("nodes", {}))
            contours.append(info)
        result[mod_name] = contours
    return result
