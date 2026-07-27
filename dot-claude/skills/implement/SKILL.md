---
name: implement
description: Orchestrate implementation of a design spec or a decomposed ad-hoc task by delegating tiered work items to coder subagents, with complexity-tiered codex review (per-item for complex work, one batch review of the integrated change-set for everything). Invoke when the user explicitly asks to implement a spec or to run the implementation workflow; not for trivial single-file edits, and never self-invoked during routine coding.
---

# Implement through tiered coder subagents

You are the orchestrator. Coder subagents do the implementation; Codex reviews every
deliverable before you see it. Your context stays reserved for sequencing, integration,
and judgment — not for the grunt work.

## Load the plan

**Spec-driven** (a Design spec is named or discoverable): open the spec in the Obsidian
vault and extract the implementation sequence with its per-item complexity tiers. Do not
re-derive decisions the spec has already settled. If any sequence item lacks a tier, tier
it yourself and say so.

**Ad-hoc** (no spec): decompose the task into self-contained work items and assign each a
tier using `references/complexity-tiers.md`. State the decomposition and tiers to the user
before starting.

## Route each item

Dispatch items **serially, in dependency order** via the Task tool, with the subagent
type, `model` parameter, and (via the subagent definition) effort that
`references/complexity-tiers.md` maps the item's tier to — `coder` for `trivial` and
`standard` items, `coder-complex` for `complex` items. Tiers are logical (`trivial`,
`standard`, `complex`); the routing table in that file is the only place tiers become
models and efforts.

Serial is the default because sustained completion beats wall-clock speed: burn spreads
across usage windows instead of spiking into one, a session-limit hit strands at most one
agent, warm prompt-cache prefixes get reused, and each brief can carry forward what
earlier items learned. Dispatch in parallel only when the user explicitly asks for speed
on this run.

Each dispatch prompt is a self-contained work-item brief — the subagent cannot see this
conversation. Include: the goal, acceptance criteria, constraints, the exact files
involved, decisions already made, anything from the spec the item depends on, and the
item's tier with its review requirement (`complex` → per-item review; `trivial`/
`standard` → review deferred to the batch).

**Every brief names the repository's instruction files by absolute path** — `AGENTS.md`,
`CLAUDE.md`, and any covering the directories in scope — and requires reading them before
the first edit and confirming compliance in the summary. Locate them yourself before the
first dispatch (they are not reliably in a subagent's context) and re-state any rule the
item is likely to brush against. A returned summary that is silent about them is
incomplete: ask before accepting the item.

For `standard` items, add a short approach note when you hold non-obvious context the
coder cannot cheaply rediscover — entry points, the existing pattern to follow, an
invariant or pitfall worth naming. Skip it for plain pattern-following items; a wrong but
authoritative-sounding note misleads more than no note.

For `complex` items, additionally write the implementation plan into the brief — the
approach, load-bearing invariants, the tricky spots, and explicit stop conditions ("if
assumption X does not hold, stop and return for guidance"). When a complex item returns:
run the conceptual review before accepting it — check the coder's summary and targeted
reads of the load-bearing code against the plan's invariants and intent, and verify any
reported deviation was the right call. Send a focused fix brief if it drifted.

Do an item inline yourself only when it is inseparable from live conversation or design
context — and then run the identical review gate yourself (`codex-review` with a brief,
verify findings, loop to PASS) before marking the item done.

## Review placement

Review is placed per the policy in `references/complexity-tiers.md`: deterministic checks
always, per-item codex review for `complex` items inside the coder, and one **batch codex
review** of the integrated change-set here (below) covering everything — including the
cross-item interactions no per-item review can see. Within this workflow these reviews are
authorized. Do not additionally chain `codex-plan-review`, `codex-research`, or
`codex-brainstorm` from inside the workflow.

A coder reporting an unavailable reviewer has reported a blocker, not a pass — the same
applies to the batch review. Surface it to the user instead of proceeding as if reviewed.

## Batch review of the integrated change-set

After all items have landed and the full test suite passes:

1. Write a batch brief: the overall goal, the list of work items with their intent and
   acceptance criteria, spec references, the exact integrated diff/range, the absolute
   paths of the repository's instruction files (`AGENTS.md`/`CLAUDE.md`) with a
   requirement to verify the change against them, and the interactions between items that
   deserve scrutiny. Note which items already passed a per-item review so the reviewer
   spends its depth on the rest and on integration.
2. Run `codex-review --brief <batch-brief.md> --repo <root> --out <review.md>`. Review
   quality degrades on oversized diffs: if the integrated change-set is large (roughly
   more than several hundred changed lines), split the review into coherent clusters of
   related items instead of one pass.
3. Verify every finding yourself, then dispatch accepted findings back to coders as
   focused fix briefs (fixes are `standard`-tier unless riskier). Re-review only the fix
   delta, not the whole set again.
4. Loop until PASS or return with unresolved findings explicitly flagged to the user.

## Interruptions: resume, don't redo

Long runs cross usage-limit windows; treat interruption as normal, not exceptional.

- Write progress through as you go: update the spec's implementation status (or, ad-hoc,
  a brief checkpoint note to the user) after every item lands — a resume must need only
  the spec and the working tree, never conversation archaeology.
- On a session-limit error: stop dispatching immediately. Do not retry into a closed
  window and do not leave coders queued. State the checkpoint (items done, item in
  flight, next steps) and wait.
- Before re-dispatching any interrupted item, inspect the working tree first (`git status`,
  the item's files). A stranded coder's work is usually still on disk — brief the resume
  against the existing diff ("verify and complete") instead of re-running the item from
  scratch.

## What you keep

- **Sequencing and dependencies** between items; re-briefing when an earlier item's
  outcome changes a later item's inputs.
- **Integration**: cross-item consistency, interfaces between deliverables, a full
  test-suite run, and the batch review above. If integration reveals a defect inside one
  item, send it back to a coder with a focused brief rather than patching it inline.
- **Spec status** (spec-driven case): update the Design note's implementation status as
  items land.
- **The final report**: per-item summaries with their review status, the batch review
  verdict, rejected findings worth the user's attention, test results, and residual
  risks. Report coder summaries faithfully — do not soften flagged items.
