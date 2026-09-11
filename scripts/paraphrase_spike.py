"""Measures how well Needle handles differently phrased English commands.

Each case defines the expected tool call. A run counts as PASS when Needle
returns exactly that call with confidence >= threshold (i.e. it would route
LOCAL and execute the intended action).

Three suites:
  (default)      paraphrases of the documented commands
  --terse        very short commands ("move robot to a", "reset C")
  --letter-case  one template swept over every sector letter in both cases,
                 which is how the lower-case mis-extraction was found

Usage: uv run python scripts/paraphrase_spike.py [--terse|--letter-case] [--threshold 0.75]
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


# Short, telegraphic commands. Most of these escalate: see the README's
# "What we tried and what it cost" table for why that is left alone.
TERSE_CASES = [
    ("move robot to a", "move_robot", {"target_sector": "A"}),
    ("move robot to A", "move_robot", {"target_sector": "A"}),
    ("move to A", "move_robot", {"target_sector": "A"}),
    ("go to A", "move_robot", {"target_sector": "A"}),
    ("robot to E", "move_robot", {"target_sector": "E"}),
    ("A", "move_robot", {"target_sector": "A"}),
    ("Drive to E.", "move_robot", {"target_sector": "E"}),
    ("set A to 30", "set_temperature", {"sector_id": "A", "target_c": 30}),
    ("A to 30 degrees", "set_temperature", {"sector_id": "A", "target_c": 30}),
    ("heat A to 30", "set_temperature", {"sector_id": "A", "target_c": 30}),
    ("open B door", "toggle_door", {"sector_id": "B", "open": True}),
    ("open the door", "toggle_door", {"sector_id": "B", "open": True}),
    ("close B door", "toggle_door", {"sector_id": "B", "open": False}),
    ("reset C", "reset_sector", {"sector_id": "C"}),
    ("clean C", "reset_sector", {"sector_id": "C"}),
    ("stop", "emergency_stop", {}),
    ("e-stop", "emergency_stop", {}),
]

# Goal-oriented requests that must keep escalating to the Cloud planner —
# any tuning that makes these route LOCAL has broken Demo C.
MUST_ESCALATE = [
    "Inspect the current factory state, determine the required actions and their "
    "safe order, and transport the cargo to sector E without damage.",
    "transport the cargo to sector E safely",
    "get the cargo to the goal",
]


def run_letter_case_sweep(agent, threshold: float) -> int:
    """Sweep one template over every sector letter, upper and lower case.

    This is the suite that exposed the real hazard: with a lower-case letter
    *and* the word "sector", the model extracts sector S whatever letter was
    asked for — a wrong action held back only by the confidence gate.
    """
    worst_wrong = 0.0
    for template in ("move robot to {}", "move robot to sector {}"):
        print(f"template: {template!r}")
        for letter in ("S", "s", "A", "a", "B", "b", "C", "c", "E", "e"):
            result = run_single_command(agent, template.format(letter))
            call = result.function_calls[0] if result.function_calls else {}
            got = (call.get("arguments") or {}).get("target_sector")
            conf = result.confidence
            correct = bool(got) and got.upper() == letter.upper()
            if not correct and conf is not None:
                worst_wrong = max(worst_wrong, conf)
            conf_text = f"{conf:.2f}" if conf is not None else "None"
            print(
                f"  {'ok ' if correct else 'BAD'} {letter!r:4} conf={conf_text}"
                f" -> {got}"
                + ("" if correct or conf is None or conf < threshold else "  << WOULD EXECUTE")
            )
        print()
    print(f"highest confidence on a WRONG sector: {worst_wrong:.2f} (threshold {threshold:.2f})")
    if worst_wrong >= threshold:
        print("FAIL: a wrong extraction would be executed locally")
        return 1
    print("OK: every wrong extraction stays below the threshold and escalates")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=DEFAULT_CONFIDENCE_THRESHOLD)
    parser.add_argument("--terse", action="store_true", help="run the short-command suite")
    parser.add_argument(
        "--letter-case", action="store_true", help="sweep sector letters in both cases"
    )
    args = parser.parse_args()

    agent = build_agent()
    if args.letter_case:
        return run_letter_case_sweep(agent, args.threshold)

    cases = TERSE_CASES if args.terse else CASES
    passed = 0
    per_action: dict[str, list[int]] = {}
    for prompt, want_action, want_args in cases:
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
    print(f"{'TOTAL':>18}: {passed}/{len(cases)}")

    print()
    print("must keep escalating (goal-oriented):")
    leaked = 0
    for prompt in MUST_ESCALATE:
        decision = decide_route(run_single_command(agent, prompt), args.threshold)
        ok = decision.route is Route.CLOUD
        leaked += not ok
        print(f"  [{'ok ' if ok else 'LEAKED LOCAL'}] {prompt[:60]!r}")
    return 1 if leaked else 0


if __name__ == "__main__":
    raise SystemExit(main())
