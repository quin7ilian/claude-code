---
name: codex-brainstorm
description: Conduct one explicitly requested Codex divergence pass alongside your own brainstorming, then reconcile both option spaces. Invoke only when the user explicitly requests Codex by name or invokes /codex-brainstorm; design, strategy, architecture, implementation approaches, or anchoring risk alone are not triggers. Do not invoke after another Codex pass or when the user declined Codex.
---

# Brainstorm with Codex

Use Codex for a full independent divergence pass while conducting a substantive native brainstorm of
your own. Do not ask Codex to choose the winner; reconcile both option spaces before evaluating or
converging.

## Confirm explicit authorization

Proceed only when the user explicitly requested Codex by name or invoked `/codex-brainstorm`. Stop
and brainstorm natively if authorization is absent, the user declined Codex, or any Codex skill
already ran for this task. Use one Codex pass and never chain into another Codex skill; only the
user may request a follow-up pass.

## Seed useful divergence

Write a focused, self-contained temporary brief containing everything Codex needs to explore the
option space completely:

- the concrete problem or opportunity;
- the goal and what a good outcome looks like;
- hard constraints and non-goals;
- approaches already considered, rejected, or overrepresented;
- the axes along which genuine variety would be useful;
- any requested minimum number of ideas, treating it as a floor unless the user explicitly asks for
  an exact count.

Codex cannot see the conversation. Include the context needed to make ideas specific, but omit
duplicated large code or documentation dumps. Research unknown facts with native tools before
preparing the brief; do not chain into `/codex-research`.

End the brief with this contract:

```text
Perform exhaustive divergent ideation before converging. Build a coverage map of the problem's
meaningful axes, then explore each axis and useful combinations systematically. Span different
mechanisms, ownership boundaries, abstraction levels, time horizons, resource profiles, risk
profiles, reversibility, incentives, and cross-domain analogies where relevant. Include simple and
conservative options, ambitious options, contrarian reframings, inversions, hybrids, staged paths,
and approaches that remove or redefine the problem. Do not stop after the first obvious set: run
additional divergence rounds, look for missing categories and near-duplicates, and continue until
new rounds produce no materially distinct mechanisms. Do not optimize for speed, brevity, or a
fixed small idea count. Do not repeat the approaches already listed, count cosmetic variations as
distinct, or rank a winner.

Organize the result as: coverage map; exhaustive option catalog grouped by genuinely different
mechanisms; hybrids and staged combinations; gaps explored but found unproductive; factual
assumptions requiring research. For each option provide: one-line gist; the distinct mechanism or
insight; why it could fit these constraints; the largest risk; and what must be true for it to work.
Verify factual assumptions when useful and cite the evidence; otherwise tag them as unverified. If
one missing constraint prevents useful divergence, name it instead of guessing.
```

## Run a divergence pass

Run Codex from an empty temporary directory so the pass diverges from the brief alone rather than
anchoring on repository contents; live web access lets it verify factual assumptions. Codex inherits
the user's configured model and reasoning effort; pass no model or effort flags.

```bash
# Create the empty temporary directory and the brief first, then substitute concrete paths.
SCRATCH="$(mktemp -d)"
codex exec --skip-git-repo-check \
  --sandbox workspace-write \
  -c sandbox_workspace_write.network_access=true \
  -c web_search=live \
  -C "$SCRATCH" \
  "$(cat "/absolute/path/to/codex-brainstorm-brief.md")" </dev/null \
  >"/absolute/path/to/codex-brainstorm.md" \
  2>"/absolute/path/to/codex-brainstorm.stderr"
```

Wait for the complete run; do not cut it short because it takes several minutes. Fill thin axes with
your own native divergence rather than starting another Codex pass. If Codex is missing,
unauthenticated, or fails, state that briefly and perform the full divergence pass yourself.

## Reconcile the option spaces

1. Conduct your own exhaustive native brainstorm, in parallel with Codex when practical. Explore the
   problem independently rather than merely extending Codex's list.
2. Compare coverage maps and identify mechanisms, reframings, combinations, and risks found by
   either pass but missed by the other.
3. Merge true duplicates without discarding materially different variants, and remove only ideas
   that are generic or violate hard constraints.
4. Run another native divergence round for important gaps exposed by the comparison.
5. Verify factual assumptions before using them to evaluate an option.
6. Build a complete integrated option map. Compare options against the goal, constraints, risks,
   reversibility, and information needed next.
7. Converge only when the user asks for a recommendation; preserve the broader map even when
   presenting a shortlist.

Give the user the raw Codex brainstorm path and the complete integrated option map. Include a
refined shortlist only when useful or requested, and state what was merged or discarded and why.
Present all ideas as candidates until evidence or testing supports them.
