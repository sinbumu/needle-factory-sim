"""Measures how well Needle handles paraphrased English commands.

Each case defines the expected tool call. A run counts as PASS when Needle
returns exactly that call with confidence >= threshold (i.e. it would route
LOCAL and execute the intended action).

Usage: uv run python scripts/paraphrase_spike.py [--threshold 0.75]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from needle_factory_sim.ai.needle_adapter import build_agent, run_single_command
from needle_factory_sim.ai.router import Route, decide_route
from needle_factory_sim.constants import DEFAULT_CONFIDENCE_THRESHOLD

# (prompt, expected action, expected arguments)
CASES = [
    # --- move_robot: synonyms for "move to sector X"
    ("Move the robot to sector A.", "move_robot", {"target_sector": "A"}),
    ("Go to sector A.", "move_robot", {"target_sector": "A"}),
    ("Head over to sector B.", "move_robot", {"target_sector": "B"}),
    ("Send the robot into sector C.", "move_robot", {"target_sector": "C"}),
    ("Drive to E.", "move_robot", {"target_sector": "E"}),
    ("Take the cargo to sector B.", "move_robot", {"target_sector": "B"}),
    # --- set_temperature: warm/cool/adjust/make
    ("Set sector A temperature to 30 degrees.", "set_temperature", {"sector_id": "A", "target_c": 30}),
    ("Warm up sector A to 30 degrees.", "set_temperature", {"sector_id": "A", "target_c": 30}),
    ("Cool sector B down to 25 degrees.", "set_temperature", {"sector_id": "B", "target_c": 25}),
    ("Make sector E 35 degrees.", "set_temperature", {"sector_id": "E", "target_c": 35}),
    ("Adjust the temperature of sector C to 20.", "set_temperature", {"sector_id": "C", "target_c": 20}),
    ("Change sector A to 22 degrees Celsius.", "set_temperature", {"sector_id": "A", "target_c": 22}),
    # --- toggle_door: open/close/shut/unlock
    ("Open the door of sector B.", "toggle_door", {"sector_id": "B", "open": True}),
    ("Open sector B's door.", "toggle_door", {"sector_id": "B", "open": True}),
    ("Close the door to sector B.", "toggle_door", {"sector_id": "B", "open": False}),
    ("Shut the B door.", "toggle_door", {"sector_id": "B", "open": False}),
    ("Unlock the entry door for B.", "toggle_door", {"sector_id": "B", "open": True}),
    # --- reset_sector: reset/clean/decontaminate
    ("Reset sector C.", "reset_sector", {"sector_id": "C"}),
    ("Decontaminate sector C.", "reset_sector", {"sector_id": "C"}),
    ("Clean up sector C.", "reset_sector", {"sector_id": "C"}),
    ("Clear the contamination in C.", "reset_sector", {"sector_id": "C"}),
    # --- emergency_stop: stop/halt/abort
    ("Emergency stop.", "emergency_stop", {}),
    ("Stop everything right now!", "emergency_stop", {}),
    ("Halt the factory immediately.", "emergency_stop", {}),
    ("Abort all operations, emergency!", "emergency_stop", {}),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=DEFAULT_CONFIDENCE_THRESHOLD)
    args = parser.parse_args()

    agent = build_agent()
    passed = 0
    per_action: dict[str, list[int]] = {}
    for prompt, want_action, want_args in CASES:
        result = run_single_command(agent, prompt)
        decision = decide_route(result, args.threshold)
        ok = (
            decision.route is Route.LOCAL
            and decision.action == want_action
            and decision.arguments == want_args
        )
        passed += ok
        per_action.setdefault(want_action, []).append(int(ok))
        conf = f"{result.confidence:.2f}" if result.confidence is not None else "None"
        got = (
            f"{decision.action}({decision.arguments})"
            if decision.route is Route.LOCAL
            else f"CLOUD ({decision.reason})"
        )
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] conf={conf}  {prompt!r}")
        if not ok:
            print(f"       want {want_action}({want_args})")
            print(f"       got  {got}")

    print()
    for action, results in per_action.items():
        print(f"{action:>18}: {sum(results)}/{len(results)}")
    print(f"{'TOTAL':>18}: {passed}/{len(CASES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
