---
name: design-spec
description: Iteratively develop architecture, feature designs, and implementation-ready specifications in Obsidian under Design/, using current repository state and selected Research notes as evidence. Use only when the user explicitly invokes /design-spec or explicitly asks to begin a design or implementation-specification workflow. Do not implement the design, conduct unrelated broad research, or invoke another workflow automatically.
---

# Develop a Design Specification

Turn an explicit goal into a durable, decision-oriented specification. Treat the Obsidian Design note
as the canonical working context and keep implementation outside this workflow.

## Maintain write-through context

Establish the draft specification before extended design reasoning. Seed it immediately with the
problem, goals, known constraints, Research basis, the initial premise register, and unresolved
decision agenda.
Never design the whole system in chat and write the specification only after the discussion ends.

- Work through consequential design points iteratively. Raise one coherent decision or tightly coupled
  group of decisions, present the evidence and tradeoffs, and obtain the user's direction before treating
  it as settled.
- Immediately patch the specification whenever the user accepts, rejects, amends, or defers a point.
  Record the decision, rationale, relevant rejected alternatives, consequences, and resulting changes to
  downstream sections or open questions before moving to the next point.
- Mark unapproved proposals as pending rather than blending them into the agreed design. Keep the note's
  distinction between settled decisions, premises awaiting verification, and unresolved questions
  explicit.
- Re-read the relevant specification sections before raising the next decision, and after compaction,
  resumption, or a long diversion. The current note—not recalled transcript detail—is authoritative.
- Reconcile superseded material in place so the specification always presents a coherent current design
  while retaining concise rationale for meaningful rejected or replaced choices.

## Establish the design boundary

1. Clarify the problem, stakeholders, goals, non-goals, constraints, approval boundaries, acceptance
   criteria, and required level of implementation detail. Ask only about choices that would materially
   change the design.
2. Inspect the current repository, configuration, interfaces, tests, and applicable repository guidance
   before making local-state claims. Current artifacts override historical notes.
3. Retrieve only the Research notes relevant to the stated goal. Start from notes the user names, then
   search narrowly by shared `topic/*`, `strategy/*`, and `platform/*` tags. Do not crawl the vault.
4. Search `Design/` for an existing specification that owns the feature. Create or open the canonical
   draft and seed its working sections before continuing the design conversation.
5. Use Hindsight for relevant project history and prior decisions, not as proof of current state.

Verification depth is not self-judged. A load-bearing premise has exactly two legal states:
evidence attached (file:line, command output, or a version-matched document), or *awaiting
verification* — the check was attempted and a named obstacle blocks it, recorded with what was
tried, what blocks it, and what will unblock it, where the user sees it at ratification and the
handoff blocks on it. There is no assumed-by-choice state: "checked enough", "obviously fine", and
an unattempted check filed as an assumption are the exact evasions this rule exists to close. Stay
targeted and never cap a check because the lookup grew — when a check is genuinely blocked, file
the blocker and let the user rule. If the work exposes a broad evidence gap, record a precise
research question. If it blocks the design, stop and let the user decide whether to start
`/research-note` separately; never invoke that skill automatically.

## Develop and challenge the design

- Describe the current state and the forces that constrain the design before selecting a solution.
- Compare credible alternatives and make tradeoffs explicit. Record the chosen design, rationale,
  rejected alternatives, consequences, failure modes, and unresolved decisions.
- Every consequential decision carries a **premise register**: the load-bearing claims it rests on,
  each marked *verified* (with this-session evidence — file:line of installed source, command
  output, or a version-matched document), *awaiting verification* (the check was attempted; record
  what was tried, the specific blocker, and what will unblock it), or *disproven* (the decision
  reopens). Never present a decision for ratification over silent or unlabeled
  premises, and never assert dependency runtime behavior — threading, retries, lifecycle, failure
  modes — from recall. Verify cheap premises before presenting; route deep ones to a `verifier`
  lane first, or present the ruling as explicitly conditional on the named verification. When in
  doubt whether a claim is load-bearing, it is — the same tie-break-upward rule tiers use.
- Specify the relevant architecture, components, data flows, interfaces, state transitions, operational
  behavior, security and privacy boundaries, migration or rollout, observability, testing, and acceptance
  evidence. Omit sections that genuinely do not apply.
- Keep the design internally consistent and implementation-ready at the level requested. Do not edit
  production code, implement the feature, or expand into unrelated work.
- Invoke no Codex skill during design. The single exception is the premise audit the handoff step
  runs on the completed specification; the user may additionally request `/codex-plan-review` at any
  point after completion.

Use subagents selectively: independent read-heavy repository or web surveys go to `researcher` lanes
(compact evidence memo), load-bearing premise checks go to `verifier` lanes (verdict with
falsification-grade evidence), and bounded specialist critiques — security, performance, operations,
testability — to whichever fits. Require compact findings with evidence
paths, not raw output. Prohibit subagents from editing the canonical note or implementation. Keep
coupled design reasoning, user decision points, conflict resolution, and all vault writes in the
orchestrator. Update the specification with any verified evidence or newly raised decision before
later reasoning depends on it.

## Tier the implementation sequence

Every item in the specification's implementation sequence carries a logical complexity tier —
`trivial`, `standard`, or `complex` — per `~/.claude/skills/implement/references/complexity-tiers.md`.
The tier expresses the item's difficulty only; the `implement` workflow translates it into an
executing model through that file's routing table, so specs never name models and stay valid when
the model lineup changes.

- Propose each item's tier with a one-line rationale and settle it with the user like any other design
  decision.
- Tier the work item, not its file count; tie-break upward when in doubt.

## Maintain the vault artifact

- Search `Design/` before creating a note. Update the existing specification when it owns the feature;
  avoid parallel specs unless the user intentionally branches the design.
- Create and update canonical Markdown under `Design/`. Patch deliberately and reconcile superseded
  decisions instead of leaving conflicting append-only history.
- Store newly created diagrams and design media under `Design/attachments/` using relative
  `attachments/...` embeds. Embed source evidence directly from `Research/attachments/` when
  appropriate; do not copy it into Design merely to colocate it.
- Add a `Research basis` section containing explicit wikilinks to the Research notes that materially
  informed the design. Tags support discovery; links preserve exact provenance.
- Keep the note synchronized immediately after every material user decision. Treat impending context
  compaction as a mandatory consistency check, not as the first time the discussion is persisted.

A substantial specification normally covers the problem, goals and non-goals, constraints and current
state, research basis, alternatives, chosen design, interfaces and data flows, failure and operational
behavior, validation, the tiered implementation sequence, and open questions. Adapt this shape to the
task rather than adding empty boilerplate.

## Apply the established tags

Write tags through the YAML `tags` property. Inspect existing vault tag values before choosing them.

- Assign exactly one primary artifact tag: `type/spec` for a normative architecture or implementation
  specification, or `type/plan` when the artifact is primarily an execution plan.
- Carry forward only the relevant `topic/*`, `strategy/*`, and `platform/*` tags from supporting
  Research notes. Preserve shared subject identity while replacing source-role tags such as
  `type/research`, `type/video-notes`, and `type/moc`.
- Preserve correct existing tags when updating a spec. Introduce a new value only when no established
  tag expresses the concept, using the appropriate namespace and lowercase kebab-case.

## Complete the handoff

Verify the saved note path, primary type, inherited subject tags, Research wikilinks, media embeds,
that every implementation-sequence item carries a settled complexity tier, and that every decision's
premise register is verified — or awaiting verification, with the attempt and its blocker recorded.
A premise still awaiting verification is named in the handoff summary and becomes a binding stop
condition in every implementation item that rests on it.

When the sequence contains a `complex` item or any premise still awaits verification, run the
`codex-plan-review` premise audit before declaring the specification implementation-ready (the user
may wave it off). Its findings follow the reviewer rules: each must cite the spec decision or
premise it challenges — a finding that introduces a design decision the owner has not made is
contract invention, rejected not incorporated. Present every material finding to the user with its
concrete scenario — when it occurs, when it does not, and its effect, in plain terms — and change
the specification only on the user's ruling, never directly from the review.

Summarize the settled decisions, remaining risks or research gaps, and the exact implementation
entry point. Stop at the completed specification until the user separately authorizes implementation
via `/implement`.
