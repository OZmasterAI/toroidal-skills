---
name: indexer-ai-pass
description: "Run Tier 3 AI edge discovery on a code graph project. Orchestrates a 3-pass agent pipeline: Pass 1 (Haiku fleet) extracts explicit edges from file batches, Pass 2 (Sonnet fleet) finds implicit coupling, Pass 3 (Sonnet reviewer) detects structural anomalies. Requires T1 index to exist. When user says 'indexer ai pass', 'tier 3', 'AI edge discovery', 'run AI indexer', 't3 pass', or wants code relationships that static analysis missed."
---

# /indexer-ai-pass — AI Edge Discovery Pipeline

## Arguments
- `project_path`: (required) Absolute path to the project root
- `project_name`: (optional) Override project name, default: basename of project_path
- `batch_size`: (optional) Files per agent batch, default: 10
- `pass_num`: (optional) Which pass to run: 1, 2, 3, or "all" (default: "all")
- `dry_run`: (optional) If "true", show plan without executing

## Flow

### 1. VALIDATE
Check project has T1 index:
```bash
python3 -c "
import sys; sys.path.insert(0, '$HOME/.claude/toroidal-indexer')
from indexer.schema import connect_code_graph
db = connect_code_graph()
r = db.query(\"SELECT count() AS c FROM code_node WHERE project='\$PROJECT_NAME' GROUP ALL\")
count = r[0]['c'] if r else 0
print(f'Nodes: {count}')
if count == 0: print('ERROR: No nodes — run T1 build first'); sys.exit(1)
"
```
Replace `$PROJECT_NAME` with the actual project name.
If 0 nodes, tell user to run T1 first and stop.

### 2. PLAN
```bash
python3 ~/.claude/toroidal-indexer/scripts/ai_pass.py run --project $PROJECT_PATH --dry-run --batch-size $BATCH_SIZE
```
Parse the JSON output. Show user: total files, batch count, estimated agents, which passes will run.
Ask user to confirm before proceeding. If `dry_run` is "true", stop here.

### 3. PASS 1 — HAIKU FLEET (explicit edge extraction)
For each batch index (0 to pass1_batches-1):
1. Generate the prompt:
```bash
python3 ~/.claude/toroidal-indexer/scripts/ai_pass.py prompt --project $PROJECT_PATH --pass 1 --batch $INDEX --batch-size $BATCH_SIZE
```
2. Capture the full prompt output text.

Spawn agents in waves of up to 5 per message. Each agent:
```
Agent(subagent_type="builder", model="haiku", prompt="You are a code analysis agent. Read the files listed below and output ONLY a valid JSON array of code edges. No markdown fencing, no explanation.\n\n<prompt from step 1>\n\nAfter reading all files, output the JSON array.")
```
Use `builder` type so agents can Read files.

For each completed agent, extract the JSON array from its response and store:
```bash
echo '$AGENT_JSON_OUTPUT' | python3 ~/.claude/toroidal-indexer/scripts/ai_pass.py store --stdin --project $PROJECT_NAME --pass 1
```

**CRITICAL: ALL Pass 1 agents must complete and ALL edges must be stored before starting Pass 2.**

If `pass_num` is "1", skip to SUMMARY.

### 4. PASS 2 — SONNET FLEET (implicit coupling)
For each batch index:
1. Generate the prompt (includes Pass 1 edges as context):
```bash
python3 ~/.claude/toroidal-indexer/scripts/ai_pass.py prompt --project $PROJECT_PATH --pass 2 --batch $INDEX --batch-size $BATCH_SIZE
```
2. Spawn agents in waves of up to 5:
```
Agent(subagent_type="builder", model="sonnet", prompt="You are a code coupling analyst. Read the files and find IMPLICIT relationships not in the known edges list. Output ONLY a valid JSON array.\n\n<prompt from step 1>")
```

Store each result with `--pass 2`.

**CRITICAL: ALL Pass 2 storage must complete before Pass 3.**

If `pass_num` is "2", skip to SUMMARY.

### 5. PASS 3 — SONNET REVIEWER (anomaly detection)
Generate the reviewer prompt:
```bash
python3 ~/.claude/toroidal-indexer/scripts/ai_pass.py prompt --project $PROJECT_PATH --pass 3
```

Spawn single reviewer agent:
```
Agent(subagent_type="builder", model="sonnet", prompt="You are a code graph reviewer. Analyze the graph summary below and find structural anomalies — isolated nodes that should have edges, missing connections, asymmetric relationships. Output ONLY a valid JSON array of correction edges.\n\n<prompt from above>")
```

Store result with `--pass 3`.

### 6. SUMMARY
```bash
python3 -c "
import sys; sys.path.insert(0, '$HOME/.claude/toroidal-indexer')
from indexer.schema import connect_code_graph, VALID_RELATIONS
db = connect_code_graph()
total = 0
for rel in sorted(VALID_RELATIONS):
    for p in [1, 2, 3]:
        try:
            r = db.query(f'SELECT count() AS c FROM {rel} WHERE pass={p} AND in.project=\"\$PROJECT_NAME\" GROUP ALL')
            c = r[0]['c'] if r else 0
        except: c = 0
        if c > 0:
            print(f'  Pass {p} | {rel}: {c}')
            total += c
print(f'Total AI edges: {total}')
"
```
Replace `$PROJECT_NAME`. Report per-pass breakdown and total.

## Rollback
Per-pass: `DELETE calls WHERE pass=1 AND in.project='PROJECT_NAME'` etc. for each relation.
Full AI rollback: delete edges where pass IN [1,2,3] for the project.

## Rules
- NEVER start Pass N+1 before Pass N is fully stored
- Agents within a pass run in PARALLEL (multiple Agent calls in one message)
- Maximum 5 Agent calls per message — split into waves if more batches
- Use `builder` subagent type (agents need Read access to source files)
- Pass 3 receives a compact graph summary, NOT raw edges
- All AI edges get confidence=0.8, tagged with pass number
- If a batch agent returns invalid JSON, skip it and log the error
