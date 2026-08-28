from needle_factory_sim.ai.needle_adapter import NeedleResult
from needle_factory_sim.ai.router import Route, decide_route

THRESHOLD = 0.75


def result(**kwargs) -> NeedleResult:
    base = dict(
        type="call",
        success=True,
        confidence=0.9,
        function_calls=[{"name": "move_robot", "arguments": {"target_sector": "A"}}],
    )
    base.update(kwargs)
    return NeedleResult(**base)


def test_high_confidence_single_call_routes_local():
    decision = decide_route(result(), THRESHOLD)
    assert decision.route is Route.LOCAL
    assert decision.action == "move_robot"
    assert decision.arguments == {"target_sector": "A"}


def test_low_confidence_routes_cloud():
    decision = decide_route(result(confidence=0.5), THRESHOLD)
    assert decision.route is Route.CLOUD


def test_missing_confidence_routes_cloud():
    decision = decide_route(result(confidence=None), THRESHOLD)
    assert decision.route is Route.CLOUD


def test_empty_calls_routes_cloud():
    decision = decide_route(result(function_calls=[]), THRESHOLD)
    assert decision.route is Route.CLOUD


def test_multiple_calls_routes_cloud():
    calls = [
        {"name": "move_robot", "arguments": {"target_sector": "A"}},
        {"name": "move_robot", "arguments": {"target_sector": "B"}},
    ]
    decision = decide_route(result(function_calls=calls), THRESHOLD)
    assert decision.route is Route.CLOUD


def test_inference_error_routes_cloud():
    decision = decide_route(
        NeedleResult(success=False, error="token budget exhausted"), THRESHOLD
    )
    assert decision.route is Route.CLOUD


def test_unknown_action_routes_cloud():
    calls = [{"name": "self_destruct", "arguments": {}}]
    decision = decide_route(result(function_calls=calls), THRESHOLD)
    assert decision.route is Route.CLOUD


def test_invalid_arguments_route_cloud():
    calls = [{"name": "move_robot", "arguments": {"target_sector": "X"}}]
    decision = decide_route(result(function_calls=calls), THRESHOLD)
    assert decision.route is Route.CLOUD


def test_out_of_range_temperature_routes_cloud():
    calls = [{"name": "set_temperature", "arguments": {"sector_id": "A", "target_c": 99}}]
    decision = decide_route(result(function_calls=calls), THRESHOLD)
    assert decision.route is Route.CLOUD


def test_confidence_exactly_threshold_routes_local():
    decision = decide_route(result(confidence=0.75), THRESHOLD)
    assert decision.route is Route.LOCAL


def test_from_raw_tolerates_missing_and_garbage_fields():
    parsed = NeedleResult.from_raw({"function_calls": "oops", "confidence": "high"})
    assert parsed.function_calls == []
    assert parsed.confidence is None
    decision = decide_route(parsed, THRESHOLD)
    assert decision.route is Route.CLOUD
