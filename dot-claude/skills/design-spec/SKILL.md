---
name: design-spec
description: Iteratively develop architecture, feature designs, and implementation-ready specifications in Obsidian under Design/, using current repository state and selected Research notes as evidence. Use only when the user explicitly invokes /design-spec or explicitly asks to begin a design or implementation-specification workflow. Do not implement the design, conduct unrelated broad research, or invoke another workflow automatically.
---

# Develop a Design Specification

Turn an explicit goal into a durable, decision-oriented specification that a principal
engineer can review in one pass. The Obsidian Design note is the canonical working context;
implementation stays outside this workflow.

## The note is a reviewed document, not a scratchpad

Every Design note follows `references/vault-note-standard.md` — read it before the first
write. The rules that shape everything below: the body is current state only and never
carries history; every change is a decision-log row the body references by id, with fuller
reasoning in that row's reasoning comment; a register row is the entry's current value in one
sentence, never a changelog; sections are structured to scan, never walls of prose; the
status block at the top is the note's whole state; the heading set is closed; tags follow the
contract. Enforcement is the template and the checkpoint, never a script: each section's
contract travels in the note as a comment, and every checkpoint runs the standard's
self-check against it.

Drift builds one decision at a time. The ruling that "just adds a clause" to a `W-n` cell,
the answered question that keeps its argument, the `phase` that gains a commit — each is
small, and together they make the note unreadable. Every write is held to the row and
formatting rules on its own, not deferred to a later cleanup.

## Maintain write-through context

Instantiate the note from `references/spec-template.md` before extended design reasoning:
fill the frontmatter, status block, §1 Summary and §2 Problem, goals, non-goals, replace
every remaining placeholder with real content or nothing, save. Never design the whole
system in chat and write the specification when the discussion ends.

- Work through consequential design points iteratively: raise one coherent decision or
  tightly coupled group, present evidence and tradeoffs, obtain the user's direction.
- The moment the user accepts, rejects, amends, or defers a point, perform **Record a
  decision** from the standard's operations table: one `D-n` row carrying the ask you put
  and the ruling it earned, and its reasoning comment when two sentences cannot carry the
  why; every affected body section and register row rewritten to its new current state
  with the old text removed, not annotated; the status block refreshed; any `Q-n` it
  answers reduced to its question and marked answered. One logical update.
- A proposal the user has not ruled on is a `Q-n` row and a `[Q-n]` marker at the site that
  depends on it — never text blended into the agreed design.
- The ask is the contract for the write. What you record may not reach past what you put to
  the user, at the altitude you put it: a consequence the ask omitted is a decision not
  ratified, and it returns as its own ask or waits as a `Q-n`. Before saving, compare the
  write against the ask you actually sent — a body rewrite reaching a section the ask never
  named is the signal that it grew.
- A ruling that would contradict, narrow, or override a prior `D-m` names that `D-m` in the
  ask itself — what it required, what this does instead, what the user would observe change
  — and takes its own ruling. An override you notice only while writing sends the decision
  back before the row lands; you never fill `Supersedes` from your own reading after the
  user has answered.
- Re-read §1, the status block, and the decision log before raising the next decision, and
  after compaction, resumption, or a long diversion. The status block names one prior
  ruling; the log names them all, and a ruling you cannot see is one you can contradict
  without noticing. The note, not recalled transcript, is authoritative.
- Treat impending compaction, a subagent batch, and handoff as **Checkpoint** operations:
  re-read, reconcile, run the standard's self-check.

## Establish the design boundary

1. Clarify the problem, stakeholders, goals, non-goals, constraints, approval boundaries,
   acceptance criteria, and required level of implementation detail. Ask only about choices
   that would materially change the design.
2. Establish the current repository, configuration, interfaces, tests, and applicable
   repository guidance before making local-state claims — a survey that size is a lane,
   not your own reading; §3 Current state holds the facts it returns with their evidence,
   never design. Current artifacts override historical notes.
3. Retrieve only the Research notes relevant to the stated goal: start from notes the user
   names, then search narrowly by shared `topic/*`, `strategy/*`, and `platform/*` tags. Do
   not crawl the vault. Link what materially informed the design in §4 Research basis.
4. Search `Design/` for an existing specification that owns the feature; update it rather
   than creating a parallel one unless the user intentionally branches the design.
5. Use Hindsight for relevant project history and prior decisions, not as proof of current
   state.

Verification depth is not self-judged. A load-bearing premise is a `P-n` row in one of the
standard's states: `verified`, with evidence attached (file:line, command output, or a
version-matched document); `awaiting verification` — the check was attempted and a named
obstacle blocks it, recorded with what was tried, what blocks it, and what will unblock it;
or `disproven`, which reopens the decision resting on it. There is no assumed-by-choice state: "checked enough", "obviously fine", and an unattempted
check filed as an assumption are the evasions this rule closes. Never cap a check because
the lookup grew; when a check is genuinely blocked, file the blocker and let the user rule.
If the work exposes a broad evidence gap, record a precise research question as a `Q-n`
row; if it blocks the design, stop and let the user decide whether to start
`/research-note` separately — never invoke that skill automatically.

## Develop and challenge the design

- Describe the current state and the forces that constrain the design before selecting a
  solution. Compare credible alternatives and make tradeoffs explicit; the chosen design
  goes to §5, the alternatives and their rejection go to the `D-n` row, never to the body.
- Every consequential decision rests on `P-n` rows. Never present a decision for
  ratification over silent or unlabeled premises, and never assert dependency runtime
  behavior — threading, retries, lifecycle, failure modes — from recall. A premise you
  can settle within the delegation boundary's inline allowance you may settle yourself;
  every other one routes to a `verifier` lane before presenting, or the ruling goes to
  the user explicitly conditional on the named `P-n`. When in doubt whether a claim is
  load-bearing, it is.
- Specify architecture, components, data flows, interfaces, state transitions, operational
  behavior, security and privacy boundaries, migration or rollout, observability, and
  testing across §5–6, omitting what genuinely does not apply. Build in the standard's
  order: the `O-n` oracle rows first, then the smallest design expressing exactly those
  rows, then the `A-n` rows whose values the oracles supply. A design settled before its
  oracles acquires fields no authority requires, and acceptance values written after the
  design get read back off the thing they exist to test.
- Sourcing an oracle's authority is a lane, and the lane must not have read the design: a
  `researcher` sent for a source's own rules and worked examples returns numbers nobody
  derived from the specification. Where no external authority exists the oracle is a
  formula you put to the user, or their ruling by `D-n` — never your own reading of prose
  left unreduced, which is the form that can be neither checked nor argued with.
- Keep the design internally consistent and implementation-ready at the level requested.
  Do not edit production code, implement the feature, or expand into unrelated work.
- Invoke no Codex skill during design. The single exception is the premise audit the
  handoff step runs; the user may additionally request `/codex-plan-review` after
  completion.

Delegation is not optional here. Under the delegation boundary in `~/.claude/CLAUDE.md`
you keep coupled design reasoning, user decision points, conflict resolution, and every
vault write; everything else is a lane. Repository and web surveys go to `researcher`;
premise checks, command and probe runs, and bounded specialist critiques — security,
performance, operations, testability — go to `verifier`. Pressure-testing your own
candidate design is the case most often skipped and the one a lane most repays: send the
design out to be attacked rather than arguing both sides of it yourself. Require compact
findings with evidence paths, never raw output, and prohibit lanes from editing the
canonical note or implementation. A returned verdict lands as **Verify a premise** before
later reasoning depends on it.

## Tier the implementation sequence

Every `W-n` row in §8 carries a logical complexity tier — `trivial`, `standard`, or
`complex` — per `~/.claude/skills/implement/references/complexity-tiers.md`, the `R-n`
rows it covers, and the `P-n` rows that are its stop conditions. The tier expresses
difficulty only; the `implement` workflow translates it into an executing model, so specs
never name models. Propose each tier with a one-line rationale and settle it with the user
like any other decision; tier the work item, not its file count; tie-break upward.

## Maintain the vault artifact

- Every write is one of the standard's operations, performed as a targeted `patch_note`
  replacement or a whole-file `write_note` on a named path — never `write_note`'s `append`
  or `prepend` mode, and `patch_note` keeps `replaceAll` at its `false` default.
- Store newly created diagrams and design media on disk under
  `$OBSIDIAN_VAULT_PATH/Design/attachments/` with the ordinary file tools, creating the
  directory if absent — no mcpvault tool writes a binary, so this is the mechanism, not a
  fallback. Embed them with relative `attachments/...` paths; embed source evidence directly
  from `Research/attachments/` rather than copying it.
- Tags follow the standard's contract — a specification primary type, at least one
  `topic/*`, `strategy/*` and `platform/*` only when inherited from a linked Research note.
  A value not already carried by another note is proposed to the user with the inventory
  searched for a synonym first, and enters the note only as **Introduce a tag** after the
  user's ruling.
- Body budget is a tripwire: when the status block shows it exceeded, the next **Checkpoint**
  asks of each block whether it is design or bulk — bulk moves to an appendix or a linked
  note, design stays at whatever size it is, and nothing is cut.

## Complete the handoff

Checkpoint, then verify: the self-check passes; every `W-n` has a settled tier and
covers at least one `R-n`; every `R-n` has an `A-n`; every `A-n` names an `O-n` and every
`O-n` carries a settled authority that is not the design; every field, enum member and
default in §5–6 cites the `O-n` requiring it; every `P-n` is `verified` or `awaiting
verification` with its attempt and blocker recorded; no `[Q-n]` remains in the body once
the status moves to `ratified`. A premise still awaiting verification is named in the
handoff summary and is a binding stop condition in every `W-n` that rests on it. You never
move the status to `ratified` yourself: it goes there on the user's word, and only once no
`D-n` row still reads `orchestrator` and no `A-n` is missing its oracle — that status is
what authorises implementation, so setting it is granting yourself the authority to build.

Run a requirements-quality review of §2 and §7 — the judgment the self-check does not make:
attributes without a measurable value, requirements with a verb and no observable object,
acceptance rows whose result is not observable, terminology that drifts between sections.
The oracle register takes its own question, the one that catches a design built on a misread
source: does every `O-n` say what its cited authority says. That question is answered against
the authority and the row alone — a reviewer handed the design checks the specification
against itself, which is how a wrong rule survives every gate downstream of it.
For a sequence containing a `complex` item or any premise still awaiting verification, this
is the `codex-plan-review` premise audit (the user may wave it off); otherwise a `verifier`
lane reads the two registers. Findings follow the reviewer rules: each cites the `R-n`,
`A-n`, `D-n`, or `P-n` it challenges — a finding that introduces a decision the owner has
not made is contract invention, rejected not incorporated. Present every finding that would
change what the specification means to the user with its concrete scenario — when it occurs,
when it does not, its effect — and change the specification only on the user's ruling, as
**Record a decision**, never directly from the review. Materiality orders how you present
findings; it never decides whether the user hears one. Spelling, formatting and id
renumbering are the whole of what lands without a ruling, and the message reporting the
findings lists them.

No part of a specification is mechanics. The mechanics-and-decisions split governs code
briefs, where a disclosed design sits above an implementation free to vary beneath it; a note
has no layer below its text, so every clause is a decision or a premise. "Minor", "a
leftover of mine", and "mechanics under an earlier ruling" are the three phrasings this rule
exists to refuse — each one ends with the specification edited on the agent's authority.

Summarize the settled decisions, remaining risks or research gaps, and the exact
implementation entry point, quoting the status block. Stop at the completed specification
until the user separately authorizes implementation via `/implement`.
