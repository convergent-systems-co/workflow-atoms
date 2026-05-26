# Temporal Workflow Compiler

`scripts/compile-to-temporal.py` converts a workflow-atoms composition JSON into a
runnable [Temporal](https://temporal.io) Python workflow skeleton.

## Requirements

```bash
pip install temporalio
```

The compiler itself has no runtime dependencies beyond the Python standard library.
`temporalio` is required only to execute the generated code.

## Usage

**Print to stdout:**

```bash
python3 scripts/compile-to-temporal.py workflows/olympus-agentic-loop.json
```

**Write to a file:**

```bash
python3 scripts/compile-to-temporal.py workflows/olympus-agentic-loop.json \
  --output src/workflows/olympus_agentic_loop.py
```

**Compile all workflows at once:**

```bash
for f in workflows/*.json; do
  slug=$(basename "$f" .json | tr '-' '_')
  python3 scripts/compile-to-temporal.py "$f" \
    --output "src/workflows/${slug}.py"
done
```

## Concept mapping

| workflow-atoms concept | Temporal concept |
|---|---|
| `step-type` atom | `@activity.defn` function + `workflow.execute_activity` call |
| `gate-type` atom | `await workflow.wait_condition(...)` inline check |
| `trigger.atom_id == "…/manual"` | `client.start_workflow(...)` — generated as a comment |
| `trigger.atom_id == "…/schedule"` | Temporal schedule — generated as a comment |
| `loop_back_to` | Python `for _iteration in range(max_iterations):` loop |
| `termination_conditions` | `# if <condition>: break` comment stubs inside the loop |
| `on_failure: "fail"` | `workflow.ApplicationError` note on the gate step |

## How it works

```
composition.json
  └─ trigger.atom_id  ──► trigger comment block at top of file
  └─ steps[].atom_id  ──► @activity.defn stub + execute_activity call
                           (gate-type steps become wait_condition calls)
  └─ loop_back_to     ──► for loop wrapping all steps
  └─ max_iterations   ──► range(N) upper bound on the for loop
```

The compiler always produces a syntactically valid Python file. Gate steps and
termination conditions are emitted as `wait_condition(lambda: True)` placeholders
with inline comments — replace the lambda with real signal or condition logic before
running in production.

## Example

Input (`workflows/olympus-agentic-loop.json`):

```json
{
  "name": "Olympus Agentic Toolloop",
  "trigger": {"atom_id": "workflow-atoms/trigger-type/manual"},
  "steps": [
    {"id": "policy-gate",    "atom_id": "workflow-atoms/gate-type/policy-broker-gate"},
    {"id": "invoke-llm",     "atom_id": "workflow-atoms/step-type/invoke-llm"},
    {"id": "parse-tool-calls","atom_id": "workflow-atoms/step-type/parse-tool-calls"},
    {"id": "execute-tools",  "atom_id": "workflow-atoms/step-type/execute-tool-calls"},
    {"id": "append-results", "atom_id": "workflow-atoms/step-type/append-tool-results"},
    {"id": "termination-gate","atom_id": "workflow-atoms/gate-type/no-tool-calls-gate"}
  ]
}
```

Produces a `OlympusAgenticToolloopWorkflow` class with:
- A `run(self, inputs)` method containing six steps (two `wait_condition` gates, four
  `execute_activity` calls).
- Four `@activity.defn` stub functions (`invoke_llm`, `parse_tool_calls`,
  `execute_tools`, `append_results`).
- A `main()` worker bootstrap function.

## Extending the compiler

To change how a specific atom is compiled, override the `_is_gate` helper or add a
custom branch in `compile_to_temporal_python` keyed on `atom_id`. The compiler is
intentionally simple — it is a starting point, not a production runtime adapter.
