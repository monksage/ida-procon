# Procon API — Read-Only Reference

Base URL: `http://127.0.0.1:40000`

Use `--noproxy '*'` with all curl commands.

## Endpoints

### GET /status
Coverage stats per module.
```
curl -s --noproxy '*' http://127.0.0.1:40000/status
curl -s --noproxy '*' "http://127.0.0.1:40000/status?module=algorithm"
```
Returns: `[{module, total, uncovered, resolved, skip, claimed, contours}]`

### GET /contours
List all completed contours with summaries.
```
curl -s --noproxy '*' http://127.0.0.1:40000/contours
curl -s --noproxy '*' "http://127.0.0.1:40000/contours?module=algorithm"
```
Returns: `{module: [{name, entry, soldier, summary, node_count}]}`

### GET /contour-code
Full assembled source code of a contour — all functions in call-graph order.
```
curl -s --noproxy '*' "http://127.0.0.1:40000/contour-code?module=algorithm&name=tls_slot_manager@TlsCallback_0"
```
Returns: `{name, module, graph, code}` — `code` is the concatenated C source, `graph` is the full dependency graph.

### GET /func-code
Read a single function's source code.
```
curl -s --noproxy '*' "http://127.0.0.1:40000/func-code?module=algorithm&name=TlsCallback_0"
curl -s --noproxy '*' "http://127.0.0.1:40000/func-code?module=algorithm&name=TlsCallback_0&source=raw"
```
`source=resolved` (default) — cleaned up code. `source=raw` — original Hex-Rays decompilation.

### GET /func-meta
Function metadata: address, callees, cross-references, coverage status.
```
curl -s --noproxy '*' "http://127.0.0.1:40000/func-meta?module=algorithm&name=TlsCallback_0"
```
Returns: `{name, meta: {addr, size, callees, xrefs_to}, coverage: {status, size, lines, partof}}`

## Typical workflow

1. `GET /status` — see what modules exist and their coverage
2. `GET /contours?module=X` — browse available contours
3. `GET /contour-code?module=X&name=Y` — read assembled source of a contour
4. `GET /func-code` / `GET /func-meta` — drill into individual functions
