---
tags: [type/research, ⟨topic/…⟩]
status: active
phase: ⟨stage the research is in⟩
next_step: ⟨the single next action⟩
updated: ⟨YYYY-MM-DD⟩
---

# ⟨Title — identical to the file stem⟩

> **Status**: active · **Phase**: ⟨phase⟩
> **Next step**: ⟨next_step⟩
> **Last decision**: —
> **Open questions**: 0
> **Body**: 0 words of 1500

<!-- Standard: ~/.claude/skills/design-spec/references/vault-note-standard.md
     §3 is the current synthesis, rewritten in place as evidence moves. What was run goes
     to §8 by row; scope and method changes to §9 by row. Keep these comments — Obsidian
     hides them in reading view. -->

## 1. Summary

<!-- ≤10 lines. What was asked and what is now known. -->

⟨summary⟩

## 2. Questions and scope

<!-- Research questions as rows; status: open · answered · dropped. Then scope, time
     horizon, constraints, and what would make the work sufficiently complete. -->

| Id | Question | Status |
|---|---|---|
| RQ-1 | ⟨question⟩ | open |

⟨scope⟩

## 3. Synthesis

<!-- Current conclusions only. Each finding carries a confidence — established · probable ·
     contested · speculative — and the E-n rows it rests on. Rewrite a finding when its
     evidence changes; never append a dated update beneath it. -->

**F-1** (⟨confidence⟩; E-1) — ⟨finding⟩

## 4. Evidence

<!-- One row per source. URL or file:line; the source's own date; what it shows; which
     findings it supports or contradicts. A search snippet or another agent's summary is
     not evidence. -->

| Id | Source | Date | Shows | Bears on |
|---|---|---|---|---|
| E-1 | ⟨URL or file:line⟩ | ⟨YYYY-MM-DD⟩ | ⟨what it shows⟩ | F-1 |

## 5. Implications

<!-- What the findings would mean for design or practice. Implications only — never a
     specification, never a file under Design/. -->

- ⟨implication⟩

## 6. Open questions

<!-- Reference from the body as [Q-n]. Status: open · answered → D-n / X-n. -->

| Id | Question | Why it matters | Status |
|---|---|---|---|

## 7. Runbook

<!-- How to reproduce or resume: scripts, commands, data locations, parameters.
     One copy, always current — never a dated "resume state" section. -->

⟨runbook⟩

## 8. Experiment log

<!-- Append-only. One row per thing run: date, what, result, which F-n it changed. -->

| Id | Date | Run | Result | Changed |
|---|---|---|---|---|

## 9. Decision log

<!-- Append-only. Scope corrections, method changes, tag introductions (T-n rows).
     Decided by is owner (the user ruled), orchestrator (the agent's own call, unratified),
     or orchestrator → D-m (its call, ratified later by that row). Every row has one.
     Asked is the ask as it was put to the user, one line, verbatim in substance — the
     proposal they answered, never a summary composed afterward from the decision. An owner
     row always carries its ask; an orchestrator row carries —. A Decision that reaches past
     its Asked is an error and its excess is not ratified. Supersedes names every D-m this
     ruling contradicts, narrows, or overrides, and the override was disclosed in the ask
     that earned the ruling. An override noticed while writing means the row does not land:
     it returns as its own ask. -->

| Id | Date | Decided by | Asked | Decision | Supersedes | Rationale |
|---|---|---|---|---|---|---|
