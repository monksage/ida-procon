# Procon Coordinator API

Base URL: `http://127.0.0.1:40000`

All requests use `--noproxy '*'` with curl.

## Query Endpoints (GET)

### GET /status
Coverage stats per module.
```
?module=algorithm        (optional, omit for all modules)
```
Returns: `[{module, total, uncovered, resolved, skip, claimed, contours}]`

### GET /next-entry
Get uncovered functions ranked by callee richness.
```
?module=algorithm        (required)
&size=func               (micro|func|precontour|any, default: func)
&limit=5                 (1-50, default: 1)
&allow_sub=false         (allow sub_ functions, default: false)
```
Returns: `[{name, size, lines, callees_count, xrefs_count, uncovered_callees}]`

### GET /func-meta
Function metadata from manifest + coverage status.
```
?module=algorithm&name=TlsCallback_0
```
Returns: `{name, meta: {addr, size, callees, xrefs_to, ...}, coverage: {status, size, lines, partof}}`

### GET /func-code
Read function source code.
```
?module=algorithm&name=TlsCallback_0&source=resolved    (resolved|raw, default: resolved)
```
Returns: `{name, source, code}`

### GET /contours
List all contours with metadata.
```
?module=algorithm        (optional, omit for all modules)
```
Returns: `{module: [{name, entry, soldier, summary, node_count}]}`

### GET /contour-code
Assembled source code of an entire contour (all functions concatenated in graph order).
```
?module=algorithm&name=tls_slot_manager@TlsCallback_0
```
Returns: `{name, module, graph: {full graph.json}, code: "assembled source"}`

## Mutation Endpoints (POST)

All POST bodies are JSON with `Content-Type: application/json`.

### POST /claim
Atomically claim a function for editing. Must claim before modifying any file.
```json
{"module": "algorithm", "name": "sub_662CE740"}
```
Returns: `{ok: true}` or `{ok: false, reason: "already_claimed|already_resolved|skip"}`

### POST /release
Release a claim (e.g., if agent abandons work).
```json
{"module": "algorithm", "name": "sub_662CE740"}
```
Returns: `{ok: true}` or `{ok: false, reason: "not_claimed"}`

### POST /resolve
Mark a function as resolved within a contour.
```json
{"module": "algorithm", "name": "sub_662CE740", "contour": "spline_fit@sub_662CE740", "role": "helper"}
```
Roles: `entry`, `helper`, `leaf`, `micro`, `borrowed`

### POST /update-code
Update resolved function code via API (alternative to direct file edit).
```json
{"module": "algorithm", "name": "sub_662CE740", "code": "int foo() { ... }"}
```

### POST /submit-contour
Submit a completed contour. Creates `procon/{name}/graph.json`, updates coverage, releases all claims.
```json
{
  "module": "algorithm",
  "name": "descriptive_name@entry_func",
  "soldier": "opus",
  "entry": "entry_func",
  "nodes": {
    "entry_func": {"role": "entry", "resolved_file": "resolved_funcs/entry_func.c", "description": "..."},
    "helper_func": {"role": "helper", "resolved_file": "resolved_funcs/helper_func.c", "description": "..."},
    "borrowed_func": {"role": "borrowed", "resolved_file": "resolved_funcs/borrowed_func.c", "description": "read-only"}
  },
  "edges": [["entry_func", "helper_func"], ["helper_func", "borrowed_func"]],
  "external_deps": [{"name": "Sleep", "module": "KERNEL32"}],
  "summary": "What this contour does..."
}
```

## Key Concepts

- **Claim before edit**: Always POST /claim before modifying a function file. If claim fails, read-only (borrowed).
- **Borrowed**: Function claimed by another agent. Include in contour nodes with role `"borrowed"`, but do not edit.
- **Micro**: Functions <=10 lines. Shared across contours via `partof[]`, not exclusively owned.
- **Function sizes**: micro (<=10 lines), func (11-200), precontour (200+).
- **Coverage statuses**: uncovered, resolved, skip.
- **Claims have TTL**: Auto-released after 600s if not resolved/submitted.
- **File paths**: `dump/{module}/resolved_funcs/{name}.c` for direct file access, `dump/{module}/raw_funcs/{name}.c` for original Hex-Rays output.
