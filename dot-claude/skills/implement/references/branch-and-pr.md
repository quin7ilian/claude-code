# Branch and PR delivery

The implement workflow's git delivery protocol: every run executes on a dedicated branch
off the target branch, the orchestrator commits each work item at the moment its gate
closes, every commit is pushed to a draft PR whose templated body is regenerated from the
design spec, CI failures wake the orchestrator into the standard fix discipline, and the
PR leaves draft only after the batch codex review of the merge-base diff reaches PASS.
The protocol is the orchestrator's alone; coder subagents never run git write operations.

Tiering, review placement, and the fix rules this protocol routes into live in
`complexity-tiers.md` and `review-loop.md` — cited here, never restated.

## Branch lifecycle

The run's first git act is observation: tree state, current branch, target branch. The
target is the repository's default branch unless the user names another.

Refs do not self-update, so the observation refreshes the target ref from its configured
remote before anything reads the target head: `git fetch <remote> <target>`, where
`<remote>` is the remote the target's upstream configuration names, `origin` when it
names none. After this observation, the protocol's `<target-ref>` is `<remote>/<target>`,
the remote-tracking ref the fetch advances; on the no-remote degradation rung,
`<target-ref>` is the local `<target>` branch. Every later use of the target — creating
the run's branch from its head, deciding whether it moved, the merge-base diff — is
against `<target-ref>`. No remote, or a fetch refused, drops to the degradation ladder
below.

A branch whose name matches the spec's deterministic slug is this protocol's own for this
spec: the run resumes it together with its open draft PR, and no new branch or PR is
created. Otherwise a clean tree gets a new `<type>/<slug>` branch from `<target-ref>`,
where `<type>` is `fix` iff the spec's goal is correcting defective behavior and `feat`
otherwise — chosen at decomposition and named in the decomposition report before any git
action.

A fresh start with any `git status --porcelain` output, tracked or untracked, stops the
run for the user's ruling before any branch, stage, or commit action: those changes are
not the workflow's to stage, and the first commit under the override must never absorb
them. A resume onto the protocol's own branch inspects the tree instead of stopping, per
Resume below.

## Commit protocol

The commit is the orchestrator's acceptance act, never the coder's completion act. When
an item's gate closes — deterministic checks green, the tier's review (if any) done, the
summary accepted — the orchestrator stages exactly the item's file scope: the files the
brief named, checked against the coder's reported list and `git status`. A touched file
outside that scope halts the item for the orchestrator's judgment instead of being
staged. Until the gate closes a returned item stays uncommitted, so a stranded coder's
work remains inspectable as a dirty tree for resume.

The push happens in the same acceptance operation, before the next dispatch. Coder
subagents never run git write operations, and every dispatch brief says so.

Pushed history is immutable: no amend, no rebase, no force-push. Fix rounds land as new
commits, and every pushed head SHA is recorded in the run report.

## Commit message contract

Subject `<type>(<scope>): <item summary>`, scope optional. The body carries the work
item id, which the PR's Implementation sequence checklist resolves:

```
Ref: W-<n>
```

No attribution trailer, no PR attribution line, no session link — attribution is removed
globally by the `attribution` settings key, installed add-when-absent, so a user-tuned
value wins and is not a violation.

## Draft PR and body regeneration

The draft PR opens at the first push, since a PR needs a commit ahead of the target:
`gh pr create --draft --title … --body-file …`.

Its body is always an instantiation of the template below — never a document maintained
in its own right — regenerated whole with `gh pr edit --body-file …` at exactly four
checkpoints:

1. PR creation.
2. A spec amendment ruled through the deviation gate.
3. Each item landing.
4. The undraft step.

Checkbox state is recomputed from which items have landed commits on the branch, never
preserved by hand. That makes regeneration idempotent and the branch the source of truth
for progress: an item that landed and was later dropped by amendment stays listed and
checked, because its commit is in the branch.

The body never mentions the design spec — no title, no vault path — and carries no tier
vocabulary. The spec is the body's source, never its subject.

## PR body template

```markdown
## Summary

<One to three sentences: what is delivered and why, at reader altitude.>

<Every further part of the delivery is a one-line bullet — grouped under ### subheaders
only when the groups are real:>

- <part — one line>
- <part — one line>

## Implementation sequence

- [ ] W-1 — <item summary>
- [ ] W-2 — <item summary>

## Verification

- <check command> — <outcome>
- <check command> — <outcome>

## Breaking changes

None
```

*Summary*: opens with at most three sentences of what and why; every further part of the
delivery is a one-line bullet, grouped under `###` subheaders only when the groups are
real — never a prose enumeration of mechanisms.
*Implementation sequence*: one checkbox per work item, state derived from landed commits.
*Verification*: each deterministic check named with its outcome, one line per check —
never pasted logs. *Breaking changes*: each break with its observable effect, traceable
to the spec or a decision-log ruling; the literal `None` when there are none. Absence of
the section is illegal.

## CI watch

After each push the orchestrator watches the PR's checks in the background with
`gh pr checks --watch --fail-fast` and ends its turn; a completed failure wakes it.

The response is root-cause verification first: one rerun distinguishes a flake. A second
identical failure, or one reproducible locally, is a defect, and a defect enters a fix
round per `review-loop.md`.

The watch dies with the session, so a failure that lands after the turn ends is reported
by nothing — which is why every resume re-checks CI itself.

## Resume

The branch and its PR are the run's checkpoint. On the protocol's own branch, before
re-dispatching anything, a resume reads:

1. `git log` on the branch — which items have landed as commits.
2. `git status` — a stranded coder's work is usually still on disk, so here a dirty tree
   is something to inspect and brief a resume against, never a stop condition.
3. The PR checklist — the run's progress as the body last rendered it.
4. The pushed head's CI state (`gh pr checks`) — the only report of a failure that
   arrived while the session was gone.

## Completion and the final review

After the last item lands: the conformance sweep, then `git fetch <remote> <target>`
again. The moved-or-not decision is made against `<target-ref>` after that fetch — a
stale ref reports a moved target as unmoved — and if it moved, `<target-ref>` is merged
into the branch (never rebase), resolved, and the deterministic checks re-run. A push
rejected as non-fast-forward is answered the same way: fetch and merge `<target-ref>`,
never force.

The batch codex review then runs on the merge-base diff against `<target-ref>`,
`git diff <target-ref>...HEAD`, which is the named baseline `review-loop.md` requires and
covers the whole delivery rather than the latest change-set.

Only a PASS releases the undraft: the body regenerated with every box checked and
Breaking changes final, then `gh pr ready`. A loop exiting with unresolved findings
leaves the PR draft and returns the findings to the user. Merging the PR is the user's
act.

History invariant: every pushed head SHA recorded in the run report must remain an
ancestor of the final head — `git merge-base --is-ancestor <sha> HEAD` succeeds for each,
verifiable from any clone. That is the observable form of the no-force-push rule.

## No-commit override

Inside the implement workflow, the orchestrator's protocol actions — branch creation,
item-scoped staging, commit, push, PR operations — are authorized even where repository
instruction files forbid agent git writes. The bank directive carries this carve-out
itself, so what gets overridden is repository instructions alone.

The disclosure trigger is exactly that case: when the repository's instruction files
forbid agent commits, the decomposition report discloses the override before the first
git action and invites veto, and the final report states that it was exercised.

The scope is exactly the orchestrator's protocol. Coder subagents remain forbidden, and
nothing outside the workflow inherits the authorization.

A veto at start reverts the run to unstaged delivery in the live branch — zero git write
operations for the run. A mid-run veto freezes git operations from that moment: pushed
work stays, remaining items are delivered unstaged, and the PR stays draft with a final
regenerated body marking the boundary commit.

## Degradation ladder

No remote, no push access, or a fetch or push refused on authorization: commit locally
from that point, skip the target refresh, push, PR, and watch. Non-GitHub remote, or `gh` missing or unauthenticated:
commit and push, skip PR and watch. Every skipped rung is named in the report; no rung is
a hard failure. A reviewer that is unavailable is a blocker surfaced to the user, never a
silent skip.

Commit messages and PR bodies are public surface: they never mention the design spec —
no title, no vault path — and carry no secrets or personal data.
