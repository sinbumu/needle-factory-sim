"""Go/No-Go spike: run real Needle 2 inference on the three demo prompts.

Usage:
    uv run python scripts/needle_spike.py [--runs 3] [--english] [--threshold 0.75]

Prints confidence / function_calls / route decision per run so the AUTO routing
behaviour is measured, not assumed.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from needle_factory_sim.ai.needle_adapter import build_agent, run_single_command
from needle_factory_sim.ai.router import decide_route
from needle_factory_sim.constants import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEMO_PROMPTS as ENGLISH_PROMPTS,
    DEMO_PROMPTS_KR as DEMO_PROMPTS,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--english", action="store_true")
    parser.add_argument("--threshold", type=float, default=DEFAULT_CONFIDENCE_THRESHOLD)
    args = parser.parse_args()

    prompts = ENGLISH_PROMPTS if args.english else DEMO_PROMPTS
    lang = "EN" if args.english else "KR"

    print("Initializing Needle engine (first run may download the engine)...")
    t0 = time.monotonic()
    agent = build_agent()
    print(f"Needle ready in {time.monotonic() - t0:.1f}s\n")

    rows = []
    for demo, prompt in prompts.items():
        for run in range(1, args.runs + 1):
            result = run_single_command(agent, prompt)
            decision = decide_route(result, args.threshold)
            calls = [
                f"{c.get('name')}({c.get('arguments')})" for c in result.function_calls
            ]
            conf = f"{result.confidence:.2f}" if result.confidence is not None else "None"
            print(f"DEMO {demo} ({lang}) / RUN {run}")
            print(f"  confidence={conf}")
            print(f"  calls={calls or '[]'}")
            print(f"  route={decision.route.value}  ({decision.reason})")
            print(
                f"  success={result.success} error={result.error} "
                f"prefill_tps={result.prefill_tps} decode_tps={result.decode_tps} "
                f"peak_ram_mb={result.peak_ram_mb} latency={result.latency_s:.2f}s"
            )
            if result.reasoning:
                print(f"  reasoning={str(result.reasoning)[:200]}")
            print()
            rows.append((demo, lang, run, conf, ";".join(calls) or "[]", decision.route.value))

    print("SUMMARY (Demo / Lang / Run / Confidence / Calls / Route)")
    for row in rows:
        print("  " + " / ".join(str(x) for x in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
