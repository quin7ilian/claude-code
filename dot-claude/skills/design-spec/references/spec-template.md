---
tags: [type/spec, ⟨topic/…⟩]
status: draft
phase: ⟨≤5 words — the stage⟩
next_step: ⟨≤15 words — the single next action⟩
updated: ⟨YYYY-MM-DD⟩
---

# ⟨Title — identical to the file stem⟩

> **Status**: draft · **Phase**: ⟨phase⟩
> **Next step**: ⟨next_step⟩
> **Last decision**: —
> **Open questions**: 0 · **Premises awaiting verification**: 0
> **Body**: 0 words of 2500

<!-- Standard: ~/.claude/skills/design-spec/references/vault-note-standard.md
     The body (§1–10) is current state only. History goes to §11 by row; the body
     references rows by id. Register rows are current values in one sentence, never a
     changelog. Sections are built to scan: H3 per part, bullets led by their subject, no
     paragraph over three sentences. phase ≤5 words, next_step ≤15, neither narrates.
     Keep these comments — Obsidian hides them in reading view. -->

## 1. Summary

<!-- ≤10 lines. What is being built and why. A reviewer may stop here. -->

⟨summary⟩

## 2. Problem, goals, non-goals

<!-- The problem in plain terms; goals as requirement rows; explicit non-goals.
     Every R-n is covered by at least one W-n (§8) and one A-n (§7).
     Each requirement is one sentence of at most 25 words. -->

⟨one or two sentences: the problem⟩

- **⟨Force or symptom⟩** — ⟨what it costs⟩

| Id | Requirement |
|---|---|
| R-1 | ⟨requirement⟩ |

**Non-goals**

- ⟨non-goal⟩

## 3. Current state

<!-- Verified facts about the repository and environment, each with evidence —
     file:line, command output, or a version-matched document. Facts, never design.
     A verification date belongs in a table row, not in prose. -->

| Fact | Evidence |
|---|---|
| ⟨fact⟩ | ⟨file:line / command / document⟩ |

## 4. Research basis

<!-- Wikilinks to the Research notes that materially informed the design, one line
     each on what was taken. strategy/* and platform/* tags must appear on one of these. -->

- [[⟨Research note⟩]] — ⟨what was taken⟩

## 5. Design

<!-- The chosen design as it stands: architecture, components, data flow, invariants.
     Alternatives and their rejection are D-n rows, not paragraphs here.
     Every field, enum member, parameter and default cites the O-n (§7) that requires it;
     a value an oracle derives is never a configurable field.
     One H3 per part — never a date, revision, or reading instruction. Under it, one or
     two sentences on what the part is, then bullets led by their subject; conditions are
     sub-bullets. No paragraph over three sentences. -->

### ⟨Component⟩

⟨one or two sentences: what it is and why it exists⟩

- **⟨Invariant⟩** — ⟨what holds⟩ (⟨O-n⟩)
- **⟨Failure mode⟩** — ⟨what happens, what the caller observes⟩

## 6. Interfaces and behaviour

<!-- Contracts, state transitions, failure and operational behaviour, security and
     privacy boundaries, migration, observability — those that apply. Omit what does not.
     A behaviour example here is worked from its O-n, never from the intended code.
     Every surface a caller can set cites the O-n that requires it.
     Structured like §5: H3 per interface or behaviour, bullets beneath. -->

### ⟨Interface or behaviour⟩

- **⟨Contract, transition, or failure⟩** — ⟨what holds⟩ (⟨O-n⟩)

## 7. Validation and acceptance

<!-- Two registers. O-n is the oracle: what a result is checked against, evaluable without
     the implementation. Legal authorities — an external source cited to document and
     section, a formula in named variables stated here, or the user's ruling by D-n. Never
     the implementation's current behaviour, never a reading of prose left unreduced, never
     a value whose derivation nobody recorded; a row that would claim one of those is a Q-n
     in §10 until the user settles it. The worked example is computed from the authority,
     not from the design.

     A-n is one row per observable outcome, each naming the O-n its expected result comes
     from. Concrete values, never prose — an implementer derives tests from these rows, and
     a row with no oracle passes green when the design itself is wrong.

     Rows are current values: text cells one sentence of ≤25 words (an O-n's formula and
     authority stay whole), reference cells ids only, no narration of how a row changed. -->

| Id | Rule | Formula or invariant | Authority | Worked example |
|---|---|---|---|---|
| O-1 | ⟨rule⟩ | ⟨formula in named variables⟩ | ⟨source · document §x, or D-n⟩ | ⟨inputs → expected output⟩ |

| Id | Scenario | Expected result | Oracle | Covers |
|---|---|---|---|---|
| A-1 | ⟨scenario⟩ | ⟨exact observable result⟩ | O-1 | R-1 |

## 8. Implementation sequence

<!-- Tiers per ~/.claude/skills/implement/references/complexity-tiers.md.
     Status: todo · in-progress · done · blocked · dropped; once done, plus one commit or
     PR reference. Item: one sentence of ≤25 words naming the deliverable — its detail is a
     work-item brief in an appendix, never the cell. Depends on, Covers, Stop conditions:
     ids only. A ruling that reshapes an item rewrites the row; it never extends it. -->

| Id | Item | Tier | Status | Depends on | Covers | Stop conditions |
|---|---|---|---|---|---|---|
| W-1 | ⟨item⟩ | ⟨trivial/standard/complex⟩ | todo | — | R-1 | ⟨P-n that must be verified, or —⟩ |

## 9. Premise register

<!-- Load-bearing claims the design rests on. State: verified · awaiting verification ·
     disproven. Evidence for verified; what was tried, what blocks, what unblocks for
     awaiting. There is no assumed-by-choice state.
     Claim: one sentence of ≤25 words. Evidence: a citation (file:line, command, document
     section) or an appendix anchor — never a narrative of the check. -->

| Id | Claim | State | Evidence / blocker |
|---|---|---|---|
| P-1 | ⟨claim⟩ | ⟨state⟩ | ⟨evidence or blocker⟩ |

## 10. Open questions

<!-- Reference from the body as [Q-n]. Status: open · answered → D-n.
     Question: the question alone, one sentence. The proposal and its argument belong in the
     ask put to the user, not the row. Blocks: ids only. -->

| Id | Question | Blocks | Status |
|---|---|---|---|

## 11. Decision log

<!-- Append-only. One row per decision, correction, scope change, or tag introduction
     (T-n rows live here too). Decision in one sentence; rationale and rejected alternatives
     in at most two. Reasoning that needs more — the constraints stated, the alternatives
     weighed, the evidence consulted, what a later agent must understand — goes in a
     reasoning comment below the table, one block per D-n in id order, opened "D-n —",
     written with its row and append-only like it. The note must be resumable from itself.
     Decided by is owner (the user ruled), orchestrator (the agent's own call, unratified),
     or orchestrator → D-m (its call, ratified later by that row). Every row has one.
     Asked is the ask as it was put to the user, one line, verbatim in substance — the
     proposal they answered, never a summary composed afterward from the decision. An owner
     row always carries its ask; an orchestrator row carries —. A Decision that reaches past
     its Asked is an error and its excess is not ratified. Supersedes names every D-m this
     ruling contradicts, narrows, or overrides, and the override was disclosed in the ask
     that earned the ruling. An override noticed while writing means the row does not land:
     it returns as its own ask. The spec reaches ratified on the user's word alone and only
     when no row is orchestrator. -->

| Id | Date | Decided by | Asked | Decision | Supersedes | Rationale |
|---|---|---|---|---|---|---|
