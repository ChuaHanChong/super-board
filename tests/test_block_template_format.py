"""Pins the block-exit template's rendering shape and its machine lines (#1548).

GitHub Markdown collapses a single newline into a space, so a blocker written as
`Card:` / `PR:` / `Reason tag:` lines on consecutive single-newline lines renders
as one paragraph. Every prose field in the blocker block is therefore a list item,
while the lines a script reads (`blocked-by:`, `approval-request:`) stay bare at
column 0 so the sweep and the approval check keep matching them.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "skills" / "super-board" / "references" / "block-template.md"
DEPS = ROOT / "scripts" / "super-board-deps.sh"
APPROVAL = ROOT / "scripts" / "super-board-approval.py"
BUILD_SKILL = ROOT / "skills" / "super-build" / "SKILL.md"

PROSE_FIELDS = [
    "Card",
    "PR",
    "Reason tag",
    "Why blocked",
    "Evidence",
    "Checked",
    "What blocks",
    "Why I (bot) cannot decide",
    "To unblock",
    "Owner",
    "Move back",
]

# Mirror of super-board-deps.sh's `comment_line` anchor and super-board-approval.py's
# BLOCK regex; `_assert_parsers_keep_these_anchors` fails when either drifts.
DEP_LINE = re.compile(r"^[ \t]*blocked-by:", re.I)
APPROVAL_LINE = re.compile(r"^approval-request:")
NEEDS_TAG = re.compile(r"Reason tag:[^\n]*🙋")


def _fenced_blocks() -> list[str]:
    """Return every fenced block in the template."""
    return re.findall(r"```[a-z]*\n(.*?)```", TEMPLATE.read_text(encoding="utf-8"), flags=re.S)


def _blocker_block() -> str:
    """Return the generic `[<role>] [blocker]` block."""
    blocks = [b for b in _fenced_blocks() if b.startswith("[<role>] [blocker]")]
    assert len(blocks) == 1, f"expected one generic blocker block, found {len(blocks)}"
    return blocks[0]


def _needs_block() -> str:
    """Return the 🙋 needs-you block."""
    blocks = [b for b in _fenced_blocks() if "🙋 Your turn on" in b]
    assert len(blocks) == 1, f"expected one needs-you block, found {len(blocks)}"
    return blocks[0]


def _assert_parsers_keep_these_anchors() -> None:
    """The template and the parsers agree only while these anchors exist in the scripts."""
    assert '^[ \\t]*blocked-by:' in DEPS.read_text(encoding="utf-8"), (
        "super-board-deps.sh changed its blocked-by anchor; update the template and this test"
    )
    assert "^approval-request:" in APPROVAL.read_text(encoding="utf-8"), (
        "super-board-approval.py changed its approval-request anchor; update the template and this test"
    )


def test_prose_fields_are_list_items() -> None:
    """Every prose field is a list item, so GitHub renders one line per field."""
    block = _blocker_block()
    for field in PROSE_FIELDS:
        assert f"- **{field}:**" in block, f"field missing as a list item: {field}"
    # A field starts at column 0; indented lines continue the item above them.
    merged = [
        line for line in block.splitlines()[1:]
        if line.strip() and not line.startswith(("- **", " "))
    ]
    assert [line for line in merged if not DEP_LINE.match(line)] == [], (
        f"field lines would merge into one paragraph: {merged}"
    )


def test_blocked_by_line_stays_bare_for_the_sweep() -> None:
    """The sweep's parser reads a bare `blocked-by:`; a list item would hide it."""
    block = _blocker_block()
    assert "- **blocked-by:**" not in block, "blocked-by must not become a list item"
    hits = [line for line in block.splitlines() if DEP_LINE.match(line)]
    assert len(hits) == 1, f"expected one bare blocked-by line, found {hits}"
    assert block.splitlines()[block.splitlines().index(hits[0]) - 1].strip() == "", (
        "a blank line separates the bare blocked-by line from the list above it"
    )


def test_blocked_by_line_is_parseable_when_rendered() -> None:
    """Both rendered shapes the template prescribes parse with the sweep's value rule."""
    for rendered in ("blocked-by: 32, 91", "blocked-by: -"):
        assert DEP_LINE.match(rendered), f"sweep anchor misses {rendered!r}"
        # super-board-deps.sh strips blanks before matching the value.
        value = re.sub(r"[ \t]", "", DEP_LINE.sub("", rendered))
        assert re.fullmatch(r"\d+(,\d+)*|-", value), f"sweep value rule rejects {value!r}"


def test_parser_anchors_are_pinned() -> None:
    """The template's bare machine lines match the parsers' own anchors (#1548 R1)."""
    _assert_parsers_keep_these_anchors()


def test_needs_you_checklist_stays_before_the_fold() -> None:
    """The 🙋 block keeps its checklist before the fold, and nothing merges into its last item."""
    block = _needs_block()
    fold = block.index("<details><summary>Why, and what I checked</summary>")
    assert block.index("- [ ] ") < fold, "checklist items must come before the fold"
    lines = block.splitlines()
    last_item = max(i for i, line in enumerate(lines) if line.startswith("- [ ] "))
    assert lines[last_item + 1].strip() == "", (
        "a blank line separates the checklist from the sentence after it, or GitHub folds it in"
    )


def test_needs_you_machine_lines_stay_bare() -> None:
    """The planner and the approval check read the 🙋 block's machine lines at column 0."""
    block = _needs_block()
    assert [line for line in block.splitlines() if APPROVAL_LINE.match(line)], (
        "approval-request: must stay at column 0"
    )
    assert NEEDS_TAG.search(block), "Reason tag must name the 🙋 emoji"
    assert re.search(r"^blocked-by: -$", block, flags=re.M), "planner reads 'blocked-by: -'"


def test_builder_skill_leaves_ac_ticking_to_qa() -> None:
    """The Builder writes AC boxes unchecked; the Tester ticks them with proof."""
    text = BUILD_SKILL.read_text(encoding="utf-8")
    assert "Builder never ticks a box" in text
    assert "The Tester ticks each box" in text
    assert "Tick an AC in the issue body as soon as" not in text


if __name__ == "__main__":
    import pytest_lite
    raise SystemExit(pytest_lite.main(globals()))
