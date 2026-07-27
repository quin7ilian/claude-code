# AGENTS.md — working in the `claude-code` repo

Orientation for an agent editing this repo. Pairs with `README.md` (user-facing overview). When code
and this file disagree, the code wins — fix this file.

## What this repo is

A personal Claude Code setup: global guidance (`dot-claude/CLAUDE.md`), skills, subagent
definitions, a Codex review-gate wrapper, and the session hooks that carry memory and repository
instructions. `apply.sh` installs it (ownership-checked symlinks, MCP registration, settings merge).
Hindsight is the long-term memory; Obsidian is the research/design vault; Codex is the only external
model.

## Conventions

- **Skills** live in `dot-claude/skills/<name>/SKILL.md` with `name` and `description` frontmatter.
  Keep the invocation gate inside the description (explicit-invocation skills say so there). Skills
  never select a model or reasoning effort.
- **Subagents** live in `dot-claude/agents/<name>.md`. Pin `model` and `effort` in frontmatter —
  unpinned subagents inherit the session effort, letting an expensive session silently spawn
  expensive subagents. Subagent bodies are contracts: self-contained briefs in, compact summaries
  out, never raw logs.
- **Codex invocations** are non-interactive (`</dev/null`), sandboxed (`--sandbox read-only` for
  reviews; `--sandbox workspace-write` with an ephemeral scratch `-C` for passes needing
  web/network), and never pass model or effort flags — Codex inherits the user's own configuration.
  Point Codex at files by absolute path instead of pasting large artifacts; never at secret-bearing
  paths.
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
  path-shaped names must still match via `same_project()`. Rules recall stays deliberately
  unscoped — a preference stated in one repository applies everywhere, and losing a real standing
  rule is worse than a little cross-project bleed. Re-test the server filter before relying on it.
- **Local auto memory is forced off** (`autoMemoryEnabled: false`, enforced on every merge, not
  defaulted). Local fact files fork memory into an unreconciled second store that goes stale
  silently. Never reintroduce a local memory surface.

### Implementation workflow

- **The orchestrator's model plans and reviews; it never types grunt code.** `complex` items are
  executed by the coder model against an orchestrator-authored plan carrying invariants and binding
  stop conditions, then conceptually reviewed by the orchestrator against the plan's intent — codex
  review checks correctness against the brief and cannot judge design intent it never saw.
- **Sustained completion beats wall-clock.** Coders dispatch serially by default: parallel bursts
  concentrate burn into one usage window, and a limit hit then strands several agents whose re-runs
  waste real tokens (measured: one 26-dispatch run hit three windows and rebuilt ~2.5M cache tokens
  resuming stranded agents). Parallel dispatch is an explicit per-run user request.
- **Tier policy has one home**, but two facts about it are load-bearing here: effort must be pinned
  per subagent definition because the Task tool has no per-invocation effort override (verified
  against sub-agents.md), and `coder-complex` is a thin overlay that reads `coder.md` at runtime —
  exactly one coder contract, never forked. Under-efforting execution is false economy: a shallow
  item that fails batch review costs more than the thinking would have.
- **The review gate fails loud, never silently passes.** `bin/codex-review` exits non-zero on a
  missing, failed, or empty review, and both the coder contract and the skills state that an
  unavailable reviewer is a blocker, not a pass.

### Installation and repository instructions

- **`apply.sh` refuses foreign paths.** It replaces only symlinks it owns (targets inside this repo)
  and prunes only dangling repo-owned links, so a personal file can never be clobbered by an
  install. Re-running must change nothing.
- **The settings.json merge is surgical.** Repo-owned entries are matched by script path; foreign
  hooks are preserved byte-for-byte; `MAX_MCP_OUTPUT_TOKENS` is added only when absent (large
  recalls need headroom); an unchanged merge rewrites nothing.
- **`AGENTS.md` adherence is enforced mechanically.** Claude Code auto-loads `CLAUDE.md` but not
  `AGENTS.md`, so agents were told to follow a file they never received — the failure was absence,
  not disobedience. `scripts/inject_repo_instructions.py` (SessionStart) prints the repo's
  `AGENTS.md` into context, skipping when a root `CLAUDE.md` already imports it. Subagents get no
  hooks, so the same requirement lives in their contracts and in every brief, and Codex reviewers
  must emit a compliance section. Never weaken any leg: prose alone demonstrably failed.

## Verification

Run after any change:

```bash
python3 -m unittest discover -s tests
bash -n apply.sh bin/codex-review
python3 -m py_compile scripts/*.py
```

For transcript-parser changes, also dry-run against a real session transcript
(`scripts/retain_hindsight.py --dry-run`, see README.md) and confirm: user prose in, tool noise out,
final answers only. For installer changes, run `./apply.sh` twice — the second run must change
nothing.
