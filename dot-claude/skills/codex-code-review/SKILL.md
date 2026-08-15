---
name: codex-code-review
description: Use Codex for one focused, late-stage different-model review of a completed code change. Invoke only when the user explicitly requests Codex review, or when global guidance authorizes final review of a consequential implementation with material residual risk; do not invoke for routine changes, during implementation, after a Codex pass already ran, or when the user declined Codex.
---

# Review code changes with Codex

Use Codex as a skeptical reviewer, then independently verify its findings. Keep the review centered
on the change rather than asking Codex to inventory the repository.

## Confirm the consultation gate

Proceed only when the user explicitly requested Codex review or global guidance authorizes a final
review of a completed consequential change. Stop and review natively if the user declined Codex, the
implementation or relevant tests are incomplete, the change is routine, or any Codex skill already
ran for this task. Use one Codex pass and never chain into another Codex skill; only the user may
request a follow-up pass. (Inside the `implement` workflow, coder subagents run this review per
deliverable under their own contract — that gate is separate and does not use this skill.)

## Establish the review boundary

1. Identify the repository root and the exact change set.
   - Default to staged and unstaged changes for work completed in the current task.
   - Use the user-specified ref, commit, or comparison range when provided.
   - State an explicit range for committed branch work; do not let Codex guess a base branch.
2. Extract a compact statement of the user's request, specification, acceptance criteria,
   constraints, and decisions from the conversation. Codex cannot see the conversation.
3. Point to the repository and change range. Do not paste a large diff or whole files into the
   brief; Codex can read them directly.
4. Exclude secrets. Never name or direct Codex to `.env` files, credentials, private keys,
   `~/.ssh`, or unrelated personal directories.

Before consulting Codex, inspect `git status --short`, the relevant diff stat, and applicable
repository instruction files yourself. If no change set exists, stop and explain what is missing.

## Write a compact brief

Write the brief to a temporary Markdown file. Include:

- the task and intended behavior;
- the specification and acceptance criteria, including any explicitly out-of-scope behavior;
- the exact diff/range to review;
- the absolute paths of the repository's instruction files (`AGENTS.md`, `CLAUDE.md`, and any
  covering the touched directories) — Codex must verify the change against them and report
  violations as findings;
- any assumptions or risks that deserve pressure-testing;
- absolute paths only when the target is outside the review root.

Do not append a reviewer contract — `codex-review` adds the canonical contract itself (skeptical,
evidence-driven, at most 8 high-confidence findings with severity/file:line/evidence/fix, ending in
a `verdict: PASS` or `verdict: NEEDS_CHANGES`).

## Run the review

```bash
codex-review \
  --brief "/absolute/path/to/codex-code-review-brief.md" \
  --repo "/absolute/path/to/repository" \
  --out "/absolute/path/to/codex-code-review.md"
```

Codex runs in a kernel-enforced read-only sandbox and inherits the user's configured model and
reasoning effort. If `codex-review` exits non-zero (Codex missing, unauthenticated, or failed), show
the concise error and continue with your own review. Never treat an unavailable reviewer as a pass.

## Verify and respond

Read the raw review exactly once. For every finding:

1. Reproduce or inspect the cited evidence yourself.
2. Accept, reject, or narrow the finding explicitly; Codex is advice, not an authority.
3. If the active request includes implementation, fix accepted findings and rerun the most relevant
   checks. Do not run another Codex pass unless the user explicitly requests it.
4. Present each Codex point beside your verdict and action, with its concrete scenario — when it
   occurs, when it does not, and its observable effect, in plain terms rather than the reviewer's
   shorthand. Do not silently drop or soften findings.

Give the user the raw review file path, the paired assessment, the final verdict, and verified test
results. Keep unverified concerns clearly labeled.
