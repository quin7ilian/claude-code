---
name: research-note
description: Conduct source-grounded research and iteratively maintain durable Obsidian knowledge under Research/, with embedded media under Research/attachments/. Use only when the user explicitly invokes /research-note or explicitly asks to begin an Obsidian research workflow, evidence-gathering investigation, literature review, or ongoing research collection. Do not turn findings into a design or implementation specification or invoke another workflow automatically.
---

# Maintain Research Notes

Build an evidence base that can mature across sessions without forcing it toward a design. Treat the
Obsidian note as the durable research record and primary working context; treat the chat as transient
scratch space.

## Maintain write-through context

Establish the canonical note before substantive investigation. Seed it immediately with the scope,
questions, known context, initial tags, and source plan. Never perform the full investigation and dump
the result into Obsidian only at the end.

- Patch the note after each material finding, useful source cluster, contradiction, scope correction,
  or resolved question. Mark preliminary evidence and uncertainty honestly, then revise it as evidence
  strengthens or fails.
- Persist the current synthesis before starting another substantial search lane, dispatching another
  subagent batch, or following a branch that could consume significant context.
- Re-read the relevant note sections before deciding the next research step, and after compaction,
  resumption, or a long diversion. The note—not recalled transcript detail—is the source of continuity.
- Keep the note coherent while it grows. Update conclusions and evidence tables in place; preserve
  meaningful disagreement without accumulating stale, contradictory summaries.

## Frame the research

1. Establish the research question, scope, time horizon, relevant constraints, and what would make the
   session sufficiently complete. Ask only when a missing choice would materially change the work.
2. Search `Research/` narrowly by topic, project, strategy, platform, and existing tags before creating
   a note. Open only relevant results. Update an existing note or map of content when it already owns
   the subject; avoid near-duplicates.
3. Decide whether the work belongs in one topic note, several focused notes, or an existing index, then
   create or open that artifact before continuing. Research collections may remain active indefinitely
   and need not become design-ready.
4. Consult Hindsight only for relevant historical context. Verify current code, configuration, people,
   and external facts against current authoritative artifacts or sources.

## Investigate and reduce

- Prefer primary and authoritative sources. Use independent sources to corroborate, criticize, or
  expose competing interpretations.
- Distinguish measured or sourced facts, source claims, your own inference, disagreement, and
  unresolved questions. Record publication and event dates when recency matters.
- Cite load-bearing external claims with direct URLs and local claims with precise file paths and line
  references when practical. Never promote a search snippet or another agent's summary to evidence.
- Follow material leads until the evidence converges or a specific gap is demonstrated. Preserve real
  uncertainty instead of forcing a conclusion.
- Record potentially useful applications as research implications only. Do not create a file under
  `Design/`, produce an implementation specification, or invoke `/design-spec`.
- Never invoke a Codex skill. The user may request `/codex-research` separately when desired.

Delegate read-heavy retrieval — web sweeps, source fetching, corpus and repository skims — to
`researcher` subagents whenever the fetching would otherwise flood this context, and run two or more
independent lanes in parallel when the questions allow it. Give each lane a bounded question and
require a compact memo containing findings, evidence, contradictions, unresolved gaps, and source
links or paths; never raw logs or wholesale page content. Read the load-bearing sources yourself when
a judgment depends on them. Keep source verification, contradiction resolution, synthesis, taxonomy,
and all canonical vault writes in the orchestrator. Integrate each verified subagent contribution into
the note before allowing later work to depend on it.

## Maintain the vault artifact

- Create and update canonical Markdown notes under `Research/`. Patch existing notes deliberately;
  preserve useful content, frontmatter, links, and the note's established structure.
- Store newly captured research media under `Research/attachments/` and embed it with the vault's
  established relative `attachments/...` Markdown paths. Keep source media there if a later Design
  note embeds it; do not duplicate it merely to colocate it. If the available tools cannot write exact
  binary content safely, retain the source URL and report the gap instead of creating a corrupt
  placeholder.
- Update a relevant map-of-content note when adding material to an established collection.
- Keep the note current throughout the investigation. Treat natural phase boundaries and impending
  context compaction as mandatory reconciliation checks, not as the first time findings are written.

## Apply the established tags

Write tags through the YAML `tags` property. Inspect existing vault tag values before choosing them,
and reuse the established hierarchical vocabulary instead of creating synonyms.

- Assign exactly one primary artifact tag: `type/research` for general investigation,
  `type/video-notes` for video-source notes, or `type/moc` for an index or map of content.
- Add every materially relevant `topic/*` tag.
- Add `strategy/*` and `platform/*` only when the note is genuinely scoped to them.
- Preserve correct existing tags when updating a note. Introduce a new value only when no existing tag
  expresses the concept, using the appropriate namespace and lowercase kebab-case.
- Do not add `type/plan` or `type/spec` merely because the research may support later implementation.

## Close the session

Verify the saved note paths, frontmatter tags, source links, and embedded-media paths. Report which
notes were created or updated, the strongest conclusions, material uncertainties, and the most
promising next research questions. Do not imply that a design workflow has started.
