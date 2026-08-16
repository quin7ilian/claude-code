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
- **Repository instructions are enforced.** `AGENTS.md` is not loaded natively by Claude Code, so a
  hook announces it and a write gate requires it — and your standing rules — to have been read.
- **Code navigation is graph-first.** A repository that opts in carries a
  [code-review-graph](https://github.com/tirth8205/code-review-graph) kept current by a background
  watcher; agents and Codex query callers, blast radius, and test coverage from it instead of
  grepping the tree.

## The split

| Role | Model | Where |
|---|---|---|
| Orchestration, design, research synthesis | Session model | main loop |
| Implementation | `coder` / `coder-complex` subagent — model per tier | Task tool |
| Bulk retrieval | `researcher` subagent | Task tool |
| Claim verification | `verifier` subagent | Task tool |
| Code/plan review, second-prior research | Codex (ChatGPT subscription, no API key) | `codex exec`, sandboxed |
| Long-term memory | Hindsight (self-hosted) | MCP + REST hooks |
| Research/design artifacts | Obsidian vault | MCP |

Effort is pinned per subagent definition, since there is no per-invocation override — so an
expensive session never silently spawns expensive subagents:

- Main session: `high`; raise manually for hard design work.
- `coder`: `high` — standard items have no plan and no per-item review, so its own judgment carries
  them.
- `coder-complex`: `xhigh` — where Opus performs at its best on hard work.
- `verifier`: `high` — falsification-grade checks on load-bearing claims before they are ratified
  into a design or relayed as fact.
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

- **Standing rules and preferences** — the bank's directives, verbatim. Directives only: a recall
  over rule-shaped language returns notes *about* the rules as readily as the rules themselves, so a
  preference reaches the gate by being promoted into a directive.
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
and matching legacy path-shaped names. The project section cannot come from `reflect`: synthesis
returns prose with no per-fact provenance to filter, and `reflect`'s tag filter is equally
non-restrictive.

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
- **Fix loops are disciplined** — a fix inherits the tier of the code it touches and lands with a
  pinning test; iterating reviews run as a living-brief loop with a circuit breaker
  ([review-loop.md](dot-claude/skills/implement/references/review-loop.md)); and fix authorship
  escalates to a Codex consult (pair mode) on countable evidence, never as a default.
- **Resume, don't redo** — interrupted runs restart from the spec and working tree.

Codex review runs through [bin/codex-review](bin/codex-review) from an ephemeral scratch workspace
with network access — the repository under review stays kernel-enforced read-only — and ends in a
PASS/NEEDS_CHANGES verdict. An unavailable reviewer is a blocker, never a pass.

## Repository instructions

Claude Code auto-loads `CLAUDE.md` but not `AGENTS.md`, the cross-vendor standard. Enforcement is
layered, so a repository's rules reach every agent that touches it:

- A `SessionStart` hook announces the repo's `AGENTS.md` — path, section headings, and notice that
  writes are gated (skipped when a root `CLAUDE.md` already imports it). It points rather than
  inlines: rules that merely sit in context get skimmed, rules an agent reads get followed.
- A `PreToolUse` gate denies `Edit`/`Write`/`MultiEdit`/`NotebookEdit` until the acting agent has
  read **both** the repository's `AGENTS.md` and its standing-rules document — the primer's rules
  section, materialized to disk so it can be read rather than skimmed. It fires inside subagents too,
  judged against each agent's own transcript, so a parent's read never satisfies a child.
- Subagent contracts read the instruction files as step one.
- Every dispatched brief names them by absolute path and requires a compliance statement back.
- Every Codex review verifies the change against them and reports violations as findings.

### What satisfies the gate

The two documents are judged on different terms.

For **`AGENTS.md`**, a read counts when it used the `Read` tool on the whole file (no
`offset`/`limit`), its result is correlated to that call by `tool_use_id`, its content matches the
file exactly — so editing `AGENTS.md` re-gates everyone — and it is still effectively in context.

For the **standing-rules document**, presence of a read is enough. Requiring an exact content match
would re-gate an agent every time a background refresh landed, through no fault of its own. When the
gate is about to ask for it, a refresh is spawned first, so the read it prompts returns current
memory rather than whatever was recalled at session start. A project with no rules document — no
memory store configured, or a first session — is not gated on it at all.

"Still in context" is measured in **context tokens**, not transcript bytes: tool output inflates a
transcript far more than it occupies the model's context, and it is the context the agent reasons
over. The hook reads the `usage` figures in the transcript, denies once the context has grown more
than 200,000 tokens since the read, and treats compaction as immediately stale — an explicit
compact-summary record, or any dip in context size, means the rules were discarded rather than
merely pushed back.

Evidence is the agent's own transcript — the reads it actually performed, each correlated to its
result. Nothing accumulates on disk, and the record cannot drift out of sync with what happened.

### When it stands aside

The gate fails open wherever it cannot make an honest judgment, because a gate that deadlocks a
session is worse than the problem it solves: no `AGENTS.md`; an unreadable or non-UTF8 transcript;
an unidentifiable write target; instruction files with CRLF endings or too long for one `Read`
(either would make an exact match impossible); a truncated scan window, where a still-current read
may sit just outside it; and a read whose result carried no rendered content, which re-reading
could not turn into proof. `CLAUDE_SKIP_AGENTS_GATE=1` disables it outright.

## Codex skills

`/codex-code-review`, `/codex-plan-review`, `/codex-research`, `/codex-brainstorm` each run one
sandboxed pass from a self-contained brief with a strict output contract, then every finding is
independently verified. At most one pass per task, never chained, user veto absolute — the
per-deliverable gate and pair-mode fix consults inside `/implement` are the deliberate exceptions.

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

### Code graph (optional)

The graph-first navigation activates only in repositories that carry a
[code-review-graph](https://github.com/tirth8205/code-review-graph) database; everywhere else the
instructions are inert. To set it up:

1. `pipx install code-review-graph` — the CLI must be on PATH for the agents and the watcher hook.
2. Add the semantic-search stack into the same venv:
   `pipx runpip code-review-graph install 'sentence-transformers<6,>=3.0.0'`. (Plain
   `pipx inject code-review-graph 'code-review-graph[embeddings]'` resolves the package as already
   satisfied and installs nothing.) This pulls torch — several GB with CUDA wheels — and the watcher
   uses the GPU when one is present. Skipping this step is fine: search degrades to keyword FTS.
3. Opt a repository in: `code-review-graph build && code-review-graph embed` at its root, and add
   `.code-review-graph/` to its `.gitignore`. The first `embed` downloads the `all-MiniLM-L6-v2`
   model (~90 MB) from Hugging Face.
4. Nothing else. The `SessionStart` hook starts a detached background watcher — the graph's only
   writer — that keeps the graph, keyword index, and vectors current within about a second of every
   save, and the review gate verifies freshness before telling Codex the graph exists. The watcher
   is left running between sessions; kill it freely, the next session restarts it after a catch-up.

## Security posture

- This setup registers the Hindsight and Obsidian MCP servers for Claude only; it grants Codex no
  access to either. Codex runs kernel-sandboxed in every pass: writes are confined to an ephemeral
  scratch directory and `/tmp`, so the repository under review stays read-only, while network and
  web access are enabled — a deliberate trade, so briefs must never point it at `.env` files,
  credentials, or key material, and reviewing repositories containing untrusted content is a
  conscious decision.
- Retained memory is conversation-only: tool output is structurally excluded before anything leaves
  the machine, and secret patterns are redacted on top.
- `apply.sh` never echoes tokens; settings and state files are written `0600`.
