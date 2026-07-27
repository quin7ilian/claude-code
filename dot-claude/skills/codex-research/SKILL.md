---
name: codex-research
description: Conduct one explicitly requested independent Codex research pass alongside your own investigation, then verify and reconcile the evidence. Invoke only when the user explicitly requests Codex by name or invokes /codex-research; broad or deep research alone is not a trigger. Do not invoke after another Codex pass or when the user declined Codex.
---

# Research with Codex

Use Codex for a full independent research pass while conducting a substantive native research pass of
your own. Retain responsibility for scoping, source verification, resolving disagreements, following
new leads, and producing the final integrated answer.

## Confirm explicit authorization

Proceed only when the user explicitly requested Codex by name or invoked `/codex-research`. Stop and
research natively if authorization is absent, the user declined Codex, or any Codex skill already ran
for this task. Use one Codex pass and never chain into another Codex skill; only the user may request
a follow-up pass.

## Scope the question

State reasonable assumptions when the request is slightly underspecified. Ask the user only when a
missing choice would materially change the investigation.

Create a focused, self-contained temporary brief containing everything Codex needs to investigate the
question completely:

- the sharpened research question and time horizon;
- relevant constraints, definitions, region, audience, or decision being informed;
- the subquestions a complete answer must resolve;
- the desired output depth and format;
- session context Codex cannot see;
- specific URLs, primary-source domains, or absolute local paths worth consulting;
- exclusions, especially secret-bearing paths.

Keep the brief efficient by pointing to large local artifacts instead of pasting them. Efficiency
here applies to duplicated input, not to research depth, source coverage, runtime, or output length.
Do not point Codex at an entire repository unless repository-wide evidence is genuinely required.

End the brief with this contract:

```text
Act as an exhaustive, evidence-driven researcher with live web access and read-only local access.
Produce a complete research dossier, not quick notes, a search summary, or a preliminary overview.
Cover every subquestion and investigate the wider context needed to interpret the answer correctly.
Search iteratively using multiple query formulations, fetch and read full sources rather than
relying on snippets, follow citations and important leads, and revisit weak or contradictory areas.
Prefer primary and authoritative sources; use independent secondary sources for corroboration,
criticism, and competing interpretations. Continue until the evidence converges, every material
subquestion is answered, or a specific unresolved gap is demonstrated. Do not optimize for speed,
brevity, or a predetermined output length.

Cite every load-bearing factual claim with a direct URL or file path and line number where possible.
Separate sourced findings, inference, and unresolved questions. Record search coverage, conflicts
between sources, publication dates, and event dates when recency matters. Never fabricate a source,
quote, number, or local fact. Do not read secrets, credentials, .env files, private keys, or ~/.ssh.
Do not change local files outside your scratch directory. Output: executive summary; comprehensive
findings organized by subquestion with inline citations; competing evidence and uncertainties;
source-by-source notes; sources consulted; unresolved gaps and promising follow-up leads.
```

## Run the research

Run Codex from an ephemeral scratch directory: it reads local artifacts by absolute path and fetches
live sources, while its writes stay confined to the throwaway scratch. Codex inherits the user's
configured model and reasoning effort; pass no model or effort flags.

```bash
# Create the brief and scratch directory first, then substitute concrete absolute paths.
SCRATCH="$(mktemp -d)"
codex exec --skip-git-repo-check \
  --sandbox workspace-write \
  -c sandbox_workspace_write.network_access=true \
  -c web_search=live \
  -C "$SCRATCH" \
  "$(cat "/absolute/path/to/codex-research-brief.md")" </dev/null \
  >"/absolute/path/to/codex-research.md" \
  2>"/absolute/path/to/codex-research.stderr"
```

Wait for the complete run; do not cut it short because it takes several minutes. If the dossier
leaves material subquestions thin, investigate them with native tools rather than starting another
Codex pass. If Codex is missing, unauthenticated, or fails, report the limitation and continue the
full native research pass.

## Verify and synthesize

Treat Codex's dossier as an independent research corpus, not as proof and not as a substitute for
your own research.

1. Conduct your own broad research with native tools — delegating read-heavy lanes to `researcher`
   subagents where useful — in parallel with Codex when practical. Build an independent view rather
   than merely checking Codex's citations.
2. Compare coverage: identify evidence, interpretations, counterarguments, and leads found by either
   researcher but missed by the other.
3. Open every source supporting a claim the final answer will rely on. Prefer the original source
   over either model's paraphrase and correct misread dates, scope, or causality.
4. Investigate material disagreements and follow valuable new leads from Codex until resolved or
   explicitly uncertain.
5. Cross-check consequential claims with independent evidence where appropriate, and distinguish
   verified findings from useful but still unverified leads.
6. Preserve genuine disagreement or uncertainty instead of forcing consensus.

Give the user the raw Codex dossier path and a complete integrated research answer at the depth the
question warrants. Incorporate verified Codex findings into the broader investigation, include
material corrections and disagreements, and retain useful detail rather than collapsing the work
into quick notes. Cite the sources you independently opened, not merely the dossier.
