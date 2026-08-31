"""Fixed factory map, physics constants and routing defaults."""

from __future__ import annotations

SECTOR_IDS = ("S", "A", "B", "C", "E")

# Bidirectional adjacency of the fixed 2x3 map (X is a wall and does not exist).
ADJACENCY: dict[str, frozenset[str]] = {
    "S": frozenset({"A"}),
    "A": frozenset({"S", "B", "C"}),
    "B": frozenset({"A", "E"}),
    "C": frozenset({"A", "E"}),
    "E": frozenset({"B", "C"}),
}

INITIAL_TEMPERATURES: dict[str, float] = {
    "S": 30.0,
    "A": 10.0,
    "B": 55.0,
    "C": 50.0,
    "E": 30.0,
}

SAFE_TEMP_MIN_C = 20.0
SAFE_TEMP_MAX_C = 40.0
TEMPERATURE_RATE_C_PER_SECOND = 10.0
CARGO_DAMAGE_HP_PER_SECOND = 10.0
CARGO_MAX_HP = 100.0

TEMP_SETPOINT_MIN_C = 0
TEMP_SETPOINT_MAX_C = 60

SIMULATION_TICK_MS = 100
# Upper bound on the time a single tick may apply. Guards against clock jumps
# (system suspend/resume) turning one tick into hours of simulated damage.
MAX_TICK_ELAPSED_S = 0.25
EXECUTOR_VISUAL_STEP_DELAY_MS = 400

DEFAULT_CONFIDENCE_THRESHOLD = 0.75

PLAN_MAX_STEPS = 8
PLAN_MAX_SINGLE_WAIT_S = 10
PLAN_MAX_TOTAL_WAIT_S = 15

LOCAL_ACTION_WHITELIST = frozenset(
    {"move_robot", "set_temperature", "toggle_door", "reset_sector", "emergency_stop"}
)
CLOUD_ACTION_WHITELIST = frozenset(
    {"move_robot", "set_temperature", "toggle_door", "reset_sector", "wait"}
)

CLOUD_REQUEST_TIMEOUT_S = 20.0

# Korean demo prompts (original spec). Spike measurement 2026-08-28 showed the
# Needle 2 base model is unstable on Korean (confidence 0.00–0.21, wrong sector),
# so the demo buttons use the English fallback prompts per PLAN §56.
DEMO_PROMPTS_KR = {
    "A": "A 구역 온도를 30도로 맞춰",
    "B": "E 구역으로 바로 이동해",
    "C": (
        "현재 공장 상태를 직접 판단해서 필요한 작업들을 올바른 순서로 수행하고, "
        "화물이 손상되지 않도록 E 구역까지 안전하게 운송해줘."
    ),
}

DEMO_PROMPTS = {
    "A": "Set sector A temperature to 30 degrees.",
    "B": "Move the robot directly to sector E.",
    "C": (
        "Inspect the current factory state, determine the required actions and their "
        "safe order, and transport the cargo to sector E without damage."
    ),
}
