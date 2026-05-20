# workflow-atoms — Goals

> Workflow primitives unified across n8n, Zapier, GitHub Actions, Temporal, Airflow — step types, triggers, states, and gates composed into typed workflows with no per-tool DSL.

*This document is derived from `aish/ARCHITECTURE.md` (now `xdao/xdao/ARCHITECTURE.md` §The *-Atoms Catalogs). Sections marked **Generated** are pattern-based and are intended as a starting point for revision, not as decided plan.*

---

## What this catalog makes civilization-grade

Workflow tooling is fragmented. n8n, Zapier, GitHub Actions, Temporal, Airflow — each invents its own DSL, its own trigger model, its own state machine semantics. Porting a workflow between tools is a rewrite.

By cataloging the primitives, `workflow-atoms` turns this domain from opaque-and-ephemeral to typed, versioned, composable, machine-readable, and open — the civilization-grade properties the ecosystem requires.

## What it catalogs

### Atom types

- **`step-type`** — Action / decision / parallel / loop / wait / approval.
- **`trigger-type`** — Event / schedule / webhook / manual / chained.
- **`state-type`** — Workflow state machine states (pending, running, succeeded, failed, retrying, suspended).
- **`gate-type`** — Approval gate, policy gate, evidence gate, time gate.

### Compositions: `workflows`

A workflow composition assembles steps + triggers + states + gates into a complete, version-controlled workflow definition. Portable across any compliant runtime — Temporal, GitHub Actions, an Olympus agentic loop.

### Rule types

- **`state-transition-validity`** — Permitted transitions (pending → running but not pending → succeeded).
- **`gate-requirement`** — What evidence/approval a gate requires before passing.
- **`retry-policy`** — Backoff strategies, max attempts, dead-letter behavior.

## Runtime consumers

- **olympus** — Agentic loop is a workflow. Pantheon Module sequencing is a workflow. Drachma spend approval is a gated workflow.

## Status & priority

**Current status:** `proposed`

**Priority tier:** Tier 3 — Build when supporting runtimes mature

**Trigger / activation condition:** Olympus agentic loop formalization. A workflow runtime would benefit from catalog support immediately.

## Roadmap *(Generated — milestone shapes mirror aish's roadmap pattern; revise as actual work begins)*

### v0.1 — Bootstrap & spec acceptance

**Goal:** Schema accepted. Olympus agentic loop expressible as a workflow-atoms composition.

**Success criterion:** Olympus loop runs unchanged when its workflow definition is loaded from workflow-atoms.

**Kill criterion:** Existing workflow tools (Temporal) demonstrate the catalog is overlapping rather than complementary — pivot to spec-only.

**Work:**

- [ ] XAIP: workflow composition schema
- [ ] Define 4 atom type schemas
- [ ] Express Olympus agentic loop as workflow-atoms
- [ ] Compile workflow-atoms → Temporal definition (proof of portability)

### v0.2 — Adoption & expansion

**Goal:** GitHub Actions adapter. Catalog 10 common patterns (deploy, incident response, onboarding).

**Work:**

- [ ] Compile workflow-atoms → GitHub Actions YAML
- [ ] Catalog 10 common workflows
- [ ] Approval-gate integration with policy-atoms

### v1.0 — Operational

**Goal:** Cross-tool workflow portability. Write once in workflow-atoms; deploy to any compatible runtime.

## Concrete atom example *(Generated — illustrative, not seed content)*

```yaml
workflows/deploy-with-approval/definition.yml
---
id: deploy-with-approval
type: composition
version: 1.0.0
trigger: { ref: atoms/trigger-type/event, on: git-push-to-main }
steps:
  - { id: build, ref: atoms/step-type/action, action: ci-build }
  - { id: review, ref: atoms/gate-type/approval, approvers: 2 }
  - { id: deploy, ref: atoms/step-type/action, action: kubectl-apply }
states: { ref: atoms/state-type/standard-deploy }
retry: { ref: atoms/retry-policy/exponential-3 }
```

## Adoption strategy *(Generated)*

Olympus is the anchor. Wider adoption comes from compilers — workflow-atoms → Temporal, → GitHub Actions, → Argo, etc.

## Civilization-grade property checklist

Every catalog must satisfy these before v1.0. Failing any blocks a release.

| Property | Mechanism in this catalog |
|---|---|
| Typed | JSON Schema in `schemas/` validates every atom, composition, rule |
| Versioned | Every atom has a semver `version` field; compositions reference atoms by version-pinned ID |
| Machine-readable | `exports/catalog.json` published on every release |
| Composable | Compositions reference atoms by ID; CI verifies references resolve and no circular dependencies |
| Open | Apache-2.0 licensed; LICENSE file present |
| Durable | No external dependencies for primary content (no remote image URLs, no vendor APIs in the hot path) |

## Related

- **Spec:** [atoms-spec](https://github.com/convergent-systems-co/atoms-spec) — the canonical structure every catalog conforms to
- **Tools:** [atoms-tools](https://github.com/convergent-systems-co/atoms-tools) — CLI for validate / export / bootstrap / resolve
- **Federation:** [xdao](https://github.com/convergent-systems-co/xdao) — ecosystem directory and discovery
- **Umbrella:** [atoms](https://github.com/convergent-systems-co/atoms) — every catalog as a git submodule
- **Manifest:** [`ATOMS.yml`](./ATOMS.yml) — this catalog's machine-readable manifest
- **Standard:** [`README.md`](./README.md) — catalog overview and contribution flow
