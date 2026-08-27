---
name: research-note
description: Conduct source-grounded research and iteratively maintain durable Obsidian knowledge under Research/, with embedded media under Research/attachments/. Use only when the user explicitly invokes /research-note or explicitly asks to begin an Obsidian research workflow, evidence-gathering investigation, literature review, or ongoing research collection. Do not turn findings into a design or implementation specification or invoke another workflow automatically.
---

# Maintain Research Notes

Build an evidence base that matures across sessions without being forced toward a design.
The Obsidian note is the durable research record and primary working context; the chat is
transient scratch space.

## The note is a synthesis, not a lab notebook

Every Research note follows
`~/.claude/skills/design-spec/references/vault-note-standard.md` — read it before the first
write. The rules that shape everything below: §3 Synthesis holds the current conclusions
and is rewritten in place as evidence moves; what was run is an `X-n` row in the experiment
log and what changed scope or method is a `D-n` row in the decision log, never a new dated
section; the status block at the top is the note's whole state; the heading set is closed;
tags follow the contract. Enforcement is the template and the checkpoint: each section's
contract travels in the note as a comment, and every checkpoint runs the standard's
self-check against it.

## Maintain write-through context

Instantiate the note from
`~/.claude/skills/design-spec/references/note-template.md` before substantive investigation:
fill the frontmatter, status block, §1 Summary and §2 Questions and scope, replace every
remaining placeholder with real content or nothing, save. Never perform the full
investigation and write the note when it ends.

- After each material finding, source cluster, or contradiction, perform **Record a
  finding** from the standard's operations table: the `X-n` row if something was run, the
  `E-n` rows it produced, the affected `F-n` rewritten with its new confidence, the status
  block refreshed. A scope correction, a method change, or a resolved question is **Record a
  decision** — a `D-n` row and the affected section rewritten. One logical update.
- A claim that turns out wrong is **Correct a claim**: the `F-n` rewritten to what is now
  known plus one `X-n` or `D-n` row saying what was wrong and what corrected it. A
  correction is never a new section.
- **Checkpoint** before another substantial search lane, another subagent batch, or a branch
  that could consume significant context.
- Re-read §1, the status block, and §7 Runbook before deciding the next step, and after
  compaction, resumption, or a long diversion. The note, not recalled transcript, is the
  source of continuity — and §7 is the only resume point; there is no "read this first".

## Frame the research

1. Establish the research questions (`RQ-n` rows), scope, time horizon, constraints, and
   what would make the session sufficiently complete. Ask only when a missing choice would
   materially change the work.
2. Search `Research/` narrowly by topic, project, strategy, platform, and existing tags
   before creating a note. Open only relevant results. Update an existing note or map of
   content when it already owns the subject; avoid near-duplicates.
3. Decide whether the work belongs in one topic note, several focused notes, or an existing
   index, then instantiate or open that artifact before continuing. Research collections may
   stay `active` indefinitely and need not become design-ready.
4. Consult Hindsight only for relevant historical context. Verify current code,
   configuration, people, and external facts against current authoritative artifacts.

## Investigate and reduce

- Prefer primary and authoritative sources; use independent sources to corroborate,
  criticize, or expose competing interpretations.
- Every `F-n` carries one of the standard's confidence values and the `E-n` rows it rests
  on. Disagreement between sources is one `contested` finding with both sides' evidence, not
  two findings.
- Every `E-n` row cites a direct URL or a precise `file:line` and carries the source's own
  date. A search snippet or another agent's summary is never promoted to evidence.
- Follow material leads until the evidence converges or a specific gap is demonstrated;
  preserve real uncertainty as an open `Q-n` instead of forcing a conclusion.
- Record potentially useful applications in §5 Implications only. Do not create a file
  under `Design/`, produce an implementation specification, or invoke `/design-spec`.
- Never invoke a Codex skill. The user may request `/codex-research` separately.

Delegate read-heavy retrieval — web sweeps, source fetching, corpus and repository skims —
to `researcher` subagents whenever the fetching would otherwise flood this context, and run
independent lanes in parallel when the questions allow it. Give each lane a bounded question
and require a compact memo with findings, evidence, contradictions, unresolved gaps, and
source links or paths; never raw logs or page content. Read the load-bearing sources
yourself when a judgment depends on them. Keep source verification, contradiction
resolution, synthesis, taxonomy, and all vault writes in the orchestrator. Integrate each
verified contribution into the note before later work depends on it.

## Maintain the vault artifact

- Every write is one of the standard's operations, performed as a targeted `patch_note`
  replacement or a whole-file `write_note` on a named path — never `write_note`'s `append`
  or `prepend` mode, and `patch_note` keeps `replaceAll` at its `false` default.
- Store newly captured research media on disk under `$OBSIDIAN_VAULT_PATH/Research/attachments/`
  with the ordinary file tools, creating the directory if absent — no mcpvault tool writes a
  binary, so this is the mechanism, not a fallback. Embed it with the vault's relative
  `attachments/...` paths and keep source media there if a Design note later embeds it.
- A map-of-content note (`type/moc`) that indexes the collection follows only the
  standard's frontmatter and tag contract; update it when adding to the collection.
- Tags follow the standard's contract — a research primary type, every materially relevant
  `topic/*`, `strategy/*` and `platform/*` only when the note is genuinely scoped to them.
  A value not already carried by another note is proposed to the user with the inventory
  searched for a synonym first, and enters the note only as **Introduce a tag** after the
  user's ruling.
- The §3 budget is a tripwire: when the status block shows it exceeded, the next
  **Checkpoint** asks of each block whether it is a conclusion or supporting detail — detail
  moves to an appendix, conclusions stay, and nothing is cut.

## Close the session

Checkpoint, then verify the self-check passes, every `E-n` has a source and date,
every `F-n` names its evidence, and §7 Runbook would let a fresh session resume. Report
which notes were created or updated, the strongest conclusions with their confidence,
material uncertainties, and the most promising next research questions, quoting the status
block. Do not imply that a design workflow has started.
