# /graphify-overview — Structural Architecture Overview

## When to use
When you need a high-level view of the project's structural graph:
God Nodes (most connected), communities, and surprising connections.
Seeds the dedup set so subsequent Mode 1 injections skip reported nodes.

## Trigger
Manual only — invoke via `run_tool("torus-skills", "invoke_skill", {"name": "graphify-overview"})`

## Steps
1. Find nearest `graphify-out/GRAPH_REPORT.md`
2. Extract God Nodes (top 10), Surprising Connections, top Communities
3. Format concise output (≤2000 tokens)
4. Seed node dedup set with all mentioned file paths

## Output
Printed to stdout — appears in conversation as structural context.
