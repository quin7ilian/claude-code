# Vault note standard

The single home for the shape of every Obsidian note the `design-spec` and `research-note`
workflows create or maintain. The templates beside this file instantiate it and carry its
section contracts as comments; the skills' checkpoint operation verifies it. A rule lives
here once — the skills reference it, never restate it.

A note written to this standard reads like a document prepared for a principal-engineer
review: the current design or current conclusions, legible in one pass, with history kept
in a dedicated log the way version control keeps it out of the working tree.

It governs two document types: specifications (`type/spec`, `type/plan`) and research notes
(`type/research`, `type/video-notes`). Other notes — a map of content (`type/moc`), anything
later — follow only the frontmatter and tag contract.

## The two invariants everything else serves

1. **The body is current state only.** Every section outside the logs describes the design
   or the conclusions as they stand now. Nothing in the body says what was previously
   decided, what a section supersedes, when something changed, or where a reader should
   start. A reader who has never seen the note reads it top to bottom and is never routed.
2. **History lives in the logs, by row.** Every change of decision, every correction, every
   scope change is one row in the decision log (and, for research, the experiment log).
   The body references a row by its id and never carries the row's content.

## Shape

Both note types share the same mechanics; they differ only in their section set.

### Frontmatter

```yaml
---
tags: [⟨type/…⟩, ⟨topic/…⟩]
status: ⟨enum⟩
phase: ⟨one line — the stage the work is in⟩
next_step: ⟨one line — the single next action⟩
updated: ⟨YYYY-MM-DD⟩
---
```

`status` enums — specification: `draft` · `in-review` · `ratified` · `implementing` ·
`parked` · `done`; research: `active` · `parked` · `concluded`.

### Title and status block

One H1, equal to the file's stem. Immediately below it, one blockquote — the status block —
with exactly these lines, in this order (the research variant omits *Premises awaiting
verification*):

```markdown
> **Status**: ⟨status⟩ · **Phase**: ⟨phase⟩
> **Next step**: ⟨next_step⟩
> **Last decision**: D-⟨n⟩ — ⟨one line⟩ (or — before the first decision)
> **Open questions**: ⟨count⟩ · **Premises awaiting verification**: ⟨count⟩
> **Body**: ⟨words⟩ words of ⟨budget⟩
```

Every value in the block is non-empty. The status block is the whole note's state in five lines. A reviewer reads it and knows
whether to read further; a resuming agent reads it and knows what to do next. It is
rewritten in the same write as any change it summarises.

### Section set — specification (`Design/`)

| # | H2 | Contract |
|---|---|---|
| 1 | Summary | At most 10 non-blank lines. What is being built and why. A reviewer may stop here. |
| 2 | Problem, goals, non-goals | The problem; goals as requirement rows `R-n`; explicit non-goals. |
| 3 | Current state | Verified facts about the repository and environment, each with evidence (`file:line`, command output, version-matched document). Facts, never design. |
| 4 | Research basis | Wikilinks to the Research notes that materially informed the design, one line each on what was taken. |
| 5 | Design | The chosen design as it stands. Architecture, components, data flow, invariants. Alternatives appear only as decision-log rows. |
| 6 | Interfaces and behaviour | Contracts, state transitions, failure and operational behaviour, security and privacy boundaries, migration, observability — those that apply. |
| 7 | Validation and acceptance | Table of `O-n` oracle rows: rule · formula in named variables or stated invariant · authority (an external source cited to document and section, or a `D-n`) · worked example as inputs → expected output. Then table of `A-n` rows: scenario · exact expected result · oracle `O-n` · covers `R-n`. Concrete observable values, never prose. |
| 8 | Implementation sequence | Table of `W-n` rows: item · tier · status · depends on · covers `R-n` · stop conditions. Tiers per `complexity-tiers.md`; status `todo` · `in-progress` · `done` · `blocked` · `dropped`. |
| 9 | Premise register | Table of `P-n` rows: claim · state (`verified` · `awaiting verification` · `disproven`) · evidence, or what was tried, what blocks it, what unblocks it. |
| 10 | Open questions | Table of `Q-n` rows: question · what it blocks · status (`open` · `answered → D-n`). |
| 11 | Decision log | Table of `D-n` rows: date · who decided (`owner` · `orchestrator` · `orchestrator → D-m`) · the ask as it was put to the user · decision · supersedes (`D-m` or —) · rationale and rejected alternatives in one or two lines. Append-only. |
| — | Appendix A… | Bulky evidence referenced from the body by anchor. Any number, lettered, each titled `Appendix X — ⟨title⟩`. |

### Section set — research note (`Research/`)

| # | H2 | Contract |
|---|---|---|
| 1 | Summary | At most 10 non-blank lines. What was asked and what is now known. |
| 2 | Questions and scope | Research questions as `RQ-n` rows with status (`open` · `answered` · `dropped`); scope, horizon, constraints. |
| 3 | Synthesis | Current conclusions as `F-n` findings, each with a confidence (`established` · `probable` · `contested` · `speculative`) and the `E-n` evidence it rests on. Rewritten in place as evidence moves. |
| 4 | Evidence | Table of `E-n` rows: source (URL or `file:line`) · source date · what it shows · which `F-n` it supports or contradicts. |
| 5 | Implications | What the findings would mean for design or practice — implications only, never a specification. |
| 6 | Open questions | Table of `Q-n` rows: question · why it matters · status (`open` · `answered → D-n` or `answered → X-n`). |
| 7 | Runbook | How to reproduce or resume: scripts, commands, data locations, parameters. One copy, always current. |
| 8 | Experiment log | Table of `X-n` rows: date · what was run · result · which `F-n` it changed. Append-only. |
| 9 | Decision log | Table of `D-n` rows: date · who decided (`owner` · `orchestrator` · `orchestrator → D-m`) · the ask as it was put to the user · decision (scope correction, method change, tag introduction) · supersedes · rationale. Append-only. |
| — | Appendix A… | As for specifications. |

### Closed heading set

The H2 set is exactly the table above, numbered and in order, plus appendices. H3s are free
inside a section as long as they name a part of the current design or current findings —
never a date, a revision, a correction, or a reading instruction. Adding an H2 is a
deviation from the standard, not an extension of the note; content that does not fit a
section goes to an appendix or a separate note.

### Identifiers and cross-references

Registers assign ids in their own namespace — `R-n` requirements, `O-n` oracles, `A-n`
acceptance rows, `W-n` work items, `P-n` premises, `Q-n` open questions, `D-n` decisions,
`T-n` tag introductions (specification); `RQ-n`, `F-n`, `E-n`, `X-n`, `Q-n`, `D-n`, `T-n`
(research).
Ids are never reused or renumbered. The body references a register entry by id only; an id
referenced anywhere must exist in its register. Where this standard lists the legal values of
a register column — `W` status, `P` state, `Q` and `RQ` status, `F` confidence, `D` decided
by — a cell holding anything else is an error. Every `R-n` is covered by at least one `W-n`
and at least one `A-n`; every `W-n` names at least one `R-n`; every `A-n` names one `O-n`.

### Authority, the ask, and the ruling

A `D-n` row records who decided, what they were asked, and what was ruled. Not every decision
in a log is the user's, and a log that cannot tell them apart reads as consent to all of them.

`Decided by` holds one of three values. `owner` — the user ruled. `orchestrator` — the agent
made the call on its own authority and it stands unratified. `orchestrator → D-m` — the agent
made the call and the user ratified it later, in that named row. No row is written without
one.

`Asked` holds the ask as it was put to the user, in one line, verbatim in substance — the
proposal they answered, never a summary composed afterward from the decision. An `owner` row
always carries its ask; an `orchestrator` row carries `—`, because nothing was put to anyone.
The exception is a row already in the log whose ask cannot be recovered: `owner` beside `—`
means exactly that, and it is never legal on a row being written now. Together the cells make
the log auditable — a reader sees at a glance which rulings are the user's and which the agent
is still carrying alone, and compares proposal against outcome without reconstructing either.
A row whose `Decision` reaches past its `Asked` is an error whose excess is not ratified.

A ruling that contradicts, narrows, or overrides an earlier `D-m` names it in `Supersedes`, and
that override is part of the ask that earned the ruling — never filled in from the agent's own
reading after the user answered. An override noticed while writing is an unratified decision:
the row does not land, and the override goes back as its own ask. Because the body carries
current state only, these cells are the sole surviving record that a prior ruling was displaced
at all.

A specification reaches `ratified` on the user's word alone, and only when no row is
`orchestrator` and every `A-n` names an `O-n` whose authority is settled — an unratified row
is a decision the design rests on that its owner has never seen, and an acceptance row with
no oracle is a number nobody has traced. The agent never sets that status itself, and
`ratified` is what authorises implementation, so setting it is granting oneself the authority
to build.

### The oracle

An acceptance row states a number, and nothing about a number says where it came from: a
value an authority published and a value read back off the implementation sit in the same
cell looking identical. The `O-n` register is what tells them apart.

An oracle is what a result is checked against, and it qualifies only if it can be evaluated
without the implementation. Three forms do: an external source's own rule, cited to document
and section; a formula in named variables the specification states; the user's ruling, named
by its `D-n`. Three do not: the implementation's current behaviour, a reading of prose never
reduced to a formula, and a value whose derivation nobody recorded. A row that would have to
claim one of those is not an oracle but the open question it stands in for, and it waits in
§10 until the user settles it.

Every `A-n` names the `O-n` its expected result comes from. A row that cannot name one
describes what will happen rather than testing whether the right thing happened, and it
passes just as green when the design is wrong — the whole failure acceptance rows exist to
catch. The worked example in an oracle row is computed from its authority by someone who has
not read the design; where the design is the only thing that can produce the number, there is
no oracle yet.

The design answers to the register rather than sitting beside it. Every field, enum member,
parameter and default in §5–6 cites the `O-n` rows that require it, and a value an oracle
derives is never a configurable field. A parameter no row needs is a shape no authority has:
validation that admits it will eventually be handed it, and a test suite will then pin that
shape as intended behaviour. The register runs in one direction — rows first, then the
smallest design expressing exactly those rows.

When the register outgrows the body budget the worked examples move to an appendix and the
row cites the anchor, but the formula and the authority stay in the row: they are the contract
the design is derived from, and an appendix is optional reading.

### The one marker

`[Q-n]` is the only inline marker, placed where the body depends on an open question whose
row exists in §10. No ⚠️, no `TODO`, no `NEEDS CLARIFICATION`, no "see below". A
specification in `ratified`, `implementing`, or `done` carries no `[Q-n]` in its body.

### History vocabulary

In body prose — every section except the logs, the status block, and table rows — the
following do not appear: dates; `previously`, `formerly`, `superseded`, `supersedes`,
`decided`, `as of`, `start here`, `read this first`, `resume state`, `ratified revision`,
`CORRECTION`; the ⚠️ glyph. The list is deliberately short and unambiguous — a word that
also has an everyday current-state meaning is not on it. A date inside a table row (a verification date in §3, a
source date in §4) is evidence and is allowed. The words are legal in log rows, where they
are the point.

### Placeholders

Templates mark content to be filled with `⟨angle brackets⟩`. A `⟨` anywhere in a saved note
outside comments and code is an unfilled placeholder and an error: Instantiate fills what is
known and leaves the rest empty — a heading with nothing under it, a table with only its
header row — rather than saving a placeholder.

### Comments

Template comments (`<!-- … -->`) are kept: Obsidian hides them in reading view and every
agent re-read sees the section's contract. The agent may add its own comments beside a
section as working memory — what was verified against what, what a checkpoint left
unfinished, where a resume should look first — and they survive compaction the way the
template's do. Two rules keep that channel from becoming the scratchpad the body is not: a
comment is current state too, rewritten at the next checkpoint rather than appended to;
and nothing a reviewer needs to judge the design lives only in a comment — a decision, a
premise, a question, a finding is in visible text, and a comment may point at it but never
replace it.

### Body budget

Soft, and a tripwire rather than a cut. Specification: sections 1–10 ≤ 2,500 words.
Research: section 3 ≤ 1,500 words. Counted on visible text only — tables and diagrams count,
because the reviewer reads them; comments do not. Logs and appendices are exempt. The status
block reports the count so a reviewer sees the note's size up front. Over budget means the
next checkpoint asks one question of every block in the body: is this design, or is it
evidence and bulk that belongs in an appendix or a linked note? Bulk moves; design stays,
and a body that is over budget because all of it is design is correct at that size. The
budget never causes a detail to be omitted, and never moves history out of the logs.

## Tags

Tags are written only through the frontmatter `tags` property; an inline `#tag` in the
body is a violation. Every tag matches `^(type|topic|strategy|platform)/[a-z0-9]+(-[a-z0-9]+)*$`.

- **Exactly one primary type.** Specification: `type/spec` (normative design) or `type/plan`
  (primarily an execution plan). Research: `type/research`, `type/video-notes`, or
  `type/moc`. A specification never carries a research type and vice versa.
- **At least one `topic/*`.** `strategy/*` and `platform/*` only when the note is genuinely
  scoped to them.
- **Inheritance.** A specification's `strategy/*` and `platform/*` tags each appear on at
  least one note linked from its Research basis. Topic tags may be added freely.
- **No new vocabulary without a ruling.** A tag value not already carried by another note
  is legal only when the note's decision log carries a `T-n` row introducing it, and
  that row exists only after the user ratified the new value. A near-synonym of an existing
  value is the failure this rule exists for; search the inventory before proposing one.
- **Preservation.** Updating a note keeps its correct existing tags; a change of primary
  type or removal of a subject tag is a decision-log row.

## Operations

Every write to a note is one of these operations, and every operation ends with the
affected section re-read against its template contract — the same contract code has with
its tests.

| Operation | What it writes, in one logical update |
|---|---|
| **Instantiate** | Copy the template for the note type, fill the frontmatter, the status block, and §1–2, replace every remaining placeholder with real content or nothing, save. |
| **Record a decision** | Read the decision log first; if the ruling displaces a `D-m` the ask did not name, nothing is written and the override returns as its own ask. Otherwise: one `D-n` row naming who decided it, carrying the ask and the ruling it earned, and reaching no further than the ask did · the affected body section rewritten to its new current state (the old text removed, not annotated) · the status block refreshed · any `Q-n` the decision answers marked `answered → D-n`. A decision the agent made itself is recorded `orchestrator` and reported to the user in the same turn — never dressed as a ruling, never left for them to discover. A scope correction, a method change, or a resolved question in a research note is a decision. |
| **Record an oracle** (spec) | One `O-n` row: the rule, its formula or invariant, its authority, and a worked example computed from that authority and not from the design · every `A-n` it serves updated to name it · every field, enum member and default it stops requiring removed from §5–6 in the same update. An oracle only the user can settle is a `Q-n` first and lands on the ruling. |
| **Verify a premise** (spec) | The `P-n` row's state and evidence updated · the status block's awaiting count refreshed · when the state becomes `disproven`, the decision resting on it reopens as a `Q-n`. |
| **Record a finding** (research) | One `X-n` row if something was run · the `E-n` rows it produced · the affected `F-n` rewritten with its new confidence · the status block refreshed. |
| **Correct a claim** | The claim rewritten in place to what is now known · one `D-n` (or `X-n`) row stating what was wrong and what corrected it. Never a "CORRECTION" section. |
| **Introduce a tag** | Only after the user's ruling: the `T-n` row · the tag added to frontmatter. |
| **Raise a question** | One `Q-n` row · `[Q-n]` at the body site that depends on it · the status block count refreshed. |
| **Checkpoint** | Before compaction, before a subagent batch, at handoff, and when the budget warns: re-read §1 and the status block, reconcile, move bulk to an appendix or a linked note, run the self-check below. |

Appending is the mechanical cause of append-only notes, so `write_note`'s `append` and
`prepend` modes are never used. Every update is either a targeted replacement — `patch_note`,
whose `replaceAll` stays at its `false` default so an ambiguous match fails loudly instead of
rewriting the wrong site — or a whole-file `write_note` in the default `overwrite` mode on a
named path.

## The self-check

Enforcement is prompt-level: the template carries each section's contract as a comment the
agent sees on every re-read, the operations above make the current-state shape the easiest
path, and the **Checkpoint** operation is the check. At every checkpoint, and always before
handoff or close, read the note's heading outline and status block against the template and
fix drift before continuing: the H2 set and order; frontmatter fields; every value in the
status block; every id the body references existing in its register; every `R-n` covered
by a `W-n` and an `A-n`; every `A-n` naming an `O-n`, and every `O-n` an authority that is
not the implementation; every field, enum member and default in §5–6 citing the `O-n` that
requires it; every `D-n` naming who decided it and carrying an ask its decision
does not reach past; no `orchestrator` row in a specification at `ratified` or beyond; every
displaced `D-m` named in the `Supersedes` cell of the row that displaced it; no date or
history vocabulary in body prose; no `⟨` left; tags per the contract. The reviewer's test
is the standard's: a principal engineer reads Summary → status block → Design and can
review without opening the log.

Vagueness and testability of requirements are judgment, not shape: the handoff review reads
the `R-n`, `O-n` and `A-n` registers with a requirements-quality lens — including whether each
oracle says what its cited authority says — and reports findings to the user for ruling.
