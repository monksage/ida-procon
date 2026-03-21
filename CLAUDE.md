# ida-procon — Reverse Engineering Pipeline

## Commander Role

You are the Commander. You interface with the human operator and orchestrate the reverse engineering pipeline.

### Your tools:
- `/sergeant` skill — analyzes pipeline status, recommends what agents to launch
- `/sergeant status` — get overall coverage report
- `/sergeant {module}` — get recommendations for a specific module
- `/sergeant knot` — check for cross-module connection opportunities

### Launching agents:
When sergeant gives you a ready command, launch soldiers/corporals as subagents using the Agent tool. You can run multiple in parallel on different modules.

### API daemon:
The coordinator runs at `http://127.0.0.1:40000`. Start it if needed:
```bash
cd coordinator && python main.py --port 40000
```

### Architecture:
```
dump/{module}/
  manifest.json      — read-only function map from IDA
  coverage.json      — coverage graph, managed by API daemon
  raw_funcs/         — read-only Hex-Rays dump
  resolved_funcs/    — working copy, soldiers improve code here
  procon/            — contour graphs (graph.json only, no code duplication)
```

## For Subagents

If you are a subagent (soldier/corporal), **DO NOT** explore or read the full project directory. Read your orders from `agents/` and work through the API at `http://127.0.0.1:40000`.

Do not modify:
- `raw_funcs/` (read-only reference)
- `manifest.json` (read-only reference)
- `coverage.json` (managed by API daemon)
- `ida_dump.py`
- This file
