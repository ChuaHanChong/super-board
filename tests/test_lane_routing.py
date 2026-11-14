"""One lane-routing contract for every launcher: a typed card builds, a qa card tests.

A *qa card* is labelled `qa` and carries no build-path type label (bug, feature, ux,
refactor, tech-debt, tests, docs). It is the only card that enters at QA. Every other
Ready card builds, so a stale `qa` label cannot route a typed card to the Tester, and a
qa card back for a QA rebuild (`loop:rebuild-N`) stays in QA.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "scripts"
PLAN = BIN / "super-board-wave-plan.sh"
RUN = BIN / "super-board-run.sh"
CODEX = BIN / "super-board-codex-wave.sh"
WAVE = ROOT / "workflows" / "super-board-wave.js"

# Every label path of the routing contract, and the lane it must enter.
ROUTING = [
    (1, "Ready", [], "build"),
    (2, "Ready", ["qa"], "qa"),
    (3, "Ready", ["qa", "loop:rebuild-1"], "qa"),
    (4, "Ready", ["bug", "qa"], "build"),
    (5, "Ready", ["bug", "qa", "loop:rebuild-1"], "build"),
    (6, "Ready", ["feature", "qa"], "build"),
    (7, "Ready", ["docs", "qa"], "build"),
    (8, "QA", ["qa"], "qa"),
    (9, "Review", ["qa"], "review"),
    (10, "Building", ["qa"], "build"),
]


def _item(number: int, status: str, labels: list[str]) -> dict:
    """Return one board item node, the shape `super-board-card.sh items` prints."""
    return {
        "id": str(number),
        "status": status,
        "labels": labels,
        "title": f"card {number}",
        "content": {
            "type": "Issue",
            "number": number,
            "title": f"card {number}",
            "url": "u",
            "repository": "acme/app",
        },
    }


def _plan(tmp_path: Path, cards: list[dict]) -> dict[int, str]:
    """Run the real planner offline and return {number: lane} for every picked card."""
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "verify_commands": ["true"],
        "repo": {"path": str(ROOT)},
        "project": {"owner": "acme", "number": 4},
        "max_workers": 0,
    }))
    (tmp_path / "items.json").write_text(json.dumps({"items": cards}))
    (tmp_path / "deps.json").write_text(json.dumps({
        str(card["content"]["number"]): {"runnable": True, "blockers": []} for card in cards
    }))
    env = dict(os.environ)
    env.update(SB_GITHUB_HALT_FILE=str(tmp_path / "halt.json"), SB_GITHUB_RETRY_DELAY="0")
    result = subprocess.run(
        ["bash", str(PLAN), "--config", str(config), "--items", str(tmp_path / "items.json"),
         "--deps", str(tmp_path / "deps.json")],
        capture_output=True, text=True, env=env, cwd=tmp_path, check=False,
    )
    assert result.returncode == 0, result.stderr
    return {card["number"]: card["lane"] for card in json.loads(result.stdout)["cards"]}


def test_planner_routes_every_card_by_its_label_chain(tmp_path: Path) -> None:
    """The planner picks the lane from status first, then from the card's label chain."""
    rows = [row for row in ROUTING if row[1] in ("Ready", "QA", "Review")]
    lanes = _plan(tmp_path, [_item(number, status, labels) for number, status, labels, _ in rows])
    assert lanes == {number: lane for number, _, _, lane in rows}


def test_legacy_runner_routes_a_ready_card_by_its_label_chain() -> None:
    """`card_lane` returns qa only for a Ready qa card, whatever rebuild labels it has."""
    source = RUN.read_text()
    body = re.search(r"card_lane\(\) \{(.*?)\n\}", source, re.S)
    assert body, "card_lane() not found in super-board-run.sh"
    program = re.search(r"jq -r --argjson n \"\$1\" '(.*?)'", body.group(1), re.S)
    assert program, "card_lane() no longer runs a jq filter on PROJECT_ITEMS_JSON"
    cards = json.loads(json.dumps({"items": [
        _item(number, status, labels) for number, status, labels, _ in ROUTING if status == "Ready"
    ]}))

    def lane_of(number: int) -> str:
        return subprocess.run(
            ["jq", "-r", "--argjson", "n", str(number), program.group(1)],
            input=json.dumps(cards), capture_output=True, text=True, check=True,
        ).stdout.strip()

    for number, status, labels, lane in ROUTING:
        if status == "Ready":
            assert lane_of(number) == lane, f"card_lane({number}, {labels}) must be {lane}"


def test_workflow_ready_lane_routes_by_the_label_chain() -> None:
    """`readyLane` enters a Ready card at QA only when it is a qa card."""
    node = shutil.which("node")
    assert node, "node is required to evaluate the wave workflow's readyLane"
    source = WAVE.read_text()
    start = source.index("const labelsOf = ")
    end = source.index("\n", source.index("const readyLane = ")) + 1
    script = source[start:end] + """
const rows = JSON.parse(require('fs').readFileSync(0, 'utf8'))
console.log(JSON.stringify(Object.fromEntries(rows.map(([number, card]) => [number, readyLane(card)]))))
"""
    ready = [(n, s, l, lane) for n, s, l, lane in ROUTING if s == "Ready"]
    lanes = json.loads(subprocess.run(
        [node, "-e", script],
        input=json.dumps([[n, {"status": s, "labels": l}] for n, s, l, _ in ready]),
        capture_output=True, text=True, check=True,
    ).stdout)
    for number, status, labels, lane in ready:
        assert lanes[str(number)] == lane, f"readyLane({status}, {labels}) must be {lane}"


def test_codex_wave_entry_lane_routes_by_the_label_chain() -> None:
    """The codex/opencode fallback uses the same rule when the planner sends no lane."""
    source = CODEX.read_text()
    constant = source.index("BUILD_PATH_TYPES = ")
    function = source.index("def entry_lane(")
    lines = source[function:].splitlines(keepends=True)
    end = function + len(lines[0])
    for line in lines[1:]:
        if line.strip() and not line.startswith(" "):
            break
        end += len(line)
    snippet = source[constant:source.index("\n", constant) + 1] + "\n" + source[function:end]
    namespace: dict = {}
    exec(compile(snippet, str(CODEX), "exec"), namespace)  # noqa: S102 - the real predicate
    entry_lane = namespace["entry_lane"]
    for number, status, labels, lane in ROUTING:
        if status == "Ready":
            assert entry_lane(labels) == lane, f"entry_lane({labels}) must be {lane}"


if __name__ == "__main__":
    import pytest_lite
    raise SystemExit(pytest_lite.main(globals()))
