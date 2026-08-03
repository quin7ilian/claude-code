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

## Fixes

A fix inherits the tier of the code it touches, never a default — a three-line change to
concurrency or crash-recovery code is `complex`, with everything the tier implies: routing
per the table above, a fresh subagent window, an invariant-carrying brief, and the tier's
review. Review findings land in exactly the code that earned the strictest scaffolding;
giving their fixes less scrutiny than the original work is how a fix loop manufactures its
own next round.

Every fix ships with a pinning test written first and verified in both directions: it
fails on the unfixed code and passes after. An invariant that findings hit in two separate
rounds gets a permanent deterministic guard — a test or a lint — so holding it stops
depending on review at all.

### Authorship escalation (pair mode)

Claude authors fixes by default. Authorship of a finding's fix hands over to Codex —
consult-then-apply, per the mechanics in `review-loop.md` — on these triggers only:

1. The fix failed one re-review round and the finding sits on a ledger invariant — a
   property the item's invariant ledger names as load-bearing, one that must hold across
   the whole tree rather than at the finding's site. The ledger, not any fixed list of
   domains, defines the class; a lock discipline, a crash-recovery contract, a security
   boundary, or an ordering guarantee are illustrations only. One consult costs less
   than risking another failed round, and these are the fixes where the reviewer's model
   of the defect is sharpest.
2. The fix failed two re-review rounds anywhere else.
3. The review loop's circuit breaker fired (`review-loop.md`): every remaining finding
   in that loop is pair-authored.
4. The user directs it.

Pair mode is per finding and exits on success — once the pair-authored fix passes
re-review, the next finding starts back at the default. The author and the reviewer are
always different models: when Codex authors, Claude reviews adversarially, and vice
versa.

### The `pair-authored` flag

A design spec may flag a `complex` item pair-authored when the item is dominated by one
deep correctness dimension — a lock protocol, a crash-convergent state machine — where
systematic exhaustiveness matters more than repository breadth. The orchestrator proposes
the flag at decomposition and the user approves it; Codex then authors the first cut
against the orchestrator's plan, a Claude coder applies, tests, and integrates it, and
Claude runs the adversarial per-item review in place of the codex review. The flag swaps
the author and reviewer seats; it never removes the review. It is a rare, explicit
opt-in — never the `complex` default: most complex items clear review in a round or two,
and pair-authoring them all would roughly double wall-clock for nothing.

## Rules

- A tier classifies the **work item**, not its file count — a one-line change to a
  consensus-critical invariant is `complex`; a 40-file mechanical rename is `trivial`.
- Tie-break upward: when in doubt between two tiers, pick the higher one.
- The tier selects the implementing model, the review placement, and — with the fix and
  `pair-authored` rules above — the authorship route; nothing else.
