# GitHub Actions YAML Compiler

`scripts/compile-to-github-actions.py` converts a workflow-atoms composition JSON into a runnable GitHub Actions workflow YAML file.

## Requirements

```bash
pip install pyyaml
```

## Usage

**Print to stdout:**

```bash
python3 scripts/compile-to-github-actions.py workflows/ci-validate-build.json
```

**Write to a file:**

```bash
python3 scripts/compile-to-github-actions.py workflows/pr-and-merge.json \
  --output .github/workflows/pr-and-merge.yml
```

**Compile all 10 workflows at once:**

```bash
for f in workflows/*.json; do
  slug=$(basename "$f" .json)
  python3 scripts/compile-to-github-actions.py "$f" \
    --output ".github/workflows/${slug}.yml"
done
```

## How it works

The compiler reads the composition JSON and maps each `atom_id` to a GitHub Actions step using the lookup table in `ATOM_TO_ACTION`. It then assembles the `on:` trigger block, the `jobs.run.steps` list, and emits valid GitHub Actions YAML.

```
composition.json
  └─ trigger.atom_id  ──► on: { push / workflow_dispatch / schedule / pull_request }
  └─ steps[].atom_id  ──► jobs.run.steps[{ uses | run, env }]
```

**Trigger mapping:**

| Atom ID | GitHub Actions `on:` key |
|---|---|
| `workflow-atoms/trigger-type/push` | `push` |
| `workflow-atoms/trigger-type/manual` | `workflow_dispatch` |
| `workflow-atoms/trigger-type/schedule` | `schedule` |
| `workflow-atoms/trigger-type/pr` | `pull_request` |

**Automatic checkout injection:** when the trigger is `push` or `pull_request` and the first step is not already a `git-checkout` atom, the compiler prepends `actions/checkout@v4` automatically.

**Unknown atoms:** any atom ID not in the lookup table is compiled to a stub `echo` step so the output YAML is always valid and runnable. Replace stubs with real implementations incrementally.

## Example output

Input (`workflows/ci-validate-build.json`):

```json
{
  "name": "CI Validate and Build",
  "trigger": {"atom_id": "workflow-atoms/trigger-type/push"},
  "steps": [
    {"id": "checkout", "atom_id": "workflow-atoms/step-type/git-checkout"},
    {"id": "install",  "atom_id": "workflow-atoms/step-type/install-dependencies"},
    {"id": "validate", "atom_id": "workflow-atoms/step-type/run-lint-validate"},
    {"id": "build",    "atom_id": "workflow-atoms/step-type/build-artifact"},
    {"id": "upload",   "atom_id": "workflow-atoms/step-type/upload-artifact"}
  ]
}
```

Output:

```yaml
name: CI Validate and Build
on:
  push:
    branches:
    - main
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
    - name: checkout
      uses: actions/checkout@v4
      with:
        fetch-depth: 0
    - name: install
      run: npm ci
    - name: validate
      run: npm run lint
    - name: build
      run: npm run build
    - name: upload
      uses: actions/upload-artifact@v4
      with:
        name: dist
        path: dist/
```

## Extending the compiler

To add support for a new atom, add an entry to the `ATOM_TO_ACTION` dict in `scripts/compile-to-github-actions.py`:

```python
"workflow-atoms/step-type/my-new-atom": {
    # Option A — a marketplace action:
    "uses": "owner/action@v1",
    "with": {"key": "value"},
    # Option B — a shell command:
    "run": "echo 'do the thing'",
    # Optional environment variables:
    "env": {"MY_VAR": "${{ secrets.MY_SECRET }}"},
},
```

To add a new trigger type, add an entry to `TRIGGER_MAP`:

```python
TRIGGER_MAP["workflow-atoms/trigger-type/release"] = "release"
```
