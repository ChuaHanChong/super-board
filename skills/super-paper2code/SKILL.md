---
name: super-paper2code
description: Generate a paper-to-project candidate for a Super Board research card that explicitly lists super-paper2code in Skills. Use after the research preamble, before Builder integrates the required files; retain the existing QA and Review gates.
---

# Paper2Code capability

Run only for a card with a nonempty `## Papers` section and an explicit `Skills: super-paper2code` token.
This token adds the capability to the label-selected Builder helpers; it does not replace TDD or other required helpers.
Use the existing issue worktree and branch; Builder owns integration, tests, PRs, and lifecycle writes.

## Generate

1. Complete [the research preamble](../super-build/references/research-preamble.md) through locating the integration point in this repository.
   Keep paper IDs, source URLs, reference revision/license, and GitNexus evidence.
2. Prepare a local input from the paper source: `JSON` containing the documented paper object, or the paper's `LaTeX` text.
   Read `.agents/lib/paper2code/CONTRACTS.md` in the owning project for the stage contract.
   JSON must be a top-level object containing the sourced paper content; the controller supplies that text verbatim to the stage prompts.
   alphaxiv prose is not a Paper2Code JSON object; explicitly transcribe sourced content into the supported format and record that transformation, omissions, and the source URL.
   Stop with the existing `❓` Blocked template if the method or required input is missing; do not invent equations, datasets, or implementation requirements.
3. Recheck skill readiness with the hydrated card JSON and `--require super-paper2code`, then run the installed helper's runtime check for the actual lane host.
   From the owning project root, with `<worktree>` pointing to the existing issue worktree:

   ```sh
   python3 .claude/bin/super-board-skills-ready.py --root <project-root> --host codex --cards <cards.json> --lane build --require super-paper2code
   python3 .claude/bin/super-board-paper2code.py --check --root <worktree> --host codex
   ```

   Substitute the actual supported lane host throughout; use a card-requested backend override only when explicit and after checking it separately.
   `--check` proves runtime, dependencies, and CLI availability; it does not authenticate.
   Generation checks the selected CLI login before inference; missing runtime, CLI, or login halts without advancing the card.
   Saved CLI login supplies inference; never add provider API keys or switch backends silently.
4. Choose a fresh output directory strictly inside that issue worktree and an explicit positive per-stage timeout justified by a measured fixture or the card's execution budget.
   Run the full planning, configuration, analysis, coding, and reproduction-script workflow:

   ```sh
   python3 .claude/bin/super-board-paper2code.py --root <worktree> --host codex --paper <paper.json> --paper-format JSON --timeout <seconds> --output-dir <worktree>/paper2code/run-1
   ```

   Use `--paper-format LaTeX` for supported LaTeX input and `--model <exact-id>` only when explicitly selected.
   The helper writes `artifacts/` and `candidate/`; it does not run generated commands or integrate candidate files.
   Success requires exit 0 and a completed result with its stage manifest; nonzero exit, malformed output, or interruption is failure, never permission to advance to QA.

## Integrate and hand off

Inspect the candidate and reproduction script before executing any generated code in an isolated verification environment.
Adapt only files required by the card's ACs, preserving project conventions, existing files, license notices, and the existing PR size cap.
Run independent project tests against the integrated change; a generated test or a successful model response alone proves no AC.
Keep the existing Builder, QA, Review, and human merge gates.

Add a `Paper2Code:` evidence bullet to the existing `solution` block and Builder handoff: backend, recorded model/CLI version, runtime revision and source digest, input hash and transformation, completed stage, returned `evidence_path` and candidate/manifest paths, selected files, verification command and outcome.
Make the required manifest and verification evidence reachable from the normal PR/issue handoff before worktree cleanup; local scratch paths alone are insufficient.
Keep failed/interrupted evidence and name the failed stage; use a new full-run directory for a rebuild rather than overwriting the old result.

For a card explicitly requiring name refinement, debugging, or evaluation, use the helper's corresponding `--stage` and its documented options from `--help` on the same isolated candidate tree.
These retain Paper2Code's workflow and backups; they do not authorize running generated setup or training scripts.
QA and Review consume the recorded evidence and rerun independent project checks; they do not start fresh inference automatically.
