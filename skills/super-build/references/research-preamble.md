# Research preamble (Builder step 3c, research cards only)

A ticket with a `## Papers` section is a research card. Before implementing (Builder step 4),
turn the papers into a change in this repo: find them, read the useful part, reuse the paper's
own code where it exists, and use GitNexus on BOTH the reference repo and this repo. Every
other Builder rule still applies: smallest safe change, PR size cap, commits, PR blocks, report.

## Steps

1. **Papers.** Take the arxiv IDs / URLs from `## Papers`. A `- search: <query>` line instead →
   `mcp__alphaxiv__discover_papers` with the query, plus the ticket's Problem and Fix as context;
   pick at most 3, preferring papers with official code.
2. **Understand.** `mcp__alphaxiv__get_paper_content` (and `mcp__alphaxiv__answer_pdf_queries`
   for specific questions). Extract only the part the ACs need: the component, its equations,
   hyperparameters and the metric the paper reports for it. Keep a 3–5 line summary for the PR.
3. **Reference repo.** Take the official code link from the paper text or its alphaxiv page.
   Only a `github.com` repo that `mcp__alphaxiv__read_files_from_github_repository` can read is
   cloned; read it there first, then check its license: the SPDX id in its LICENSE / COPYING
   file, `none` when there is no such file. Any license is cloned and indexed for reading; the
   license decides what may be copied:
   - permissive (MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0) → adapt its code;
   - any other id, or `none` → copy nothing; implement from the paper and say so in the PR.
   `<refs>` = the path `mktemp -d /tmp/super-board-refs.XXXXXX` prints, new for each lane run: outside the
   project, so git never sees it, and under `/tmp`, so `guard-delete-outside` allows its
   cleanup. Per paper repo: `git clone --filter=blob:none <url> <refs>/<owner>_<repo>`, owner
   and repo from the URL, lowercased; a repo cited by two papers is cloned once.
   Record `git -C <clone> rev-parse HEAD`; a rebuild clones again and runs
   `git -C <clone> checkout <recorded sha>`.
   No usable repo → skip the reference half of steps 4 and 5; implement from the paper.
4. **Index both repos.** Always `--index-only`: plain `analyze` writes AGENTS.md, CLAUDE.md and
   `.claude/skills/gitnexus/` into the repo, which would land in the PR. `--index-only` writes
   none of them, still registers the repo, and adds `.gitnexus/` to `.git/info/exclude`.
   - Reference: `gitnexus analyze --index-only <clone>`.
   - This repo: index the build worktree itself, so the index is this card's branch:
     `gitnexus analyze --index-only .` from the worktree root.
   - Folder names repeat across projects (`issue-<N>-build`), so pass the absolute path as
     `repo` below, not the name.
5. **Locate in the reference repo.** GitNexus `query` / `context` with `repo=<clone path>`: the
   symbols that implement the paper's component, their callees and the config they read.
6. **Locate in this repo.** GitNexus `query` / `context` with `repo=<worktree path>` for the
   integration point, then `impact` (upstream) on every symbol you will change. HIGH or CRITICAL
   risk → name it in the `risk` block.
6a. **Paper2Code opt-in.** If the card explicitly lists `super-paper2code` in `Skills:`, invoke [the capability](../../super-paper2code/SKILL.md) after the research steps above and before step 7.
   It generates into a dedicated candidate/artifact directory inside the existing issue worktree using the actual lane host, or an explicitly requested and separately checked backend override.
   Missing prerequisites halt before generation; failed, malformed, or interrupted results preserve evidence and never advance to QA.
   Without that token, continue the existing workflow without checking or downloading Paper2Code.
7. **Implement** (Builder step 4). Adapt only the needed functions. Each adapted unit gets one
   comment: `Adapted from <repo url>@<sha>:<path>`. The license requires keeping its notice:
   append the reference repo's copyright + license text to `THIRD_PARTY_NOTICES.md` at the repo
   root (create it if missing), one section per repo.
8. **Record.** In the PR `solution` block, before the `Docs:` bullets:
   - `Papers:` arxiv ID · title · the part used;
   - `Reused:` repo url@sha · license · files adapted, or `url@sha · license · none copied: <why>`
     when nothing was copied (license forbids it, or the code did not fit), or
     `none: no usable repo` when step 3 found none;
   - `GitNexus:` each query, labelled `ref` or `dev`, with the symbol it found, and each
     `impact` target with its risk.
   - For opted-in cards, `Paper2Code:` provenance, stage manifest, selected candidate files, and independent verification evidence as required by the capability.
9. **Clean up** on every exit from the lane, Blocked and split exits included:
   `gitnexus clean --force` in the worktree and in each clone, then `rm -rf <refs>`. The PR
   evidence is the record.

**Rebuild.** Keep the `Papers:` / `Reused:` / `GitNexus:` bullets and any `Paper2Code:` evidence when rewriting `solution`.
For new full generation, use a fresh run directory and preserve the previous candidate and failure records; do not overwrite user work or imply automatic resume.
Index the new worktree (step 4, this-repo part). A thread that needs reference code → step 3
at the recorded sha, then steps 4 (reference part) and 5. Run step 6 again for any symbol the
rebuild changes that is not listed yet, add it, then step 9.

## Hosts without GitNexus MCP (e.g. hpc)

Same steps through the CLI: `gitnexus query|context|impact -r <path> ...`. If `analyze` fails
on the buffer pool there, set `GITNEXUS_LBUG_BUFFER_POOL_SIZE=4294967296` (the size measured
to work on hpc).

## Blocked exits (block-template.md)

- alphaxiv MCP or `gitnexus` not available on this host → 🔑, naming the missing tool.
- `## Papers` empty, IDs that do not resolve, a search with no match, or a paper that leaves
  the needed part unspecified → ❓, naming what is missing.
