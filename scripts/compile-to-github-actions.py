#!/usr/bin/env python3
"""Compile a workflow-atoms workflow composition to a GitHub Actions YAML workflow.

Usage:
    python3 scripts/compile-to-github-actions.py <workflow.json>
    python3 scripts/compile-to-github-actions.py <workflow.json> --output <path>

Reads a workflow composition JSON and emits a .github/workflows/<slug>.yml.
Unknown atom IDs are compiled to a shell echo stub so the output is always
runnable — callers can swap stubs for real actions incrementally.
"""
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: pyyaml not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Atom-to-GitHub-Actions mapping
#
# Each entry may have:
#   "uses"  — a marketplace action ref (takes priority over "run")
#   "run"   — a shell command
#   "with"  — static "with:" inputs appended to a "uses" step
#   "env"   — static "env:" block appended to the step
#
# Shell commands may use ${{ inputs.<name> }} for step-level interpolation.
# ---------------------------------------------------------------------------
ATOM_TO_ACTION: dict[str, dict] = {
    # --- step-type atoms ---
    "workflow-atoms/step-type/git-checkout": {
        "uses": "actions/checkout@v4",
        "with": {"fetch-depth": 0},
    },
    "workflow-atoms/step-type/install-dependencies": {
        "run": "npm ci",
    },
    "workflow-atoms/step-type/run-lint-validate": {
        "run": "npm run lint",
    },
    "workflow-atoms/step-type/build-artifact": {
        "run": "npm run build",
    },
    "workflow-atoms/step-type/upload-artifact": {
        "uses": "actions/upload-artifact@v4",
        "with": {"name": "dist", "path": "dist/"},
    },
    "workflow-atoms/step-type/git-push": {
        "run": "git push origin $BRANCH",
        "env": {"BRANCH": "${{ github.head_ref || github.ref_name }}"},
    },
    "workflow-atoms/step-type/github-pr-create": {
        "run": (
            'gh pr create --head "$BRANCH" --base main'
            ' --title "feat: $BRANCH" --fill'
        ),
        "env": {"BRANCH": "${{ github.head_ref || github.ref_name }}"},
    },
    "workflow-atoms/step-type/github-pr-merge": {
        "run": 'gh pr merge "$PR_NUMBER" --merge --delete-branch',
        "env": {"PR_NUMBER": "${{ github.event.pull_request.number }}"},
    },
    "workflow-atoms/step-type/cloudflare-pages-deploy": {
        "run": (
            "npx wrangler pages deploy dist"
            ' --project-name "$CF_PROJECT" --branch "$CF_BRANCH"'
        ),
        "env": {
            "CLOUDFLARE_API_TOKEN": "${{ secrets.CLOUDFLARE_API_TOKEN }}",
            "CLOUDFLARE_ACCOUNT_ID": "${{ secrets.CLOUDFLARE_ACCOUNT_ID }}",
            "CF_PROJECT": "${{ inputs.project_name || github.event.repository.name }}",
            "CF_BRANCH": "${{ github.ref_name }}",
        },
    },
    "workflow-atoms/step-type/git-create-tag": {
        "run": (
            'git tag -a "$TAG" -m "Release $TAG"\n'
            "git push origin \"$TAG\""
        ),
        "env": {"TAG": "${{ inputs.tag_name || github.ref_name }}"},
    },
    "workflow-atoms/step-type/trigger-workflow": {
        "run": 'gh workflow run "$WORKFLOW_ID" --ref "${{ github.ref_name }}"',
        "env": {"WORKFLOW_ID": "${{ inputs.workflow_id }}"},
    },
    "workflow-atoms/step-type/run-secret-scan": {
        "uses": "trufflesecurity/trufflehog@main",
        "with": {
            "path": "./",
            "base": "${{ github.event.repository.default_branch }}",
            "head": "HEAD",
            "extra_args": "--debug --only-verified",
        },
    },
    "workflow-atoms/step-type/run-dependency-audit": {
        "run": "npm audit --audit-level=high",
    },
    "workflow-atoms/step-type/filter-major-bumps": {
        "run": (
            "python3 -c \"\n"
            "import subprocess, json, sys\n"
            "pr = '${{ github.event.pull_request.number }}'\n"
            "result = subprocess.run(['gh','pr','view',pr,'--json','title'],\n"
            "    capture_output=True, text=True)\n"
            "title = json.loads(result.stdout).get('title','')\n"
            "if 'major' in title.lower():\n"
            "    print('major version bump — skipping auto-merge')\n"
            "    sys.exit(1)\n"
            "\""
        ),
    },
    "workflow-atoms/step-type/run-tests": {
        "run": "npm test",
    },
    "workflow-atoms/step-type/page-on-call": {
        "run": (
            'curl -s -X POST https://events.pagerduty.com/v2/enqueue \\\n'
            '  -H "Content-Type: application/json" \\\n'
            '  -d \'{"routing_key":"\'$PD_KEY\'","event_action":"trigger",'
            '"payload":{"summary":"\'$SUMMARY\'","severity":"critical","source":"github-actions"}}\''
        ),
        "env": {
            "PD_KEY": "${{ secrets.PAGERDUTY_ROUTING_KEY }}",
            "SUMMARY": "${{ inputs.summary || 'Incident triggered by GitHub Actions' }}",
        },
    },
    "workflow-atoms/step-type/diagnose-incident": {
        "run": (
            "echo 'Collecting logs for incident $INCIDENT_ID'\n"
            "gh run list --limit 10 --json status,conclusion,url > diagnosis.json\n"
            "cat diagnosis.json"
        ),
        "env": {"INCIDENT_ID": "${{ inputs.incident_id || github.run_id }}"},
    },
    "workflow-atoms/step-type/apply-mitigation": {
        "run": (
            "echo 'Applying mitigation: $MITIGATION_TYPE on $TARGET'\n"
            "# Replace with the appropriate mitigation command for your environment"
        ),
        "env": {
            "MITIGATION_TYPE": "${{ inputs.mitigation_type }}",
            "TARGET": "${{ inputs.target }}",
        },
    },
    "workflow-atoms/step-type/write-post-mortem": {
        "run": (
            "python3 -c \"\n"
            "import datetime, pathlib\n"
            "now = datetime.datetime.utcnow().isoformat()\n"
            "doc = f'# Post-Mortem\\nIncident ID: $INCIDENT_ID\\nDate: {now}\\n'\n"
            "pathlib.Path('post-mortem.md').write_text(doc)\n"
            "print('wrote post-mortem.md')\n"
            "\""
        ),
        "env": {"INCIDENT_ID": "${{ inputs.incident_id || github.run_id }}"},
    },
    "workflow-atoms/step-type/clone-repository": {
        "run": (
            "for repo in $REPOS; do\n"
            "  git clone \"https://github.com/$repo\" \"$(basename $repo)\"\n"
            "done"
        ),
        "env": {"REPOS": "${{ inputs.repos }}"},
    },
    "workflow-atoms/step-type/setup-secrets": {
        "run": (
            "echo 'Provisioning secrets from $SECRET_SOURCE'\n"
            "# Replace with your secrets management tool (1Password, Vault, etc.)"
        ),
        "env": {"SECRET_SOURCE": "${{ inputs.secret_source }}"},
    },
    "workflow-atoms/step-type/audit-atoms": {
        "run": (
            "find atoms/ -name '*.json' | sort > atom-list.txt\n"
            "echo 'Found' $(wc -l < atom-list.txt) 'atoms'\n"
            "cat atom-list.txt"
        ),
    },
    "workflow-atoms/step-type/validate-schema": {
        "run": "python3 scripts/build-exports.py",
    },
    "workflow-atoms/step-type/fix-nonconforming": {
        "run": (
            "echo 'Fix non-conforming atoms from $VIOLATIONS_REPORT'\n"
            "# Replace with your automated fixer or manual review step"
        ),
        "env": {"VIOLATIONS_REPORT": "${{ inputs.violations_report }}"},
    },
    "workflow-atoms/step-type/regenerate-exports": {
        "run": "python3 scripts/build-exports.py",
    },
    "workflow-atoms/step-type/sign-artifact": {
        "run": (
            "cosign sign-blob --yes \"$ARTIFACT_PATH\" "
            "--output-signature \"$ARTIFACT_PATH.sig\""
        ),
        "env": {"ARTIFACT_PATH": "${{ inputs.artifact_path }}"},
    },
    "workflow-atoms/step-type/deploy-catalog-site": {
        "run": (
            "npx wrangler pages deploy \"$SITE_DIR\""
            " --project-name \"$PROJECT_NAME\""
        ),
        "env": {
            "CLOUDFLARE_API_TOKEN": "${{ secrets.CLOUDFLARE_API_TOKEN }}",
            "CLOUDFLARE_ACCOUNT_ID": "${{ secrets.CLOUDFLARE_ACCOUNT_ID }}",
            "SITE_DIR": "${{ inputs.site_dir || 'web/dist' }}",
            "PROJECT_NAME": "${{ inputs.project_name || github.event.repository.name }}",
        },
    },
    # --- gate-type atoms (compiled as a verification run step) ---
    "workflow-atoms/gate-type/ci-green": {
        "run": (
            "gh pr checks \"$PR_NUMBER\" --watch --interval 30"
        ),
        "env": {"PR_NUMBER": "${{ github.event.pull_request.number }}"},
    },
    "workflow-atoms/gate-type/clean-main-gate": {
        "run": (
            "git fetch origin main\n"
            "git diff --exit-code HEAD origin/main || "
            "{ echo 'main is not clean'; exit 1; }"
        ),
    },
    "workflow-atoms/gate-type/no-secrets-found-gate": {
        "run": (
            "if [ \"$FINDINGS\" -gt 0 ]; then\n"
            "  echo \"Secret scan found $FINDINGS issue(s) — blocking pipeline\"\n"
            "  exit 1\n"
            "fi"
        ),
        "env": {"FINDINGS": "${{ steps.secret-scan.outputs.findings_count || 0 }}"},
    },
    "workflow-atoms/gate-type/no-high-severity-gate": {
        "run": (
            "if [ \"$HIGH\" -gt 0 ]; then\n"
            "  echo \"$HIGH high-severity vulnerability(ies) found — blocking pipeline\"\n"
            "  exit 1\n"
            "fi"
        ),
        "env": {"HIGH": "${{ steps.dep-audit.outputs.high_severity_count || 0 }}"},
    },
    "workflow-atoms/gate-type/not-major-bump-gate": {
        "run": (
            "if [ \"$IS_MAJOR\" = 'true' ]; then\n"
            "  echo 'Major version bump — requires manual review'\n"
            "  exit 1\n"
            "fi"
        ),
        "env": {"IS_MAJOR": "${{ steps.filter-major.outputs.is_major || 'false' }}"},
    },
    "workflow-atoms/gate-type/tests-pass-gate": {
        "run": (
            "if [ \"$FAILED\" -gt 0 ]; then\n"
            "  echo \"$FAILED test(s) failed — blocking pipeline\"\n"
            "  exit 1\n"
            "fi"
        ),
        "env": {"FAILED": "${{ steps.test.outputs.failed || 0 }}"},
    },
    "workflow-atoms/gate-type/schema-valid-gate": {
        "run": (
            "if [ \"$INVALID\" -gt 0 ]; then\n"
            "  echo \"$INVALID atom(s) failed schema validation — blocking pipeline\"\n"
            "  exit 1\n"
            "fi"
        ),
        "env": {"INVALID": "${{ steps.validate.outputs.invalid_count || 0 }}"},
    },
}

# Trigger-type atom IDs → GitHub Actions "on:" keys
TRIGGER_MAP: dict[str, str] = {
    "workflow-atoms/trigger-type/push": "push",
    "workflow-atoms/trigger-type/manual": "workflow_dispatch",
    "workflow-atoms/trigger-type/schedule": "schedule",
    "workflow-atoms/trigger-type/pr": "pull_request",
}


def _slug(atom_id: str) -> str:
    """Return the final path segment of an atom_id for use as a step id."""
    return atom_id.rstrip("/").split("/")[-1]


def _build_gha_step(composition_step: dict) -> dict:
    """Convert one composition step dict to a GitHub Actions step dict."""
    atom_id: str = composition_step.get("atom_id", "")
    step_name: str = composition_step.get("id", _slug(atom_id))

    mapping = ATOM_TO_ACTION.get(atom_id)
    if mapping is None:
        # Emit a labelled stub so the YAML is still valid and runnable.
        gha_step: dict = {
            "name": step_name,
            "run": f"echo 'stub: {atom_id}'",
        }
        return gha_step

    gha_step = {"name": step_name}

    if "uses" in mapping:
        gha_step["uses"] = mapping["uses"]
        if "with" in mapping:
            gha_step["with"] = dict(mapping["with"])
        # Note: composition-level "inputs" are atom-level parameters for runtime
        # orchestrators (n8n, Temporal, etc.). They are NOT GitHub Actions "with"
        # inputs and are not merged here — the ATOM_TO_ACTION mapping handles
        # environment-variable injection via "env" instead.
    elif "run" in mapping:
        gha_step["run"] = mapping["run"]

    if "env" in mapping:
        gha_step["env"] = dict(mapping["env"])

    return gha_step


def _build_on(trigger: dict, composition: dict) -> dict:
    """Build the GitHub Actions 'on:' block from the composition trigger."""
    atom_id = trigger.get("atom_id", "workflow-atoms/trigger-type/manual")
    config = trigger.get("config", {})
    gha_key = TRIGGER_MAP.get(atom_id, "workflow_dispatch")

    if gha_key == "push":
        on_block: dict = {"push": {"branches": config.get("branches", ["main"])}}
    elif gha_key == "pull_request":
        on_block = {"pull_request": {"branches": config.get("branches", ["main"])}}
    elif gha_key == "schedule":
        cron = config.get("cron", "0 8 * * 1")
        on_block = {"schedule": [{"cron": cron}]}
    else:
        on_block = {"workflow_dispatch": {}}

    return on_block


def compile_workflow(composition_path: Path) -> dict:
    """Read a composition JSON and return a GitHub Actions workflow dict."""
    composition = json.loads(composition_path.read_text(encoding="utf-8"))

    trigger = composition.get("trigger", {})
    on_block = _build_on(trigger, composition)

    # Always prepend checkout when the trigger is push/pr and checkout is not
    # already the first step.
    steps: list[dict] = []
    comp_steps: list[dict] = composition.get("steps", [])
    first_atom_ids = [s.get("atom_id", "") for s in comp_steps[:1]]
    needs_checkout = (
        "push" in on_block or "pull_request" in on_block
    ) and "workflow-atoms/step-type/git-checkout" not in first_atom_ids

    if needs_checkout:
        steps.append({"uses": "actions/checkout@v4", "with": {"fetch-depth": 0}})

    for comp_step in comp_steps:
        steps.append(_build_gha_step(comp_step))

    return {
        "name": composition.get("name", composition_path.stem),
        "on": on_block,
        "jobs": {
            "run": {
                "runs-on": "ubuntu-latest",
                "steps": steps,
            }
        },
    }


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(
            "Usage: python3 compile-to-github-actions.py <workflow.json>"
            " [--output <path>]",
            file=sys.stderr,
        )
        return 1

    comp_path = Path(args[0])
    if not comp_path.exists():
        print(f"error: file not found: {comp_path}", file=sys.stderr)
        return 1

    output_path: Path | None = None
    if len(args) >= 3 and args[1] == "--output":
        output_path = Path(args[2])

    gha = compile_workflow(comp_path)
    yaml_text = yaml.dump(gha, default_flow_style=False, sort_keys=False, allow_unicode=True)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml_text, encoding="utf-8")
        print(f"wrote {output_path}")
    else:
        print(yaml_text, end="")

    return 0


if __name__ == "__main__":
    sys.exit(main())
