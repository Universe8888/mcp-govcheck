"""Eval runner: labeled scan-accuracy + adversarial safety properties.

    python evals/run_evals.py            # report + append a block to BENCHMARK.md
    python evals/run_evals.py --no-write  # report only

Exit code: 0 if every safety property holds (accuracy is reported, not gated —
a labeled mismatch is a warning the rubric/labels drifted, but the hard gate is
safety). Mirrors wikilens: every run is timestamped and appended to BENCHMARK.md
so regressions are visible side by side.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "evals"))

from safety_cases import run_safety  # noqa: E402

from mcp_govcheck import introspect, scan_tools  # noqa: E402
from mcp_govcheck.rubric import load_rubric  # noqa: E402

FIXTURES = REPO / "evals" / "fixtures" / "tool_schemas.json"
SCENARIOS = REPO / "evals" / "scenarios.yaml"
RUBRIC = REPO / "rubrics" / "default.yaml"
BENCHMARK = REPO / "BENCHMARK.md"


def _load_fixture_tools(name: str, all_fixtures: dict):
    descriptors = all_fixtures[name]
    return introspect.tools_from_descriptors(descriptors)


def run_accuracy(rubric, fixtures: dict, scenarios: list[dict]) -> tuple[int, int, list[str]]:
    """Return (correct, total, mismatch_messages) over all labeled expectations."""
    correct = 0
    total = 0
    mismatches: list[str] = []
    for scen in scenarios:
        tools = _load_fixture_tools(scen["fixture"], fixtures)
        sc = scan_tools(tools, rubric, target=scen["fixture"])
        by_check = {(f.tool, f.check_id): f.result.value for f in sc.findings}
        for check_id, expected in scen["expect"].items():
            total += 1
            actual = by_check.get((scen["tool"], check_id), "missing")
            if actual == expected:
                correct += 1
            else:
                mismatches.append(
                    f"{scen['fixture']}/{scen['tool']}/{check_id}: "
                    f"expected {expected}, got {actual}"
                )
    return correct, total, mismatches


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        rc = getattr(stream, "reconfigure", None)
        if rc:
            rc(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("--no-write", action="store_true", help="don't append to BENCHMARK.md")
    parser.add_argument("--timestamp", default="", help="ISO timestamp for the BENCHMARK entry")
    ns = parser.parse_args(argv)

    rubric = load_rubric(RUBRIC)
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    scenarios = yaml.safe_load(SCENARIOS.read_text(encoding="utf-8"))["scenarios"]

    correct, total, mismatches = run_accuracy(rubric, fixtures, scenarios)
    safety_failures = run_safety(rubric)

    accuracy = correct / total if total else 1.0
    safety_pass = len(run_safety.__globals__["SAFETY_CASES"]) - len(safety_failures)  # type: ignore[attr-defined]
    safety_total = len(run_safety.__globals__["SAFETY_CASES"])  # type: ignore[attr-defined]

    print(f"Scan accuracy: {correct}/{total} = {accuracy:.0%}")
    for m in mismatches:
        print(f"  MISMATCH: {m}")
    print(f"Safety properties: {safety_pass}/{safety_total} held")
    for f in safety_failures:
        print(f"  {f}")

    if not ns.no_write:
        _append_benchmark(correct, total, accuracy, safety_pass, safety_total,
                          mismatches, safety_failures, ns.timestamp)
        print(f"appended results to {BENCHMARK.name}")

    # Hard gate: safety must hold. Accuracy mismatch is reported but non-fatal.
    return 1 if safety_failures else 0


def _append_benchmark(correct, total, accuracy, safety_pass, safety_total,
                      mismatches, safety_failures, timestamp) -> None:
    ts = timestamp or "(timestamp not supplied)"
    block = [
        f"\n## {ts}",
        "",
        f"- **Scan accuracy:** {correct}/{total} = {accuracy:.0%} on labeled scenarios "
        f"(`evals/scenarios.yaml`).",
        f"- **Safety properties:** {safety_pass}/{safety_total} held "
        f"(`evals/safety_cases.py`).",
    ]
    if mismatches:
        block.append("- Mismatches:")
        block += [f"  - {m}" for m in mismatches]
    if safety_failures:
        block.append("- SAFETY FAILURES:")
        block += [f"  - {f}" for f in safety_failures]
    block.append("")

    header = (
        ""
        if BENCHMARK.exists()
        else (
            "# Benchmark\n\nLabeled scan accuracy + adversarial safety "
            "properties. Every run is appended (never overwritten).\n"
        )
    )
    with BENCHMARK.open("a", encoding="utf-8") as fh:
        if header:
            fh.write(header)
        fh.write("\n".join(block))


if __name__ == "__main__":
    sys.exit(main())
