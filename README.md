# Claude Code

[![tests](https://github.com/quin7ilian/claude-code/actions/workflows/tests.yml/badge.svg)](https://github.com/quin7ilian/claude-code/actions/workflows/tests.yml)

My Claude Code setup: global guidance, skills, subagents, and session hooks that give an interactive
agent persistent long-term memory (self-hosted **Hindsight**), durable research and design knowledge
(an **Obsidian** vault), a cost-tiered implementation workflow, and a different-prior reviewer
(**Codex**, on the ChatGPT subscription).

Everything is version-controlled so the machine is reproducible. `apply.sh` installs it.

## What it does

- **Hindsight is the only memory store.** Every turn is retained automatically, every session opens
  with a memory primer, and the agent recalls on demand rather than guessing. No local fact files.
- **Obsidian is the knowledge vault.** `/research-note` and `/design-spec` build durable notes under
  `Research/` and `Design/`, patched as decisions land rather than dumped at the end.
- **Work is tiered.** The session model plans, steers, and reviews; subagents on tier-mapped models
  execute and retrieve.
- **Codex is the second prior.** Gated skills for review, research, and ideation — plus the
  mandatory review gate inside the implementation workflow.
- **Repository instructions are enforced**, including `AGENTS.md`, which Claude Code does not load
  natively.

## The split

| Role | Model | Where |
|---|---|---|
| Orchestration, design, research synthesis | Session model | main loop |
| Implementation | `coder` / `coder-complex` subagent — model per tier | Task tool |
| Bulk retrieval | `researcher` subagent | Task tool |
| Code/plan review, second-prior research | Codex (ChatGPT subscription, no API key) | `codex exec`, sandboxed |
| Long-term memory | Hindsight (self-hosted) | MCP + REST hooks |
| Research/design artifacts | Obsidian vault | MCP |

Effort is pinned per subagent definition, since there is no per-invocation override — so an
expensive session never silently spawns expensive subagents:

- Main session: `high`; raise manually for hard design work.
- `coder`: `high` — standard items have no plan and no per-item review, so its own judgment carries
  them.
- `coder-complex`: `xhigh` — where Opus performs at its best on hard work.
- `researcher`: `medium` — retrieval sweeps.

## Memory

**Retention.** A `Stop`/`SessionEnd` hook submits each completed turn to Hindsight as one document:
the user's prompt plus the final assistant answer, secrets redacted, tool traffic and harness noise
excluded. Stable document ids (`claude-turn-<sha256(session, prompt)>`, `update_mode: replace`) make
retries idempotent.

Retention self-heals. The transcript is flushed asynchronously, so a `Stop` can read a turn whose
tail is not yet on disk; the hook stores a content hash per turn and resubmits when content grows,
with `SessionEnd` as the final catch. Submission is asynchronous on a 3-second budget and never
blocks a turn.

**Primer.** A `SessionStart` hook injects baseline memory so it never depends on the model choosing
to recall. It has two sections:

- **Standing rules and preferences** — the bank's directives verbatim, plus a dedicated rules
  recall, so pinned behavior never competes with topical facts for ranking slots.
- **Project context** — scoped to the current project.

The primer is a starting point, not the extent of memory: global guidance also requires a targeted
`mcp__hindsight__recall` whenever an answer could depend on durable facts, prior decisions, or
project history — recall rather than guess.

Serving is a cache read (~0.1s), refreshed detached at full recall budget so quality rises without
session-start latency. The first session in a project misses the cache and builds once
synchronously at low budget before printing. One session of staleness is the deliberate price; the
header carries the generation time.

**Scoping.** Retained turns carry `tags` and `metadata.project` with stable logical identities
(`org/repo` from the working directory, never physical paths, so entities survive machine
migrations). Because recall's server-side tag filter does not currently restrict results, the primer
filters the project section client-side — dropping other projects' facts, keeping unattributed ones,
and matching legacy path-shaped names. Rules recall stays unscoped: a preference stated in one
repository applies everywhere.

**Policy.** Local auto memory is disabled (`autoMemoryEnabled: false`, enforced on every settings
merge) because local fact files go stale silently while Hindsight reconciles server-side. The only
thing kept on disk is the primer cache. Remember requests route to Hindsight; standing behavioral
rules to the repo-owned `CLAUDE.md` or a Hindsight directive; repository facts to that repository's
own instruction file.

## Implementation workflow

`/design-spec` tags every implementation-sequence item with a logical complexity tier — `trivial`,
`standard` (default), or `complex`. Specs never name models: the routing table in
[complexity-tiers.md](dot-claude/skills/implement/references/complexity-tiers.md) translates tiers
into models and efforts, so a model-lineup change is a one-file edit and existing specs stay valid.

`/implement` then orchestrates:

- **Serial dispatch by default** — sustained completion within usage limits beats wall-clock speed.
  Parallel is an explicit per-run request.
- **The orchestrator never types grunt code.** `complex` items get an orchestrator-authored plan
  (invariants + binding stop conditions) executed by a coder, then a conceptual review of the result
  against the plan's intent.
- **Review placed by tier** — deterministic checks always; per-item Codex review for `complex`; one
  batch review of the integrated change-set covering everything, including cross-item interactions.
- **Resume, don't redo** — interrupted runs restart from the spec and working tree.

Codex review runs through [bin/codex-review](bin/codex-review) in a read-only sandbox and ends in a
PASS/NEEDS_CHANGES verdict. An unavailable reviewer is a blocker, never a pass.

## Repository instructions

Claude Code auto-loads `CLAUDE.md` but not `AGENTS.md`, the cross-vendor standard. Enforcement has
four legs, so a repository's rules reach every agent that touches it:

- A `SessionStart` hook injects the repo's `AGENTS.md`, giving it the ambient status `CLAUDE.md` has
  natively (skipped when a root `CLAUDE.md` already imports it).
- Subagent contracts read the instruction files as step one.
- Every dispatched brief names them by absolute path and requires a compliance statement back.
- Every Codex review verifies the change against them and reports violations as findings.

## Codex skills

`/codex-code-review`, `/codex-plan-review`, `/codex-research`, `/codex-brainstorm` each run one
sandboxed pass from a self-contained brief with a strict output contract, then every finding is
independently verified. At most one pass per task, never chained, user veto absolute — the
per-deliverable gate inside `/implement` is the deliberate exception.

## Install

Requires `claude` logged in, OS `python3` (3.10+), and the `codex` CLI logged in via ChatGPT
(`codex login status`) for the review gate and Codex skills.

1. `cp .env.example ~/.claude/.env` and fill in the Hindsight and Obsidian credentials. Optionally
   set `HINDSIGHT_USER_TAG` to tag retained memories with `user:<value>` — useful when a bank holds
   memories from more than one person or agent.
2. Move any personal `~/.claude/CLAUDE.md` aside; the installer refuses to replace files it does not
   own.
3. `./apply.sh` — symlinks guidance, skills, agents, and hooks; registers the `hindsight` and
   `obsidian` MCP servers (user scope); merges the session hooks into `~/.claude/settings.json`.
   Re-running is always safe.
4. Restart Claude Code sessions.

## Security posture

- Codex never receives Hindsight or Obsidian access — those MCP connections are Claude-only. It runs
  kernel-sandboxed: read-only for reviews, writes confined to an ephemeral scratch directory for
  research passes. Briefs must never point it at `.env` files, credentials, or key material.
- Retained memory is conversation-only: tool output is structurally excluded before anything leaves
  the machine, and secret patterns are redacted on top.
- `apply.sh` never echoes tokens; settings and state files are written `0600`.
