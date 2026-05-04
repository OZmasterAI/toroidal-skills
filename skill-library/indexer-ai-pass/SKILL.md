# /indexer-ai-pass — AI Edge Discovery Pipeline

## When to use
When user says "indexer ai pass", "tier 3 pass", "AI edge discovery", "run AI indexer",
or wants to find code relationships that static analysis missed.

## Commands
- `/invoke indexer-ai-pass [--project PATH] [--dry-run] [--batch-size N] [--pass 1|2|3|all]`

Defaults: `--project /home/crab/.claude`, `--batch-size 10`, `--pass all`

## Flow

### 1. VALIDATE
Check project has Tier 1 index:
```bash
python3 -c "
import sys; sys.path.insert(0, '$HOME/.claude/hooks')
from shared.indexer_schema import connect_code_graph
db = connect_code_graph()
r = db.query('SELECT count() FROM code_node GROUP ALL')
count = r[0].get('count', 0) if r else 0
print(f'Nodes: {count}')
assert count > 0, 'No code_node entries — run Tier 1 build first'
"
```
If assertion fails, tell user to run `python3 scripts/indexer_build.py --project PATH` first.

### 2. PLAN
Get file list and batch plan:
```bash
python3 scripts/indexer_ai_pass.py run --project PATH --dry-run --batch-size N
```
Parse the JSON output. Show user:
- Total files, batch count, estimated agents (batches * 2 + 1)
- Estimated cost: ~$0.002 per Haiku agent, ~$0.01 per Sonnet agent
- Which passes will run (based on `--pass` flag)

Ask user to confirm before proceeding.

### 3. PASS 1 — HAIKU FLEET
Get file list:
```bash
python3 -c "
import sys, json; sys.path.insert(0, '$HOME/.claude/hooks')
from scripts.indexer_ai_pass import _find_source_files, _batch
files = _find_source_files('PROJECT_PATH')
batches = list(_batch(files, BATCH_SIZE))
print(json.dumps(batches))
"
```

For each batch, generate the prompt:
```bash
python3 -c "
import sys, json; sys.path.insert(0, '$HOME/.claude/hooks')
from scripts.indexer_ai_pass import _pass1_prompt
prompt = _pass1_prompt(BATCH_FILES, 'PROJECT_PATH')
print(prompt)
"
```

Spawn **ALL Pass 1 agents in parallel** (single message, multiple Task calls):
```
Task(subagent_type="explore", model="haiku", prompt=<generated prompt>)
```

For each completed agent:
1. Get the Task output text
2. Parse it: `python3 -c "from scripts.indexer_ai_pass import parse_agent_output; ..."`
3. Pipe parsed JSON to storage:
```bash
echo '<parsed_json_array>' | python3 scripts/indexer_ai_pass.py store --stdin --project PROJECT_NAME --pass 1
```
4. Check the returned JSON summary for errors

**CRITICAL: Wait for ALL Pass 1 agents to complete AND all edges to be stored before proceeding to Pass 2.**

Verify Pass 1 storage:
```bash
python3 -c "
import sys; sys.path.insert(0, '$HOME/.claude/hooks')
from shared.indexer_schema import connect_code_graph
db = connect_code_graph()
for rel in ['calls', 'imports', 'reads', 'writes', 'implements']:
    r = db.query(f'SELECT count() FROM {rel} WHERE pass=1 GROUP ALL')
    c = r[0].get('count', 0) if r else 0
    if c > 0: print(f'  {rel}: {c} Pass 1 edges')
"
```

If `--pass 1`, stop here and show summary. Otherwise continue.

### 4. PASS 2 — SONNET FLEET
For each batch, get Pass 1 edges as context:
```bash
python3 -c "
import sys, json; sys.path.insert(0, '$HOME/.claude/hooks')
from scripts.indexer_ai_pass import get_edges_for_files, _pass2_prompt
from shared.indexer_schema import connect_code_graph
db = connect_code_graph()
edges = get_edges_for_files(db, 'PROJECT_NAME', BATCH_FILES)
prompt = _pass2_prompt(BATCH_FILES, edges, 'PROJECT_PATH')
print(prompt)
"
```

Spawn **ALL Pass 2 agents in parallel**:
```
Task(subagent_type="explore", model="sonnet", prompt=<generated prompt>)
```

For each completed agent:
1. Parse output with `parse_agent_output()`
2. Store: `echo '<json>' | python3 scripts/indexer_ai_pass.py store --stdin --project PROJECT_NAME --pass 2`

**CRITICAL: Wait for ALL Pass 2 storage to complete before proceeding to Pass 3.**

If `--pass 2`, stop here.

### 5. PASS 3 — SONNET REVIEWER
Get compact graph summary (~2KB, NOT raw edges):
```bash
python3 -c "
import sys, json; sys.path.insert(0, '$HOME/.claude/hooks')
from scripts.indexer_ai_pass import get_graph_summary, _pass3_prompt
from shared.indexer_schema import connect_code_graph
db = connect_code_graph()
summary = get_graph_summary(db, 'PROJECT_NAME')
prompt = _pass3_prompt(summary, 'PROJECT_PATH')
print(prompt)
"
```

Spawn single reviewer:
```
Task(subagent_type="builder", model="sonnet", prompt=<generated prompt>)
```

Parse and store with `--pass 3`.

### 6. SUMMARY
Report final results:
```bash
python3 -c "
import sys; sys.path.insert(0, '$HOME/.claude/hooks')
from shared.indexer_schema import connect_code_graph
db = connect_code_graph()
total = 0
for rel in ['calls', 'imports', 'reads', 'writes', 'implements']:
    for p in [1, 2, 3]:
        r = db.query(f'SELECT count() FROM {rel} WHERE pass={p} GROUP ALL')
        c = r[0].get('count', 0) if r else 0
        if c > 0:
            print(f'  Pass {p} | {rel}: {c}')
            total += c
    ai = db.query(f'SELECT count() FROM {rel} WHERE confidence=0.8 GROUP ALL')
    t = db.query(f'SELECT count() FROM {rel} GROUP ALL')
    ai_c = ai[0].get('count', 0) if ai else 0
    t_c = t[0].get('count', 0) if t else 0
    print(f'  {rel}: {ai_c} AI / {t_c} total')
print(f'Total AI edges: {total}')
"
```

## Dry-run mode
With `--dry-run`, show the plan (file count, batches, agent count, cost estimate) without spawning any agents.

## Single-pass mode
- `--pass 1`: Only Pass 1 (Haiku, cheap, good for testing)
- `--pass 2`: Only Pass 2 (requires Pass 1 already stored)
- `--pass 3`: Only Pass 3 (requires Pass 1+2 already stored)
- `--pass all` (default): All three passes sequentially

## Rollback
Per-pass: `DELETE calls WHERE pass=1; DELETE imports WHERE pass=1;` etc.
Full AI: `DELETE calls WHERE confidence=0.8;` for each relation table.

## Rules
- NEVER spawn Pass 2 agents before Pass 1 storage is fully complete
- NEVER spawn Pass 3 before Pass 2 storage is fully complete
- ALL agents within a pass run in PARALLEL (multiple Task calls in one message)
- Maximum 5 Task calls per message (split into waves if more batches)
- Pass 3 receives compact graph summary, NOT raw edge JSON
- All AI edges get confidence=0.8, tagged with pass number
- Gate 10 enforces model= on Task calls — always include it
