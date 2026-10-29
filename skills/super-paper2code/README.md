# Paper2Code for Super Board

An optional capability that generates a paper-to-project candidate through Codex or Claude Code using an existing CLI login.
The default installation and cards without the opt-in keep their existing behavior.
Codex is the live-verified path; the retained Claude adapter has not passed live verification.

Install the capability explicitly:

```sh
bash install.sh --with-paper2code --hosts codex <project>
```

The capability requires its converted, pinned `vendor/Paper2Code` source and Python 3.10+ with the declared runtime dependency.
Installation copies the runtime into `.agents/lib/paper2code/` and links the skill through the selected hosts.
An unpublished or missing converted revision is a distribution blocker; the original upstream API implementation is not a compatible runtime.

For an archive install of this fork, set `SUPER_BOARD_REPO` and select a published Board ref containing this capability and its exact Paper2Code gitlink:

```sh
SUPER_BOARD_REPO=ChuaHanChong/super-board bash get.sh --ref '<published-Board-ref>' --with-paper2code --hosts=codex --target '<project>'
```

Replace the quoted placeholders before running the command.
`get.sh` otherwise defaults to `EricTechPro/super-board`; the Board integration must be published separately before this fork command is usable.

Add the capability token to a research card:

```markdown
Skills: super-paper2code

## Papers
- https://arxiv.org/abs/1706.03762

## Context
Paper input: papers/transformer.tex (LaTeX), obtained from the cited source.
Execution budget: an explicit per-stage timeout based on the approved fixture run.

## Acceptance Criteria
- Implement the specified component in the existing project.
- Pass independently authored numerical checks and the project's existing tests.
```

The token is additive to the card's label/default helper chain.
The research preamble still acquires and reads the paper, checks reference-code licensing, and locates integration points with GitNexus.
Builder runs Paper2Code in a dedicated directory inside the existing issue worktree, reviews its candidate files, and integrates only what the card needs.
QA and Review retain their normal authority; generation never implies a passing implementation or an automatic merge.

See [the capability instructions](SKILL.md) for the runtime check, generation command, evidence, and failure handling.
Raw PDF conversion and published training-metric reproduction are outside this integration's verified scope.
