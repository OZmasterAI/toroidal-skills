# Toroidal Skills

Skill library and MCP server for Claude Code. Each skill is a self-contained `SKILL.md` file with instructions that Claude Code agents load and execute on demand. Works standalone or as part of the [Torus Framework](https://github.com/OZmasterAI/Torus-Framework).

## What's in here

- **`trs_skill_server.py`** -- MCP server exposing 10 tools: `list_skills`, `invoke_skill`, `search_skills`, `capture_skill`, `trigger_evolution`, `skill_health`, `skill_usage`, `record_outcome`, `skill_lineage`, `self_improve`
- **`skill-library/`** -- 54 skills covering workflows, tooling, and reference patterns

## Skills

| Category | Skills |
|----------|--------|
| **Core loop** | brainstorm, writing-plans, implement, build, test, review, commit, wrap-up |
| **Planning** | prp, prp-wave, deep-dive, explore, research |
| **Diagnostics** | diagnose, fix, causal-chain-analysis, analyze-errors, trace-memory |
| **Quality** | audit, benchmark, sprint, introspect |
| **Evolution** | super-evolve, super-health, super-prof-optimize, create-skill |
| **Analytics** | gate-timing, gate-health-correlation, session-metrics, code-hotspots, tool-recommendations |
| **Agents** | agents, create-agents, chain, experiment |
| **Wiki/Obsidian** | wiki-ingest, wiki-lint, wiki-present, wiki-update, obsidian-cli-ref, obsidian-markdown-ref |
| **Utilities** | status, recall, working-summary, clear-topic, tag-branch, deploy, web, learn, ralph |
| **Testing** | generate-test-stubs, replay-events, test-mcp-http |
| **UI** | bubbletea-designer |

## Architecture

```
Claude Code  -->  toolshed (stdio bridge)  -->  trs_skill_server.py (HTTP :8743)
                                                    |
                                                    +-- skill-library/  (SKILL.md files)
                                                    +-- SQLite          (quality tracking, BM25 index)
                                                    +-- nomic embeddings (semantic search)
```

Skills are invoked by name. The server reads the `SKILL.md`, records the selection in SQLite for quality tracking, and returns the full instructions. After execution, `record_outcome` feeds back into health scoring and evolution triggers.

## Setup

### Standalone

```bash
git clone https://github.com/OZmasterAI/toroidal-skills.git
cd toroidal-skills
pip install -r requirements.txt
python3 trs_skill_server.py --http --port 8743
```

Then register it in your Claude Code MCP config (`~/.claude/mcp.json`):

```json
{
  "mcpServers": {
    "skills": {
      "type": "http",
      "url": "http://127.0.0.1:8743/mcp"
    }
  }
}
```

### As a submodule

Can be used as a submodule in any project, including [Torus-Framework](https://github.com/OZmasterAI/Torus-Framework):

```bash
git submodule add https://github.com/OZmasterAI/toroidal-skills.git torus-skills
```

## Skill anatomy

Each skill lives in `skill-library/<name>/SKILL.md` and follows this structure:

```markdown
# Skill Name

<instructions for Claude Code to follow when this skill is invoked>
```

Some skills reference shared modules from the Torus Framework hooks directory (`TORUS_HOOKS_DIR`). When running standalone without Torus, these skills will note the missing dependency.

## Quality tracking

The server tracks per-skill metrics in SQLite:
- **Selection count** -- how often a skill is invoked
- **Completion rate** -- success vs failure outcomes
- **Fallback rate** -- how often the skill falls back to alternatives
- Skills with completion rate < 35% or fallback rate > 40% are flagged as degraded
- Degraded skills can be evolved via `trigger_evolution` (auto-repair or derived variants)

## Works with Toolshed

Toroidal Skills and [Toolshed](https://github.com/OZmasterAI/toroidal-toolshed) are designed to work together. Toolshed is an MCP proxy that reduces context window overhead — instead of exposing all tool schemas directly, your agent connects to Toolshed and discovers tools on demand. Register the skill server as a Toolshed backend and all 10 skill tools are accessible through Toolshed's 2-tool interface (`list_tools` + `run_tool`).

Both can also be used independently.

## Built with

Built with [Torus Framework](https://github.com/OZmasterAI/Torus-Framework) — a self-evolving quality framework for Claude Code.

## License

Apache-2.0
