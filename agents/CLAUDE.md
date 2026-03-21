# Agent Room

You are a subagent in a reverse engineering pipeline. Your specific orders are in your assigned folder.

## Hierarchy
- **Commander** — launches you, monitors results
- **Sergeant** (`/sergeant` skill) — analyzes status, recommends actions. Does NOT launch agents.
- **Soldiers** (`AGENT_ROOM/soldiers/`) — create processed contours (procon)
- **Corporals** (`AGENT_ROOM/corporals/`) — create cross-module knots

## API Daemon

All data operations go through `http://127.0.0.1:40000`. Use `curl --noproxy '*'` for requests.

Key endpoints:
- `GET /status` — coverage stats
- `GET /next-entry?module=X&size=func` — get uncovered entry point
- `POST /claim` — claim a function (atomic)
- `GET /func-code?module=X&name=Y` — get function code
- `POST /update-code` — submit improved code
- `POST /submit-contour` — create contour and update coverage
- `POST /release` — release a claim

## Rules

1. **Never read manifest.json or coverage.json directly.** Use the API.
2. **Never read entire directories.** Navigate through code headers (// callees:, // xrefs_from:) and API.
3. **Never modify raw_funcs/.** Work through the API only.
4. **Read your specific orders** from your assigned folder before starting.
