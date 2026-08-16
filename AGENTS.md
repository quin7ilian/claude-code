# AGENTS.md — working in the `claude-code` repo

Orientation for an agent editing this repo. Pairs with `README.md` (user-facing overview). When code
and this file disagree, the code wins — fix this file.

## What this repo is

A personal Claude Code setup: global guidance (`dot-claude/CLAUDE.md`), skills, subagent
definitions, a Codex review-gate wrapper, and the session hooks that carry memory, repository
instructions, and code-graph watching. `apply.sh` installs it (ownership-checked symlinks, MCP
registration, settings merge). Hindsight is the long-term memory; Obsidian is the research/design
vault; Codex is the only external model.

## Conventions

- **Skills** live in `dot-claude/skills/<name>/SKILL.md` with `name` and `description` frontmatter.
  Keep the invocation gate inside the description (explicit-invocation skills say so there). Skills
  never select a model or reasoning effort.
- **Subagents** live in `dot-claude/agents/<name>.md`. Pin `model` and `effort` in frontmatter —
  unpinned subagents inherit the session effort, letting an expensive session silently spawn
  expensive subagents. Subagent bodies are contracts: self-contained briefs in, compact summaries
  out, never raw logs.
- **Codex invocations** are non-interactive (`</dev/null`) and run `--sandbox workspace-write`
  with an ephemeral scratch `-C` and network/web enabled — the writable workspace is the scratch
  and `/tmp`, so the repository stays kernel-enforced read-only in every pass, reviews included.
  Never pass model or effort flags — Codex inherits the user's own configuration. Point Codex at
  files by absolute path instead of pasting large artifacts; never at secret-bearing paths.
- **Python** is OS-python3, pure stdlib — no venv, no third-party dependencies. Hooks are fail-open:
  never block a turn, never print errors into a session, never log payloads or credentials.
- **One home per rule.** The tier vocabulary and its model/effort/review tables live in
  `dot-claude/skills/implement/references/complexity-tiers.md`; the code-review contract lives in
  `bin/codex-review`; behavioral policy lives in `dot-claude/CLAUDE.md`. Reference them; never fork
  or restate them here.
- **Comments and docs describe current state only** — what a thing does, its contract, its
  constraints. No history, no provenance.
- **No personal information in this repository.** No names, emails, locations, hardware
  inventories, or real home paths — in code, docs, tests, or fixtures. Personal context belongs in
  Hindsight, which the primer surfaces per session. Test fixtures use neutral placeholders
  (`example-user`, `org/repo`, `-var-home-user-…`). `.claude/settings.local.json` is gitignored.
- `dot-claude/CLAUDE.md` is load-bearing and repo-owned: memory tooling and automation must never
  edit the installed copy; changes happen here and are re-applied.

## Load-bearing design decisions

### Memory

- **Retention is per-turn with replace semantics, and self-heals.** Each turn is one document with a
  stable id from `(session_id, prompt_id)` and `update_mode: replace`, so retries are idempotent —
  no watermarks, no append bookkeeping. Turn grouping is positional: user records carry `promptId`,
  assistant records attach to the most recent prompt, and only the last assistant text is kept.
  Because the transcript is flushed asynchronously, a `Stop` can read a turn whose tail is not yet
  on disk: the state stores a content hash per turn, a changed turn is resubmitted, turns inside a
  pending operation wait for it to resolve, and `SessionEnd` is the final catch. Never reintroduce
  a submit-once rule keyed on turn id alone.
- **Memory is the conversation, not tool traffic.** `tool_use`/`tool_result`/`thinking` blocks and
  flagged records (`isMeta`, `isSidechain`, `isCompactSummary`, `isApiErrorMessage`,
  `isVisibleInTranscriptOnly`, `toolUseResult`) are structurally excluded, so file contents and
  command output cannot reach the store; secret regexes redact what remains. State files carry ids
  and timestamps only — never payloads or credentials — at `0700`/`0600`.
- **Entities use stable logical identities.** Documents are tagged and attributed `org/repo` (the
  working directory's last two components, via `stable_project`), never physical paths, which
  changed across machine eras and would fragment the graph. Keep raw `cwd` out of entity-bearing
  text; it belongs in metadata only.
- **Baseline memory is pushed and cached.** Recall-only memory degrades to no memory when the model
  doesn't call it, so `scripts/prime_hindsight.py` (SessionStart) injects a primer. A synchronous
  full-quality recall costs ~8s at session start — latency in the worst place, and it pressures
  recall budget down — so the hook serves a cache (~0.1s) and refreshes detached at `budget=high`
  on SessionStart and SessionEnd under a per-project flock. One session of staleness is the
  deliberate price; the header carries the generation time. Never make a hook wait on the store.
- **Project scoping is client-side, because the server's tag filter is not restrictive.** Retained
  items carry `tags` and `metadata.project` (both verified to persist), but recall's
  `tags`/`tag_groups` were measured non-restrictive here — a nonsense tag returns what a real one
  does. Every recall *result* carries its metadata, so the primer filters the project section
  itself: facts attributed to another project are dropped, unattributed ones kept, and legacy
  path-shaped names must still match via `same_project()`. Re-test the server filter before
  relying on it.
- **The project section cannot come from `reflect`.** Synthesis reconciles the whole bank and
  returns prose, so there is no per-fact metadata to filter and the client-side scoping above has
  nothing to act on; `tags` are non-restrictive on `reflect` as well. Constraining the query to one
  project is not sufficient — answers mix in facts from unrelated repositories. Recall stays the
  source for this section until a restrictive scoping mechanism exists.
- **Gated rules are the bank's directives, verbatim — never a recall.** A recall over rule-shaped
  language cannot separate a standing rule from a fact *about* one, so it returns notes about the
  rules, and about this primer's own construction, ranked among them. Filtering the results is not
  the fix: a regex cannot weigh meaning and discards real rules along with the noise. Directives
  are the curated set, so `render_rules` renders them alone — collapsed to one line but never
  truncated, since the name is the whole rule — and a preference reaches the gate by being promoted
  into one. The cost is deliberate: an unpromoted preference is absent from the gated document
  rather than present alongside noise.
- **An empty fetch and a failed fetch are different facts.** The rules document is deleted when the
  bank genuinely holds no directives, so a fetch that failed must be distinguishable from one that
  returned nothing — `collect_sections` reports `None` against `[]`, and a malformed response raises
  rather than degrading to empty. Conflating them deletes the gate's only copy of the rules on a
  transient network error, and the gate reads an absent document as "no rules apply."
- **Local auto memory is forced off** (`autoMemoryEnabled: false`, enforced on every merge, not
  defaulted). Local fact files fork memory into an unreconciled second store that goes stale
  silently. Never reintroduce a local memory surface.

### Implementation workflow

The workflow's rules and their rationale live in the artifacts themselves — the skills, the coder
and verifier contracts, `references/complexity-tiers.md`, `bin/codex-review` — and are not restated
here; if a rule is unclear from reading its artifact, fix the artifact. The one fact that spans
them: finding discipline (named contracts, concrete failure scenarios, no dead surface), premise
discipline (evidence attached or a recorded blocker, never assumed-by-choice), disclosure
discipline (sign-off covers only its disclosed text; deviations from the ratified design return
for ruling), and the orchestrator's holistic duties are a single system mirrored across
`bin/codex-review`, the implement, design-spec, and codex-plan-review skills, the coder contract,
and `dot-claude/CLAUDE.md`. Relaxing one seat reopens the others — sweep them together or not at
all.

### Installation and repository instructions

- **`apply.sh` refuses foreign paths.** It replaces only symlinks it owns (targets inside this repo)
  and prunes only dangling repo-owned links, so a personal file can never be clobbered by an
  install. Re-running must change nothing.
- **The settings.json merge is surgical.** Repo-owned entries are matched by script path; foreign
  hooks are preserved byte-for-byte; `MAX_MCP_OUTPUT_TOKENS` is added only when absent (large
  recalls need headroom); an unchanged merge rewrites nothing.
- **Adherence is gated, not requested.** Claude Code does not auto-load `AGENTS.md`, and rules that
  merely sit in context get skimmed while rules an agent reads get followed. So
  `scripts/inject_repo_instructions.py` (SessionStart) prints a pointer — path, section headings,
  notice that writes are gated, and the standing-rules document's path when one exists — and
  `scripts/gate_repo_instructions.py` (PreToolUse on the writing tools) denies a write until the
  acting agent has read them. It fires inside subagents too. Every gated document is announced by
  path, never inlined: a pointer keeps the read an act the agent performs, and an agent that learns
  of a gated document only from a denial spends its first write discovering it.
- **Two documents are gated, on different terms.** The repository's `AGENTS.md` must have been read
  complete and current. The standing-rules document (`rules_path()` under the primer cache) is gated
  on *presence* of a read alone, because it is regenerated in the background and an exact-content
  rule would re-gate an agent every time a refresh landed — through no fault of its own. Both expire
  on context growth. When the gate is about to ask for the rules document it first spawns a refresh,
  so the read it prompts returns current memory rather than session-start memory. A project with no
  rules document — no memory store, or a first session — is simply not gated on it.
- **The gate denies; it never allows.** Emitting `permissionDecision: "allow"` auto-approves a
  write and bypasses the normal permission prompt, so passing the gate means printing nothing at
  all. Only a denial produces output.
- **Gate compliance is derived from the transcript, never from marker files.** The transcript is
  the source of truth for what an agent read, it cannot drift, and it leaves nothing to clean up. A
  read of `AGENTS.md` qualifies only when it used `Read` on the file with no `offset`/`limit` key
  present, its result is correlated to that call by `tool_use_id`, and its content matches the file
  exactly, so any edit to `AGENTS.md` re-gates every agent. Read
  numbers every element of the newline split, so a file ending in a newline renders one final
  numbered-but-empty line — the comparison keeps it. The staleness budget bounds the scan: anything
  older is stale regardless, so cost does not grow with session length.
- **The gated repository comes from the file being written**, not from `cwd`; `cwd` only resolves
  relative paths. `transcript_path` inside a subagent names the *parent* session, so the child's
  transcript is derived from `agent_id`, and when that file is absent the gate fails open rather
  than consulting the parent — a parent's read must never satisfy a child.
- **Fail open on every uncertainty**: unreadable transcript or instructions, non-UTF8 content, and
  instruction files longer than a single `Read` can return (an unranged read would be paginated,
  leaving nothing able to satisfy the gate). `CLAUDE_SKIP_AGENTS_GATE=1` disables it outright. A
  gate that can deadlock a session is worse than the problem it solves.

## Verification

Run after any change:

```bash
python3 -m unittest discover -s tests
bash -n apply.sh bin/codex-review
python3 -m py_compile scripts/*.py
```

`.github/workflows/tests.yml` runs exactly these across Python 3.10–3.14 on pushes to `main`,
pull requests, and manual dispatch (3.10 is the floor: the `Transport` alias evaluates a `X | None` union at runtime). Keep
the workflow and this list in step; if a check is worth running locally it is worth running in CI.

For transcript-parser changes, also dry-run against a real session transcript
(`scripts/retain_hindsight.py --dry-run`, see README.md) and confirm: user prose in, tool noise out,
final answers only. For installer changes, run `./apply.sh` twice — the second run must change
nothing. Neither is automatable in CI — both need a real transcript or a real home directory.
