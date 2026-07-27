# claude-code

My Claude Code setup: global guidance, skills, subagents, and automatic memory retention that give
an interactive Claude Code agent persistent long-term memory (self-hosted **Hindsight**), durable
research and design knowledge (an **Obsidian** vault), a cost-tiered implementation workflow, and an
exceptional different-prior reviewer (**Codex**, on the ChatGPT subscription).

Everything is version-controlled so the machine is reproducible. `apply.sh` installs it.

## What it does

- **Hindsight is the only memory.** Global guidance makes recall part of the normal lifecycle:
  before answering anything that could depend on durable facts, prior decisions, or project history,
  the agent calls `recall` — it does not guess. A `Stop` hook automatically retains every completed
  turn (user prompt + final answer, secrets redacted, tool traffic excluded) to the Hindsight bank
  as a per-turn document, asynchronously and fail-open. A `SessionStart` hook injects a
  project-scoped memory primer into every session's opening context, so baseline memory is pushed —
  it never depends on the model choosing to recall. The primer is served from a local cache
  (~0.1s) and refreshed in a detached background process at Hindsight's full recall budget, so
  session start pays no latency while memory quality goes up. Documents carry stable logical
  project identities (`org/repo` from the working directory's last two components), never physical
  paths, so entities survive machine and OS migrations. Local auto memory is disabled by policy
  (`autoMemoryEnabled: false`, enforced by the settings merge): local fact files go stale silently,
  while Hindsight reconciles old memories against new facts server-side. "Remember this" routes to
  Hindsight; standing rules route to the repo-owned CLAUDE.md; repo facts belong in that repo's own
  CLAUDE.md as documentation.
- **Obsidian is the knowledge vault.** `/research-note` builds source-grounded research under
  `Research/`; `/design-spec` develops implementation-ready specifications under `Design/`. Both
  are write-through workflows: the note is the canonical working context, patched as decisions land,
  not dumped at the end.
- **Implementation is cost-tiered.** `/design-spec` tags every implementation-sequence item with a
  logical complexity tier — `trivial`, `standard` (default), `complex`. Specs never name models; the
  routing table in `skills/implement/references/complexity-tiers.md` translates tiers into models
  (currently `sonnet`/`opus`), so a model-lineup change is a one-file edit and every
  existing spec stays valid. `/implement` dispatches items serially by default (sustained
  completion within usage limits beats wall-clock speed) to a `coder` subagent on the mapped model.
  The orchestrator's model never types grunt code: `complex` items get an orchestrator-authored
  implementation plan (invariants + stop conditions) executed by the coder, then an orchestrator
  conceptual review of the result against the plan's intent. **Codex review** (`bin/codex-review`,
  read-only sandbox, PASS/NEEDS_CHANGES verdict) is placed by tier: deterministic checks always;
  per-item review-to-PASS for `complex` items; and one batch review of the integrated change-set
  covering everything, including cross-item interactions (split into clusters when the diff is
  large). Interrupted runs resume from the spec and working tree — never redo work that is already
  on disk.
- **Retrieval is delegated.** A `researcher` subagent (Sonnet, medium effort) runs read-heavy
  web/repo sweeps and returns compact evidence memos, so bulk retrieval never floods the
  orchestrator's context.
- **Repository instructions are enforced, not hoped for.** Claude Code auto-loads `CLAUDE.md` but
  not `AGENTS.md` (the cross-vendor standard), so repositories that use `AGENTS.md` were starting
  every session with their rules absent. A `SessionStart` hook injects the repo's `AGENTS.md` into
  context, giving it the same ambient status `CLAUDE.md` gets natively (skipped when a root
  `CLAUDE.md` already `@AGENTS.md`-imports it). On top of that: every subagent contract reads the
  instruction files as step one, every dispatched brief names them by absolute path and requires a
  compliance statement back, and every Codex review verifies the change against them and reports
  violations as findings.
- **Codex is the exceptional second prior.** Four gated skills — `/codex-code-review`,
  `/codex-plan-review`, `/codex-research`, `/codex-brainstorm` — run one sandboxed Codex pass with a
  self-contained brief and a strict output contract, then independently verify every finding. At
  most one pass per task, never chained, user veto absolute. (The per-deliverable review gate inside
  `/implement` is the deliberate exception.)

## The split (who does what)

| Role | Model | Where |
|---|---|---|
| Orchestration, design, research synthesis | Session model (Fable) | main loop |
| Implementation grunt work | `coder` subagent — model mapped from the item's tier (complexity-tiers.md) | Task tool |
| Bulk retrieval | `researcher` subagent — `sonnet`, medium effort | Task tool |
| Code/plan review, second-prior research & ideation | Codex (ChatGPT subscription, no API key) | `codex exec`, sandboxed |
| Long-term memory | Hindsight (self-hosted) | MCP + REST retention hook |
| Research/design artifacts | Obsidian vault | MCP |

Effort policy: run the main session at `high`; bump to `xhigh`/`max` manually only for genuinely
hard design sessions. Subagents pin their own effort in frontmatter — there is no per-invocation
effort override — so an expensive session never silently spawns expensive subagents: `coder` runs
`high` (standard items have no plan or per-item review, so the coder's own judgment carries them),
`coder-complex` runs `xhigh` for complex-tier items, where Opus performs at its best, and
`researcher` runs `medium` for retrieval sweeps.

## Layout

```
apply.sh                      installer (idempotent; ownership-checked symlinks)
.env.example                  → ~/.claude/.env (Hindsight + Obsidian credentials)
bin/codex-review              Codex code-review gate wrapper (read-only sandbox)
dot-claude/CLAUDE.md          → ~/.claude/CLAUDE.md (global guidance; repo-owned, protected)
dot-claude/agents/            coder.md, researcher.md (subagent definitions)
dot-claude/skills/            design-spec, research-note, implement (+ complexity-tiers),
                              codex-code-review, codex-plan-review, codex-research, codex-brainstorm
scripts/retain_hindsight.py   Stop/SessionEnd hook: per-turn retention to Hindsight (stdlib only)
scripts/prime_hindsight.py    SessionStart hook: cached memory primer + background refresh
scripts/inject_repo_instructions.py  SessionStart hook: injects the repo's AGENTS.md into context
scripts/configure_settings.py settings.json merge (hooks + env + auto-memory off), idempotent
tests/                        unittest suites for the retention hook and settings merge
```

## Install

1. `cp .env.example ~/.claude/.env` and fill in the Hindsight and Obsidian credentials. Optionally
   set `HINDSIGHT_USER_TAG` to tag retained memories with `user:<value>` — useful when a bank holds
   memories from more than one person or agent; leave it empty for a single-user bank.
2. If a personal `~/.claude/CLAUDE.md` exists, move it aside (e.g. `CLAUDE.md.pre-rewrite`) — the
   installer refuses to replace files it does not own, and this repo's `CLAUDE.md` replaces the
   role of any previous SYSTEM/SOUL/USER/MEMORY file split.
3. `./apply.sh` — symlinks guidance, skills, agents, and the hook scripts; registers the `hindsight`
   and `obsidian` MCP servers (user scope); merges the session hooks into
   `~/.claude/settings.json`. Re-running is always safe.
4. Restart Claude Code sessions.

Requires: `claude` logged in, OS `python3`, and the `codex` CLI logged in via ChatGPT
(`codex login status`) for the review gate and codex skills.

## Retention details

The retention hook (`~/.claude/hooks/retain_hindsight.py`, registered for `Stop` and `SessionEnd`)
parses the session transcript, groups records into turns by prompt id, and submits each turn as
`[{role: user, ...}, {role: assistant, ...}]` — the user's actual prompt(s) plus only the final
assistant answer. Tool calls/results, thinking, progress commentary, command echoes, and harness
notifications are excluded; secrets are redacted. Documents use stable ids
(`claude-turn-<sha256(session, prompt)>`, `update_mode: replace`) so retries never duplicate.

Retention is self-healing: the transcript is flushed asynchronously, so a `Stop` firing can observe
a turn before its final records are on disk. The hook stores a content hash per submitted turn and
resubmits any turn whose content has since grown — the replace-mode document converges to the full
turn on the next firing (`SessionEnd` is the final catch for a session's last turn). Submission is
asynchronous with a 3-second budget and never blocks the turn; per-session state under
`~/.claude/hindsight-retention/` tracks accepted operations and confirms, retries, or resubmits
them on later firings.

Validate the parser against a real session without writing anything:

```bash
printf '{"hook_event_name":"Stop","session_id":"S","transcript_path":"%s","cwd":"/tmp"}' \
  ~/.claude/projects/<project>/<session>.jsonl \
  | python3 scripts/retain_hindsight.py --dry-run
```

## Primer details

`SessionStart` prints the cached primer for the current project and spawns a detached refresh;
`SessionEnd` spawns a refresh too, so the cache reflects the session that just ended. A cache miss
(first session in a project) builds once synchronously at low recall budget, then upgrades in the
background. Refreshes hold a per-project lock, so concurrent sessions never stampede the store.

The primer has two sections: **standing rules and preferences** — the bank's active directives
fetched verbatim plus a dedicated rules recall, so pinned behavior never competes with topical
facts for ranking slots — and **project context**. Known bookkeeping-noise shapes are filtered, and
the header carries the generation timestamp so a session knows the age of what it holds.

Retained turns are tagged (`user:*`, `source:claude-code`, `project:<stable>`, `session:*`) and
carry `metadata.project`. Because recall's server-side tag filter does not currently restrict
results, the primer scopes the project section client-side from each result's metadata — dropping
facts belonging to another project while keeping unattributed ones, and matching legacy
path-shaped project names against the stable identity. Rules recall stays unscoped: a preference
stated in one repository applies everywhere.

```bash
# See what a session would receive, and time it
printf '{"hook_event_name":"SessionStart","session_id":"x","cwd":"%s"}' "$PWD" \
  | python3 scripts/prime_hindsight.py --env-file ~/.claude/.env

# Force a synchronous full-budget rebuild for one project
python3 scripts/prime_hindsight.py --refresh --cwd "$PWD" --env-file ~/.claude/.env
```

## Security posture

- Codex never receives Hindsight or Obsidian access — those MCP connections are Claude-only. Codex
  runs kernel-sandboxed: read-only for reviews, or writes confined to an ephemeral scratch directory
  for research passes. Briefs must never point it at `.env` files, credentials, or key material.
- Retained memory is conversation-only: tool output (file contents, command output) is structurally
  excluded before anything leaves the machine, and secret patterns are redacted on top.
- `apply.sh` never echoes tokens; the settings and state files are written `0600`.

## Verification

```bash
python3 -m unittest discover -s tests
bash -n apply.sh
python3 -m py_compile scripts/retain_hindsight.py scripts/configure_settings.py
./apply.sh && ./apply.sh   # idempotent: second run changes nothing
```
