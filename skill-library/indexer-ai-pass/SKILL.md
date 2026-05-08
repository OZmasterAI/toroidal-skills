# /indexer-ai-pass — AI Edge Discovery Pipeline

## When to use
When user says "indexer ai pass", "tier 3 pass", "AI edge discovery", "run AI indexer",
or wants to find code relationships that static analysis missed.

## Commands
- `/invoke indexer-ai-pass [--project PATH] [--dry-run] [--batch-size N] [--pass 1|2|3|all]`

Defaults: `--project` (required), `--batch-size 10`, `--pass all`

## Flow

### 1. VALIDATE
Check project has Tier 1 index:
```bash
python3 -c "
import sys; sys.path.insert(0, '$HOME/.claude/toroidal-indexer')
from indexer.schema import connect_code_graph
db = connect_code_graph()
r = db.query('SELECT count() FROM code_node GROUP ALL')
count = r[0].get('count', 0) if r else 0
print(f'Nodes: {count}')
assert count > 0, 'No code_node entries — run Tier 1 build first'
"
```
If assertion fails, tell user to run `python3 ~/.claude/toroidal-indexer/indexer/build.py --project PATH` first.

### 2. PLAN
Get file list and batch plan:
```bash
python3 ~/.claude/toroidal-indexer/scripts/ai_pass.py run --project PATH --dry-run --batch-size N
```
Parse the JSON output. Show user:
- Total files, batch count, estimated agents (batches * 2 + 1)
- Estimated cost: ~$0.002 per Haiku batch, ~$0.01 per Sonnet batch
- Which passes will run (based on `--pass` flag)

Ask user to confirm before proceeding.

### 3. PASS 1 — HAIKU FLEET
Generate prompt for each batch using the `prompt` subcommand:
```bash
python3 ~/.claude/toroidal-indexer/scripts/ai_pass.py prompt --project PATH --pass 1 --batch INDEX --batch-size N
```

Spawn **ALL Pass 1 agents in parallel** (single message, multiple Agent calls):
```
Agent(subagent_type="explore", model="haiku", prompt=<generated prompt>)
```

For each completed agent:
1. Get the agent output text (JSON edge array)
2. Pipe to storage:
```bash
echo '<agent_output_json_array>' | python3 ~/.claude/toroidal-indexer/scripts/ai_pass.py store --stdin --project PROJECT_NAME --pass 1
```
3. Check the returned JSON summary for errors

**CRITICAL: Wait for ALL Pass 1 agents to complete AND all edges to be stored before proceeding to Pass 2.**

If more than 5 batches, split into waves of 5 agents each.

If `--pass 1`, stop here and show summary. Otherwise continue.

### 4. PASS 2 — SONNET FLEET
Generate prompt for each batch (includes Pass 1 edges as context):
```bash
python3 ~/.claude/toroidal-indexer/scripts/ai_pass.py prompt --project PATH --pass 2 --batch INDEX --batch-size N
```

Spawn **ALL Pass 2 agents in parallel**:
```
Agent(subagent_type="explore", model="sonnet", prompt=<generated prompt>)
```

For each completed agent:
1. Parse output — agent should return JSON array
2. Store: `echo '<json>' | python3 ~/.claude/toroidal-indexer/scripts/ai_pass.py store --stdin --project PROJECT_NAME --pass 2`

**CRITICAL: Wait for ALL Pass 2 storage to complete before proceeding to Pass 3.**

If `--pass 2`, stop here.

### 5. PASS 3 — SONNET REVIEWER
Generate the reviewer prompt:
```bash
python3 ~/.claude/toroidal-indexer/scripts/ai_pass.py prompt --project PATH --pass 3
```

Spawn single reviewer:
```
Agent(subagent_type="builder", model="sonnet", prompt=<generated prompt>)
```

Parse and store with `--pass 3`.

### 6. SUMMARY
Report final results:
```bash
python3 -c "
import sys; sys.path.insert(0, '$HOME/.claude/toroidal-indexer')
from indexer.schema import connect_code_graph, VALID_RELATIONS
db = connect_code_graph()
total = 0
for rel in VALID_RELATIONS:
    for p in [1, 2, 3]:
        r = db.query(f'SELECT count() FROM {rel} WHERE pass={p} GROUP ALL')
        c = r[0].get('count', 0) if r else 0
        if c > 0:
            print(f'  Pass {p} | {rel}: {c}')
            total += c
print(f'Total new AI edges: {total}')
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
- ALL agents within a pass run in PARALLEL (multiple Agent calls in one message)
- Maximum 5 Agent calls per message (split into waves if more batches)
- Pass 3 receives compact graph summary, NOT raw edge JSON
- All AI edges get confidence=0.8, tagged with pass number
