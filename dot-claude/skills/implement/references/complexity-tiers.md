# Complexity tiers

Every implementation work item carries a logical complexity tier. Design specs record the
tier — never a model name — and the implement workflow translates it into a model using
the routing table below. To change which models execute which tiers, edit this file only;
no design spec ever needs to change.

## `trivial`

Renames, boilerplate, config edits, straightforward test additions, documentation updates.
Low ambiguity; the blast radius is contained to named files; correctness is checkable by
existing tests or type checks.

## `standard` — the default

Ordinary features, bug fixes, and multi-file work that follows established patterns in the
repository. When an item does not clearly belong to another tier, it belongs here.

## `complex`

Novel algorithms, subtle concurrency or state behavior, security or privacy boundaries,
architectural changes, high blast radius, or work whose failure modes are non-obvious.

## Model routing

| Tier | Orchestrator guidance in the brief | Subagent | Executing model | Effort |
|---|---|---|---|---|
| `trivial` | none | `coder` | `sonnet` | `high` |
| `standard` | short approach note, when there is non-obvious context to transfer | `coder` | `opus` | `high` |
| `complex` | full implementation plan with binding stop conditions | `coder-complex` | `opus` | `xhigh` |

The implement workflow selects the subagent type per this table and passes the mapped
model as the per-invocation `model` parameter. Effort cannot be passed per invocation —
it is pinned in each subagent definition's frontmatter, which is why the `complex` tier
has its own subagent. The gradient matches each tier's scaffolding: `standard` items have
the least support (no plan, no per-item review — the coder's own judgment carries them),
so they run at `high`; `complex` items run at `xhigh`, where Opus performs at its best on
genuinely hard work. `trivial` items share the `coder` definition and ride at `high` — a
deliberate, negligible overshoot on small Sonnet items rather than a third definition.
`max` is deliberately unused: it only sometimes beats `xhigh` and costs
disproportionately.

The orchestrator's session model is never used for grunt execution — its capability goes
into planning, steering, and conceptual review, not typing. For `complex` items the
orchestrator writes a short implementation plan into the brief: approach, load-bearing
invariants, the tricky spots, and explicit stop conditions ("if assumption X does not
hold, stop and return for guidance instead of working around it").

## Review policy

| Tier | Deterministic checks | Per-item codex review | Orchestrator conceptual review | Batch codex review |
|---|---|---|---|---|
| `trivial` | always | no | no | yes |
| `standard` | always | no | no | yes |
| `complex` | always | yes — loop to PASS | yes | yes |

Deterministic checks (tests/types/lint) are the floor and are never skipped. `trivial`
and `standard` items are reviewed once, together, in the orchestrator's batch codex
review of the integrated change-set — which also covers cross-item interactions no
per-item review can see. `complex` items additionally get, before integration: a per-item
codex review (mechanical correctness against the brief), and an orchestrator conceptual
review — the coder's summary plus targeted reads of the load-bearing code, checked
against the plan's invariants and intent. Codex cannot judge design intent because it
never saw the design context; the orchestrator can, cheaply, because it wrote the plan.
A coder that discovers mid-implementation that its item is riskier than its tier may
escalate and run the per-item review anyway.

## Rules

- A tier classifies the **work item**, not its file count — a one-line change to a
  consensus-critical invariant is `complex`; a 40-file mechanical rename is `trivial`.
- Tie-break upward: when in doubt between two tiers, pick the higher one.
- The tier selects the implementing model and the review placement per the tables above;
  nothing else.
