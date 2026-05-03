#!/usr/bin/env python3
"""Graphify overview skill — extract architectural highlights from GRAPH_REPORT.md."""

import os
import re
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "hooks")
)

from shared.graphify_context import load_dedup_set, save_dedup_set


def extract_god_nodes(report_text):
    """Extract top God Nodes as (name, edge_count) tuples."""
    results = []
    in_section = False
    for line in report_text.splitlines():
        if "God Nodes" in line:
            in_section = True
            continue
        if in_section:
            if line.startswith("##"):
                break
            m = re.match(r"\d+\.\s+`([^`]+)`\s+-\s+(\d+)\s+edges", line)
            if m:
                results.append((m.group(1), int(m.group(2))))
    return results


def extract_surprising(report_text):
    """Extract surprising connections as description strings."""
    results = []
    in_section = False
    for line in report_text.splitlines():
        if "Surprising Connections" in line:
            in_section = True
            continue
        if in_section:
            if line.startswith("##"):
                break
            if line.startswith("- "):
                results.append(line[2:].strip())
            elif line.startswith("  ") and results:
                results[-1] += " | " + line.strip()
    return results


def extract_communities(report_text):
    """Extract community summaries."""
    results = []
    lines = report_text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"### Community (\d+)", lines[i])
        if m:
            comm = {"id": int(m.group(1)), "cohesion": 0.0, "nodes": ""}
            if i + 1 < len(lines):
                cm = re.search(r"Cohesion:\s*([\d.]+)", lines[i + 1])
                if cm:
                    comm["cohesion"] = float(cm.group(1))
            if i + 2 < len(lines):
                comm["nodes"] = lines[i + 2].strip()
            results.append(comm)
        i += 1
    return results[:15]


def generate_overview(project_root, session_id=None, ramdisk_dir=None):
    """Generate full overview output and seed dedup set."""
    report_path = os.path.join(project_root, "graphify-out", "GRAPH_REPORT.md")
    if not os.path.isfile(report_path):
        return "Graph report not found. Run: graphify update"

    with open(report_path) as f:
        text = f.read()

    god_nodes = extract_god_nodes(text)
    surprising = extract_surprising(text)
    communities = extract_communities(text)

    lines = ["# Structural Overview"]
    lines.append("")
    lines.append("## Hub Nodes (God Nodes)")
    for name, edges in god_nodes:
        lines.append(f"  {name} ({edges} edges)")

    if surprising:
        lines.append("")
        lines.append("## Surprising Connections")
        for conn in surprising[:5]:
            lines.append(f"  {conn}")

    if communities:
        lines.append("")
        lines.append("## Top Communities")
        for c in communities[:10]:
            lines.append(f"  C{c['id']} (cohesion:{c['cohesion']}) {c['nodes'][:80]}")

    output = "\n".join(lines)

    # Seed dedup set with all file paths mentioned
    if session_id:
        file_paths = set(re.findall(r"[\w/]+\.py", text))
        existing = load_dedup_set(session_id, ramdisk_dir)
        existing.update(file_paths)
        save_dedup_set(session_id, existing, ramdisk_dir)

    return output


if __name__ == "__main__":
    project = (
        sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    )
    # Walk up to find graphify-out
    candidate = project
    for _ in range(10):
        if os.path.isdir(os.path.join(candidate, "graphify-out")):
            break
        candidate = os.path.dirname(candidate)
    session_id = os.environ.get("TORUS_SESSION_ID", "standalone")
    print(generate_overview(candidate, session_id))
