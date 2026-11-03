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
   JSON must be a top-level object containing the sourced paper content; the scripts supply that text verbatim to the stage prompts.
   alphaxiv prose is not a Paper2Code JSON object; explicitly transcribe sourced content into the supported format and record that transformation, omissions, and the source URL.
   Stop with the existing `❓` Blocked template if the method or required input is missing; do not invent equations, datasets, or implementation requirements.
3. Recheck skill readiness with the hydrated card JSON and `--require super-paper2code`.
   From the owning project root:

   ```sh
   python3 .claude/bin/super-board-skills-ready.py --root <project-root> --host codex --cards <cards.json> --lane build --require super-paper2code
   ```

   Substitute the actual supported lane host throughout; use a card-requested backend override only when explicit.
   Saved CLI login supplies inference; never add provider API keys or switch backends silently.
4. Choose a fresh output directory strictly inside that issue worktree, then run Paper2Code's stages in order, each one only after the last exits 0:

   ```sh
   export PAPER2CODE_BACKEND=codex  # the lane host: codex, claude or opencode
   P=<project-root>/.agents/lib/paper2code; OUT=<worktree>/paper2code/run-1/artifacts; REPO=<worktree>/paper2code/run-1/candidate
   ARGS="--paper_name <name> --gpt_version o3-mini --paper_format JSON --pdf_json_path <paper.json> --output_dir $OUT"  # the CLI backends ignore --gpt_version
   mkdir -p "$OUT" "$REPO"
   "$P/.venv/bin/python" "$P/codes/1_planning.py" $ARGS
   "$P/.venv/bin/python" "$P/codes/1.1_extract_config.py" --paper_name <name> --output_dir "$OUT"
   cp "$OUT/planning_config.yaml" "$REPO/config.yaml"
   "$P/.venv/bin/python" "$P/codes/2_analyzing.py" $ARGS
   "$P/.venv/bin/python" "$P/codes/3_coding.py" $ARGS --output_repo_dir "$REPO"
   "$P/.venv/bin/python" "$P/codes/3.1_coding_sh.py" $ARGS --output_repo_dir "$REPO"
   ```

   On a Claude lane run each line as its own command, with the variables expanded and `PAPER2CODE_BACKEND=claude` as its prefix: the allowlist cannot match `export` or `$P`.
   For LaTeX input use `--paper_format LaTeX --pdf_latex_path <paper.tex>`; set `PAPER2CODE_MODEL` only when a model is explicitly selected, or on an OpenCode lane to the board's `opencode.model`, which does not reach nested stages by itself.
   Run the lane host's own backend on Codex and OpenCode lanes: their write jails do not grant another CLI's state.
   Calls have no timeout and do not retry, so run long stages in the background; a transient capacity error fails the stage, and rerunning that stage is safe.
   The scripts write `artifacts/` and `candidate/`; they do not run generated commands or integrate candidate files.
   Any nonzero exit, including a missing login or an interruption, is failure, never permission to advance to QA.

## Integrate and hand off

Inspect the candidate and reproduction script before executing any generated code in an isolated verification environment.
Adapt only files required by the card's ACs, preserving project conventions, existing files, license notices, and the existing PR size cap.
Stage integrated files by explicit path; the `paper2code/` run directory never enters the commit.
Run independent project tests against the integrated change; a generated test or a successful model response alone proves no AC.
Keep the existing Builder, QA, Review, and human merge gates.

Add a `Paper2Code:` evidence bullet to the existing `solution` block and Builder handoff: backend, recorded model/CLI version, runtime revision from `.agents/lib/paper2code/installation.json`, input transformation, completed stages, candidate path, selected files, verification command and outcome.
Make the required verification evidence reachable from the normal PR/issue handoff before worktree cleanup; local scratch paths alone are insufficient.
Keep failed/interrupted evidence and name the failed stage; use a new run directory for a rebuild rather than overwriting the old result.

QA and Review consume the recorded evidence and rerun independent project checks; they do not start fresh inference automatically.
