---
tags: [type/spec, ⟨topic/…⟩]
status: draft
phase: ⟨stage the work is in⟩
next_step: ⟨the single next action⟩
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
     references rows by id. Keep these comments — Obsidian hides them in reading view. -->

## 1. Summary

<!-- ≤10 lines. What is being built and why. A reviewer may stop here. -->

⟨summary⟩

## 2. Problem, goals, non-goals

<!-- The problem in plain terms; goals as requirement rows; explicit non-goals.
     Every R-n is covered by at least one W-n (§8) and one A-n (§7). -->

⟨problem⟩

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
     H3s name parts of the design — never a date, revision, or reading instruction. -->

⟨design⟩

## 6. Interfaces and behaviour

<!-- Contracts, state transitions, failure and operational behaviour, security and
     privacy boundaries, migration, observability — those that apply. Omit what does not. -->

⟨interfaces⟩

## 7. Validation and acceptance

<!-- One row per observable outcome: the scenario and the exact result it must produce.
     Concrete values, never prose — an implementer derives tests from these rows. -->

| Id | Scenario | Expected result | Covers |
|---|---|---|---|
| A-1 | ⟨scenario⟩ | ⟨exact observable result⟩ | R-1 |

## 8. Implementation sequence

<!-- Tiers per ~/.claude/skills/implement/references/complexity-tiers.md.
     Status: todo · in-progress · done · blocked · dropped. -->

| Id | Item | Tier | Status | Depends on | Covers | Stop conditions |
|---|---|---|---|---|---|---|
| W-1 | ⟨item⟩ | ⟨trivial/standard/complex⟩ | todo | — | R-1 | ⟨P-n that must be verified, or —⟩ |

## 9. Premise register

<!-- Load-bearing claims the design rests on. State: verified · awaiting verification ·
     disproven. Evidence for verified; what was tried, what blocks, what unblocks for
     awaiting. There is no assumed-by-choice state. -->

| Id | Claim | State | Evidence / blocker |
|---|---|---|---|
| P-1 | ⟨claim⟩ | ⟨state⟩ | ⟨evidence or blocker⟩ |

## 10. Open questions

<!-- Reference from the body as [Q-n]. Status: open · answered → D-n. -->

| Id | Question | Blocks | Status |
|---|---|---|---|

## 11. Decision log

<!-- Append-only. One row per decision, correction, scope change, or tag introduction
     (T-n rows live here too). Rationale and rejected alternatives in one or two lines. -->

| Id | Date | Decision | Supersedes | Rationale |
|---|---|---|---|---|
