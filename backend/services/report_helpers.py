"""
report_helpers.py — I-6: sections are structured dicts serialised only at export.
"""
from __future__ import annotations
from typing import Any, Dict, List


def build_topology_section(selection: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "topology_selection",
        "recommended_topology": selection.get("recommended_topology"),
        "runner_up_topology":   selection.get("runner_up_topology"),
        "recommended_mode":      selection.get("recommended_mode"),
        "top_3":                 selection.get("top_3", []),
        "why_selected":         selection.get("why_selected", []),
        "why_runner_up_lost":   selection.get("why_runner_up_lost", []),
        "ranking": [
            {"topology": r["topology"], "final_score": r["final_score"],
             "penalty": r["penalty"], "penalty_details": r.get("penalty_details", [])}
            for r in selection.get("ranking", [])
        ],
    }


def build_step_section(step_name: str, results: Any) -> Dict[str, Any]:
    SKIP = {"educator_output", "tradeoff_output"}
    params: Dict[str, Any] = {}
    warnings: List[str]    = []
    errors:   List[str]    = []
    if isinstance(results, dict):
        for k, v in results.items():
            if k in SKIP:
                continue
            if k == "error":
                errors.append(str(v))
            elif k in {"warnings", "violations"}:
                (warnings if isinstance(v, list) else [warnings]).extend(
                    str(x) for x in (v if isinstance(v, list) else [v])
                )
            else:
                params[k] = v
    return {"type": "step_result", "step_name": step_name,
            "params": params, "warnings": warnings, "errors": errors}


def build_advisory_section(title: str, advisory: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type":     "advisory",
        "title":    title,
        "status":   advisory.get("status"),
        "blocking": advisory.get("blocking", False),
        "enabled":  advisory.get("enabled", True),
        "details":  advisory.get("details", {}),
        "notes":    advisory.get("notes", []),
    }


def build_approved_tuning_section(approved_tuning: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type":            "approved_tuning",
        "controller_mode": approved_tuning.get("controller_mode"),
        "topology":        approved_tuning.get("topology"),
        "current_loop":    approved_tuning.get("current_loop", {}),
        "voltage_loop":    approved_tuning.get("voltage_loop", {}),
    }


def section_to_markdown(section: Any) -> str:
    """Serialise a structured section dict to markdown (I-6). Backward-compat with strings."""
    if isinstance(section, str):
        return section
    if not isinstance(section, dict):
        return str(section)
    kind = section.get("type")
    if kind == "topology_selection":
        lines = ["## Topology Selection",
                 f"**Recommended:** {section['recommended_topology']}",
                 f"**Recommended mode:** {section.get('recommended_mode')}",
                 f"**Runner-up:** {section['runner_up_topology']}"]
        for c in section.get("top_3", []):
            lines.append(f"- Top choice: {c.get('topology')} ({c.get('mode')}) score={c.get('final_score')}")
        for r in section.get("ranking", []):
            lines.append(f"- {r['topology']}: score={r['final_score']}, penalty={r['penalty']}"
                         + (f" ({', '.join(r['penalty_details'])})" if r.get("penalty_details") else ""))
        return "\n".join(lines)
    if kind == "step_result":
        lines = [f"## {section['step_name'].replace('_',' ').title()}"]
        for k, v in section.get("params", {}).items():
            lines.append(f"- **{k}**: {v}")
        for w in section.get("warnings", []):
            lines.append(f"- Warning: {w}")
        for e in section.get("errors", []):
            lines.append(f"- Error: {e}")
        return "\n".join(lines)
    if kind == "advisory":
        lines = [f"## {section['title']}",
                 f"- **Status:** {section['status']}",
                 f"- **Blocking:** {section['blocking']}"]
        details = section.get("details", {})
        if isinstance(details, dict):
            for k, v in details.items():
                lines.append(f"- **{k}**: {v}")
        for note in section.get("notes", []):
            lines.append(f"- {note}")
        return "\n".join(lines)
    if kind == "approved_tuning":
        lines = ["## Approved Retuned Coefficients",
                 f"- **Controller mode:** {section.get('controller_mode')}",
                 f"- **Topology:** {section.get('topology')}"]
        for lp in ("current_loop", "voltage_loop"):
            loop = section.get(lp, {})
            if loop:
                lines.append(f"### {lp.replace('_',' ').title()}")
                for k, v in loop.items():
                    lines.append(f"- **{k}**: {v}")
        return "\n".join(lines)
    lines = []
    for k, v in section.items():
        if k != "type":
            lines.append(f"- **{k}**: {v}")
    return "\n".join(lines)


def compile_report(sections: List[str]) -> str:
    return "\n\n".join(s for s in sections if s and str(s).strip())
