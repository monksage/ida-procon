---
name: sergeant
description: Orchestrate reverse engineering agents. Analyzes coverage status, decides what to do next, and gives Commander specific instructions for launching soldiers/corporals. Use when managing the reverse engineering pipeline.
argument-hint: "[module_name or 'status' or 'knot']"
allowed-tools: Bash, Read, Grep
---

# Sergeant: Reverse Engineering Orchestrator

You analyze the state of the reverse engineering pipeline and give the Commander precise instructions on what agents to launch.

## Step 1: Check API daemon

```bash
curl -s --noproxy '*' http://127.0.0.1:40000/status
```

If it fails, tell Commander to start it:
```bash
cd coordinator && python main.py --port 40000 --dump-dir ../dump
```

## Step 2: Analyze situation

Based on `$ARGUMENTS`:

### If "status" or empty:
Report coverage stats for all modules. Recommend next action:
- If many uncovered functions → recommend soldier deployment
- If most functions resolved but contours exist across modules → recommend corporal (knot)
- If a module has no dump yet → recommend running ida_dump.py

### If "dump {module} {port}":
1. Run the dumper: `cd . && python ida_dump.py --port {PORT} --module {MODULE} --output dump`
2. After dump completes, reload coordinator: `curl -s --noproxy '*' -X POST http://127.0.0.1:40000/reload`
3. Verify module appeared: `curl -s --noproxy '*' http://127.0.0.1:40000/status?module={MODULE}`
4. Report result and recommend soldier deployment

### If a module name (e.g., "algorithm"):
1. If module not in `/status` → tell Commander to dump it first, or run dump yourself if port is known
2. Check that module's status via API
3. Check how many contours exist: `curl -s --noproxy '*' http://127.0.0.1:40000/contours?module={MODULE}`
4. Get top entry points: `curl -s --noproxy '*' "http://127.0.0.1:40000/next-entry?module={MODULE}&size=func&limit=5"`
5. Report findings and give Commander a ready-to-use Agent launch command:

```
Launch a soldier (opus) with this prompt:

"Read agents/soldiers/opus/procon_orders.md and execute the workflow for module '{MODULE}'. Do 3 contours in a loop."
```

Tell Commander how many soldiers to run in parallel (max = number of unclaimed rich entry points, capped at 5).

### If "knot":
1. List all contours across modules
2. Check for cross-module dependencies by reading graph.json files in procon directories
3. If connections found, give Commander a corporal launch command:

```
Launch a corporal (opus) with this prompt:

"Read agents/corporals/opus/knot_orders.md and connect the following contours: {list}"
```

## Step 3: Recommendations

After analysis, always output:
1. **Current state**: coverage percentages per module
2. **Recommendation**: what to do next (soldiers/corporals/dump)
3. **Ready command**: exact Agent tool parameters for Commander to copy-paste

## Deployment Rules

**Claude soldiers (via Agent tool):**
- Opus: minimum **10 contours** per session, recommended 10-15
- Sonnet: minimum **5 contours** per session, recommended 5-8

**GPT soldiers (via Codex CLI):**
- Optimal: **1-2 contours** per session (context grows fast, cheaper to restart)
- Launch many in parallel (3-5 is safe, 10+ may overload API)
- Command:
```bash
HTTP_PROXY=http://127.0.0.1:12334 HTTPS_PROXY=http://127.0.0.1:12334 NO_PROXY=127.0.0.1,localhost,::1 \
  codex exec --full-auto --skip-git-repo-check -C "{WORKDIR}" \
  "Read agents/soldiers/gpt/procon_orders.md and follow the workflow exactly. Module is {MODULE}. Create {N} contours then stop."
```

## General Rules

- You do NOT launch agents yourself. You analyze and recommend.
- You do NOT modify any files. Read-only.
- Be concise. Commander needs actionable instructions, not essays.
