---
name: codex-plan-review
description: Use Codex for one thorough, late-stage review of a complete consequential implementation, migration, architecture, or delivery plan before execution. Invoke only when the user explicitly requests Codex review, or when global guidance authorizes final review of a consequential plan; do not invoke during initial planning, for routine work, after execution starts, after another Codex pass, or when the user declined Codex.
---

# Review a plan with Codex

Use Codex as a skeptical plan reviewer with enough repository and web access to test the plan's
claims. Review the proposed work before implementation; do not reduce this to prose critique or
assume that named libraries and APIs behave as the plan claims.

## Confirm the consultation gate

Proceed only when the user explicitly requested Codex review or global guidance authorizes final
review of a complete consequential plan before execution. Stop and review natively if the user
declined Codex, the plan is still being formed, the work is routine, execution has begun, or any
Codex skill already ran for this task. Use one Codex pass and never chain into another Codex skill;
only the user may request a follow-up pass.

## Assemble the review evidence

Write a focused, self-contained brief to a temporary Markdown file containing:

- the complete plan, copied faithfully or referenced by absolute path;
- the user's goal, specification, acceptance criteria, constraints, non-goals, and rollout
  expectations;
- decisions already made and alternatives already rejected, with reasons;
- known uncertainties and research claims embedded in the plan;
- the absolute repository root and any external artifacts Codex should inspect;
- exclusions, especially secret-bearing paths.

Codex cannot see the conversation. Preserve important nuance rather than summarizing the plan into a
strawman.

## Require a broad, evidence-driven review

End the brief with this contract:

```text
Act as a skeptical, exhaustive plan reviewer. Determine whether this plan is correct, complete,
feasible, efficiently sequenced, and likely to satisfy the stated specification and acceptance
criteria. Challenge every load-bearing assumption and research claim; do not accept plausible
language as evidence.

Inspect the broader repository before judging. Read all applicable AGENTS.md/CLAUDE.md instruction
files first — they are binding, and a plan step that violates them is a finding regardless of its
technical merit. Then map the relevant architecture and ownership boundaries, search for existing
patterns and canonical helpers, trace affected callers/consumers and adjacent systems, inspect
relevant tests and operational configuration, and identify interactions the plan omitted. Explore as
broadly as the plan's blast radius requires rather than limiting review to files named in the plan.

Validate every material library or platform claim. Establish the exact dependency version from
manifests and lockfiles. Then inspect installed source, version-matched upstream source, or primary
official documentation to confirm APIs, semantics, defaults, lifecycle, compatibility, limitations,
failure behavior, concurrency/thread-safety, performance, security, and deprecations relevant to the
plan. Fetch and read sources rather than relying on search snippets or training recall. Cite the
version and direct URL/file path for each conclusion. If version-matched evidence is unavailable,
label the claim unverified instead of guessing.

Pressure-test requirement coverage, scope boundaries, prerequisites, ordering, dependencies,
parallelism, data/state migrations, backward and forward compatibility, partial-failure behavior,
idempotency, rollout, observability, rollback/recovery, testing strategy, acceptance verification,
and maintainability. Identify simpler or safer alternatives when they materially improve the plan;
do not bikeshed equivalent choices.

Continue until every plan step, acceptance criterion, and load-bearing assumption has been examined
or a specific evidence gap is recorded. Do not optimize for speed, brevity, or a fixed number of
findings. Never modify the repository and never read secrets, credentials, .env files, private keys,
or ~/.ssh.

Output:
1. Verdict: READY, REVISE, or BLOCKED, with rationale.
2. Requirement and acceptance-criteria coverage matrix mapped to plan steps.
3. Findings ordered by impact, each with evidence, consequence, and concrete plan change.
4. Assumption ledger tagged VERIFIED, DISPROVED, or UNVERIFIED, with sources.
5. Repository and dependency/library evidence inspected, including every AGENTS.md/CLAUDE.md file
   read by path and whether the plan complies with the rules it engages.
6. Missing tests, validation, rollout, observability, and rollback work.
7. A revised sequence or alternative approach where warranted.
8. Remaining questions and evidence gaps that must be resolved before execution.
Do not rewrite the whole plan merely for style and do not invent findings to appear thorough.
```

## Run the review

Run Codex from an ephemeral scratch directory: the plan reviewer needs to read the repository and
fetch live sources, while its writes stay confined to the throwaway scratch. Codex inherits the
user's configured model and reasoning effort; pass no model or effort flags. Reference the
repository by absolute path in the brief.

```bash
# Create the brief and scratch directory first, then substitute concrete absolute paths.
SCRATCH="$(mktemp -d)"
codex exec --skip-git-repo-check \
  --sandbox workspace-write \
  -c sandbox_workspace_write.network_access=true \
  -c web_search=live \
  -C "$SCRATCH" \
  "$(cat "/absolute/path/to/codex-plan-review-brief.md")" </dev/null \
  >"/absolute/path/to/codex-plan-review.md" \
  2>"/absolute/path/to/codex-plan-review.stderr"
```

Wait for the complete run. Fill thin areas with your own native inspection and research; do not
start a second Codex pass unless the user explicitly requests it. If Codex is unavailable, report
that and perform the full plan review yourself.

## Verify and incorporate the review

Treat Codex's report as independent analysis, not authority.

1. Reproduce the repository evidence and open the primary sources behind every finding that would
   change the plan.
2. Research disputed library behavior or architecture claims yourself, using the exact dependency
   version.
3. Accept, reject, narrow, or defer each material finding with a reason.
4. Revise the active plan to incorporate accepted findings, including missing validation and
   rollback steps.
5. Recheck the revised plan for requirement coverage and internal consistency yourself; do not rerun
   Codex unless the user explicitly requests it.

Give the user the raw Codex report path, a faithful finding-by-finding assessment pairing each Codex
point with your verdict, the revised plan or concrete amendments, verified sources, and the final
readiness verdict.
