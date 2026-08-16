# Review loops

Protocol for any Codex review that returns NEEDS_CHANGES and enters a fix round — the
per-item gate, the batch review, or an ad-hoc review outside the workflow. A review that
passes first time needs none of this; the moment a loop starts, run it as written. An
undisciplined loop converges slowly or not at all: fixes written hot against the last
round's findings are how the next round's findings get manufactured.

## Loop discipline

- **A reviewed baseline and a minimal diff.** The brief names the baseline commit/state
  and the exact diff artifact, regenerated every round. If the work has drifted through
  partial attempts, reset to the last reviewed state and re-derive the smallest diff
  before looping further — review depth is spent on surface, so surface is the first
  thing to shrink.
- **One living brief**, updated between rounds and re-sent whole. Adjudications
  accumulate in it; a fresh prompt per round throws them away and invites re-litigated
  findings.
- **A unique output file per round.** Concurrent runs on one path interleave and corrupt
  both.
- **Fixes route by tier** (`complexity-tiers.md`): a fix inherits the tier of the code it
  touches and is dispatched to a fresh agent window with the invariant ledger in its
  brief — never authored inline from a long session whose context has been compacted or
  polluted.
- **A fix that changes design is a deviation, not a fix.** A fix brief introducing a
  mechanism-altitude element the ratified design does not carry — a new surface or
  artifact, a behavioral change (what is refused, fabricated, deferred, conceded), a
  workaround, a limitation — goes through the implement skill's deviation gate before
  dispatch: disclosed with its concrete example, ruled or parked. Only a fix restoring
  already-ratified behavior dispatches without a ruling.

## The living brief

1. **Scope**: baseline, the diff artifact's path, and what is explicitly out of scope.
2. **Design intent and the invariant ledger** — the change's load-bearing invariants,
   stated as review dimensions to audit tree-wide in both directions (violated where
   present; missing where required), every round. A finding that exposes a load-bearing
   invariant the ledger did not yet name adds it: the ledger grows by adjudication, not
   by anticipation, and the next round audits the new entry like any other.
3. **Adjudications** — every prior finding filed under exactly one class, by the owner:
   - **Fixed** — with its pinning test; the reviewer judges the current code, not the
     old description.
   - **Accepted** — the owner takes the cost knowingly; do not re-report.
   - **Rejected — do not re-propose** — unless required for correctness of what is here,
     with a concrete failure sequence; that goes back to the owner. A finding whose
     premise was invented — no citable spec, repository-instruction, or
     language/framework contract, only the current use-case — is filed here with that
     basis stated.
   - **Escalated** — pre-existing defect outside this change-set; report only an aspect
     the description misses or a way the change worsens it.
4. The instruction that silence is an answer: "no findings" must be stated explicitly.

## Convergence

- Every fix lands with its pinning test, per `complexity-tiers.md`.
- **Re-reviews cover the fix delta plus the full invariant ledger tree-wide.** A
  delta-only re-review is exactly how a local fix that violates a global invariant
  escapes to the next round.
- **Circuit breaker**: when two consecutive rounds each contain a regression introduced
  by the previous round's fixes, stop the loop. Step back with the user — is the baseline
  right, is the diff still minimal, is the design itself the problem — and pair-author
  the remaining findings.
- A loop that reaches its round limit returns with unresolved findings explicitly
  flagged, never silently softened.

## Pair-mode consults

Consult-then-apply: Codex proposes the patch, a Claude agent applies, tests, and gates
it. Codex never writes the tree.

The consult brief opens "working session, not a review — give me the patch" and carries:
the finding; the constraints in priority order; every prior failed attempt and why it was
wrong; the invariant ledger; pointers to the repository discipline the patch must match;
and the repository's instruction files by absolute path, to be read first. Point at files
rather than pasting artifacts; never name `.env` files, credentials, or key material.

Run it like a review — non-interactive, no model or effort flags, a unique output path,
an ephemeral scratch as the writable workspace so the repository stays kernel-enforced
read-only:

```bash
SCRATCH="$(mktemp -d)"
codex exec --skip-git-repo-check --sandbox workspace-write \
  -c sandbox_workspace_write.network_access=true \
  -c web_search=live \
  -C "$SCRATCH" \
  "$(cat consult-brief.md)" </dev/null > consult-N.md 2> consult-N.stderr
```

The brief names the repository by absolute path — the working directory is the scratch,
not the repo.

An empty or failed consult is a blocker, not an answer. Apply the returned patch with the
normal editing tools, run the pinning test and the relevant suite, then re-review. The
patch is untrusted advice: it lands because it survived verification, not because the
reviewer wrote it.
