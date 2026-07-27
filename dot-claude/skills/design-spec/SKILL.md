---
name: design-spec
description: Iteratively develop architecture, feature designs, and implementation-ready specifications in Obsidian under Design/, using current repository state and selected Research notes as evidence. Use only when the user explicitly invokes /design-spec or explicitly asks to begin a design or implementation-specification workflow. Do not implement the design, conduct unrelated broad research, or invoke another workflow automatically.
---

# Develop a Design Specification

Turn an explicit goal into a durable, decision-oriented specification. Treat the Obsidian Design note
as the canonical working context and keep implementation outside this workflow.

## Maintain write-through context

Establish the draft specification before extended design reasoning. Seed it immediately with the
problem, goals, known constraints, Research basis, current assumptions, and unresolved decision agenda.
Never design the whole system in chat and write the specification only after the discussion ends.

- Work through consequential design points iteratively. Raise one coherent decision or tightly coupled
  group of decisions, present the evidence and tradeoffs, and obtain the user's direction before treating
  it as settled.
- Immediately patch the specification whenever the user accepts, rejects, amends, or defers a point.
  Record the decision, rationale, relevant rejected alternatives, consequences, and resulting changes to
  downstream sections or open questions before moving to the next point.
- Mark unapproved proposals as pending rather than blending them into the agreed design. Keep the note's
  distinction between settled decisions, working assumptions, and unresolved questions explicit.
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

Perform small, targeted authoritative lookups needed to keep the design correct. If the work exposes a
broad evidence gap, record a precise research question. If it blocks the design, stop and let the user
decide whether to start `/research-note` separately; never invoke that skill automatically.

## Develop and challenge the design

- Describe the current state and the forces that constrain the design before selecting a solution.
- Compare credible alternatives and make tradeoffs explicit. Record the chosen design, rationale,
  rejected alternatives, consequences, assumptions, failure modes, and unresolved decisions.
- Specify the relevant architecture, components, data flows, interfaces, state transitions, operational
  behavior, security and privacy boundaries, migration or rollout, observability, testing, and acceptance
  evidence. Omit sections that genuinely do not apply.
- Keep the design internally consistent and implementation-ready at the level requested. Do not edit
  production code, implement the feature, or expand into unrelated work.
- Never invoke a Codex skill. The user may request `/codex-plan-review` separately after the complete
  specification exists and before implementation when its exceptional-review criteria are met.

Use subagents selectively for independent, read-heavy repository or web surveys — route those lanes to
the `researcher` subagent, which returns a compact evidence memo — and for bounded specialist critiques
such as security, performance, operations, or testability. Require compact findings with evidence
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

Verify the saved note path, primary type, inherited subject tags, Research wikilinks, media embeds, and
that every implementation-sequence item carries a settled complexity tier. Summarize the settled
decisions, remaining risks or research gaps, and the exact implementation entry point. Stop at the
completed specification until the user separately authorizes implementation via `/implement`.
