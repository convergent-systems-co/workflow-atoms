#!/usr/bin/env python3
"""Compile a workflow-atoms composition to a Temporal workflow definition.

Usage:
    python3 scripts/compile-to-temporal.py <workflow.json>
    python3 scripts/compile-to-temporal.py <workflow.json> --output <path>

Reads a workflow composition JSON and generates a Temporal Python workflow
skeleton that implements the same step sequence.

Temporal concepts mapped:
    step-type  →  @activity.defn function + workflow.execute_activity call
    gate-type  →  inline workflow.wait_condition or conditional branch
    trigger.atom_id == "…/manual"    →  Temporal start_workflow API call comment
    trigger.atom_id == "…/schedule"  →  Temporal schedule comment
    loop composition (loop_back_to)  →  Python while loop with iteration cap
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def _is_gate(atom_id: str) -> bool:
    return "/gate-type/" in atom_id


def _step_slug(step: dict) -> str:
    return step.get("id", "step").replace("-", "_")


def _trigger_comment(trigger: dict) -> str:
    atom_id = trigger.get("atom_id", "")
    if "manual" in atom_id:
        return (
            "# Trigger: manual — start via Temporal client:\n"
            "#   await client.start_workflow({}Workflow.run, inputs, id=..., task_queue=...)".format
        )
    if "schedule" in atom_id:
        return (
            "# Trigger: schedule — register a Temporal schedule pointing at this workflow."
        )
    if "push" in atom_id or "pr" in atom_id:
        return (
            "# Trigger: {} — wire a webhook or CI event to start_workflow.".format(atom_id.rsplit("/", 1)[-1])
        )
    return "# Trigger: {}".format(atom_id)


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------

def compile_to_temporal_python(composition: dict) -> str:
    name = composition.get("name", "UnnamedWorkflow")
    slug = name.replace(" ", "_").replace("-", "_")
    wf_id = composition.get("id", slug)
    steps = composition.get("steps", [])
    has_loop = "loop_back_to" in composition
    max_iter = composition.get("max_iterations", 10)
    trigger = composition.get("trigger", {})
    termination_conditions = composition.get("termination_conditions", [])

    lines: list[str] = []

    # --- file header ---
    lines += [
        '"""',
        f"Temporal workflow skeleton — auto-generated from workflow-atoms.",
        f"Source composition: {wf_id}",
        f"Description: {composition.get('description', '')}",
        "",
        "Do not edit the activity stubs in-place; instead implement them in a",
        "separate module and register them on the Worker.",
        '"""',
        "from __future__ import annotations",
        "",
        "from datetime import timedelta",
        "",
        "from temporalio import activity, workflow",
        "from temporalio.client import Client",
        "from temporalio.worker import Worker",
        "",
        "",
    ]

    # --- trigger comment ---
    trig = trigger.get("atom_id", "")
    if "manual" in trig:
        lines.append(
            "# Trigger: manual — start via Temporal client:\n"
            f"#   await client.start_workflow({slug}Workflow.run, inputs,"
            " id='run-id', task_queue='default')"
        )
    elif "schedule" in trig:
        lines.append(
            "# Trigger: schedule — register a Temporal schedule pointing at this workflow."
        )
    else:
        lines.append(f"# Trigger: {trig}")
    lines.append("")

    # --- @workflow.defn class ---
    lines += [
        "@workflow.defn",
        f"class {slug}Workflow:",
        f'    """',
        f"    Auto-generated Temporal workflow for: {name}",
        f"    workflow-atoms ID: {wf_id}",
        f'    """',
        "",
        "    @workflow.run",
        "    async def run(self, inputs: dict) -> dict:",
    ]

    base_indent = "        "

    if has_loop:
        loop_back = composition["loop_back_to"]
        lines.append(f"{base_indent}# Agentic loop — max {max_iter} iterations")
        lines.append(f"{base_indent}for _iteration in range({max_iter}):")
        step_indent = base_indent + "    "
    else:
        step_indent = base_indent

    for step in steps:
        step_id = step.get("id", "step")
        step_name = step.get("name", step_id)
        atom_id = step.get("atom_id", "")
        slug_s = _step_slug(step)
        deps = step.get("depends_on", [])
        on_fail = step.get("on_failure", "fail")

        lines.append(f"{step_indent}# --- {step_name} ---")
        if deps:
            lines.append(f"{step_indent}# depends_on: {deps}")

        if _is_gate(atom_id):
            # Gates become wait_condition calls or inline conditionals
            lines.append(
                f"{step_indent}# Gate: {atom_id.rsplit('/', 1)[-1]}"
            )
            lines.append(
                f"{step_indent}# Replace the lambda with actual signal/condition logic:"
            )
            lines.append(
                f"{step_indent}await workflow.wait_condition(lambda: True)"
                f"  # gate: {step_name}"
            )
            if on_fail == "fail":
                lines.append(
                    f"{step_indent}# on_failure=fail: raise workflow.ApplicationError if gate rejects"
                )
        else:
            lines.append(
                f"{step_indent}result_{slug_s} = await workflow.execute_activity("
            )
            lines.append(f"{step_indent}    {slug_s},")
            lines.append(f"{step_indent}    inputs,")
            lines.append(
                f"{step_indent}    schedule_to_close_timeout=timedelta(minutes=10),"
            )
            lines.append(f"{step_indent})")

        lines.append("")

    if has_loop:
        if termination_conditions:
            lines.append(f"{step_indent}# Termination conditions — implement these checks:")
            for cond in termination_conditions:
                lines.append(f"{step_indent}# if <{cond}>: break")
        lines.append(f"{step_indent}# Loop back to: {composition['loop_back_to']}")
        lines.append(f"{step_indent}# Remove 'pass' once termination checks are wired:")
        lines.append(f"{step_indent}pass")
        lines.append("")

    lines.append(f"{base_indent}return {{}}")
    lines.append("")
    lines.append("")

    # --- activity stubs ---
    activity_steps = [s for s in steps if not _is_gate(s.get("atom_id", ""))]

    if activity_steps:
        lines.append("# ---------------------------------------------------------------------------")
        lines.append("# Activity stubs — implement these with real logic and register on Worker")
        lines.append("# ---------------------------------------------------------------------------")
        lines.append("")

        for step in activity_steps:
            slug_s = _step_slug(step)
            step_name = step.get("name", slug_s)
            atom_id = step.get("atom_id", "")
            lines += [
                "@activity.defn",
                f"async def {slug_s}(inputs: dict) -> dict:",
                f'    """',
                f"    Activity for: {step_name}",
                f"    atom: {atom_id}",
                f'    """',
                f"    raise NotImplementedError(",
                f"        'Implement {slug_s} — see atom: {atom_id}'",
                f"    )",
                "",
            ]

    # --- worker bootstrap ---
    all_activities = [_step_slug(s) for s in activity_steps]
    activity_list = ", ".join(all_activities)
    lines += [
        "# ---------------------------------------------------------------------------",
        "# Worker bootstrap — wire activities and start the worker",
        "# ---------------------------------------------------------------------------",
        "",
        "async def main() -> None:",
        "    client = await Client.connect('localhost:7233')",
        "    async with Worker(",
        "        client,",
        "        task_queue='default',",
        f"        workflows=[{slug}Workflow],",
        f"        activities=[{activity_list}],",
        "    ):",
        "        await workflow.wait_condition(lambda: False)  # run forever",
        "",
        "",
        "if __name__ == '__main__':",
        "    import asyncio",
        "    asyncio.run(main())",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    if len(sys.argv) < 2:
        print(
            "Usage: python3 compile-to-temporal.py <workflow.json> [--output <path>]",
            file=sys.stderr,
        )
        return 1

    comp_path = Path(sys.argv[1])
    if not comp_path.exists():
        print(f"error: file not found: {comp_path}", file=sys.stderr)
        return 1

    composition = json.loads(comp_path.read_text(encoding="utf-8"))
    output = compile_to_temporal_python(composition)

    if len(sys.argv) >= 4 and sys.argv[2] == "--output":
        out_path = Path(sys.argv[3])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"wrote {out_path}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
