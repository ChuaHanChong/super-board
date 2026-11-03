# Paper2Code for Super Board

An optional capability that generates a paper-to-project candidate through Codex, Claude Code or OpenCode using an existing CLI login.
The default installation and cards without the opt-in keep their existing behavior.

Install the capability explicitly:

```sh
bash install.sh --with-paper2code --hosts codex <project>
```

The capability requires the pinned `vendor/Paper2Code` source.
Installation copies the runtime into `.agents/lib/paper2code/` and links the skill through the selected hosts.

To install this fork with `get.sh`, which uses a git clone of the default branch (or `--ref` tag or branch) for this capability:

```sh
SUPER_BOARD_REPO=ChuaHanChong/super-board bash get.sh --with-paper2code --hosts=codex --target '<project>'
```

Add the capability token to a research card:

```markdown
Skills: super-paper2code

## Papers
- https://arxiv.org/abs/1706.03762

## Context
Paper input: papers/transformer.tex (LaTeX), obtained from the cited source.

## Acceptance Criteria
- Implement the specified component in the existing project.
- Pass independently authored numerical checks and the project's existing tests.
```

The token is additive to the card's label/default helper chain.
The research preamble still acquires and reads the paper, checks reference-code licensing, and locates integration points with GitNexus.
Builder runs Paper2Code in a dedicated directory inside the existing issue worktree, reviews its candidate files, and integrates only what the card needs.
QA and Review retain their normal authority; generation never implies a passing implementation or an automatic merge.

For an opted-in Codex Builder, the lane also permits writes to the existing nonsecret `installation_id` file under `CODEX_HOME` (default `~/.codex`).
[Codex v0.165.0 opens that file for reading and writing before startup](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/core/src/installation_id.rs#L20-L29), even when it already exists.
The grant uses the canonical home path and rejects a missing, nonregular, symlinked, or hard-linked ID before launching the lane; it never grants the home directory, credentials, or global SQLite databases additional write access.
Ordinary cards, QA, and Review retain their existing grants.
Builder shell tools receive the validated canonical `CODEX_HOME` path so nested stages retain the same saved login when their working directory changes; an explicit `shell_environment_policy.include_only` filter must also allow `CODEX_HOME` for a custom home.

See [the capability instructions](SKILL.md) for the runtime check, generation command, evidence, and failure handling.
Raw PDF conversion and published training-metric reproduction are outside this integration's verified scope.
