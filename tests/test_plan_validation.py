import pytest
from pydantic import ValidationError

from needle_factory_sim.models import ExecutionPlan


def step(order: int, action: str, arguments: dict, reason: str = "r") -> dict:
    return {"order": order, "action": action, "arguments": arguments, "reason": reason}


def valid_plan_dict() -> dict:
    return {
        "status": "ready",
        "summary": "safe route via B",
        "steps": [
            step(1, "set_temperature", {"sector_id": "A", "target_c": 30}),
            step(2, "set_temperature", {"sector_id": "B", "target_c": 30}),
            step(3, "wait", {"seconds": 3}),
            step(4, "toggle_door", {"sector_id": "B", "open": True}),
            step(5, "move_robot", {"target_sector": "A"}),
            step(6, "move_robot", {"target_sector": "B"}),
            step(7, "move_robot", {"target_sector": "E"}),
        ],
    }


def test_valid_plan_accepted():
    plan = ExecutionPlan.model_validate(valid_plan_dict())
    assert plan.status == "ready"
    assert len(plan.steps) == 7


def test_unknown_action_rejected():
    data = valid_plan_dict()
    data["steps"][0]["action"] = "emergency_stop"
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(data)


def test_wrong_enum_rejected():
    data = valid_plan_dict()
    data["steps"][4]["arguments"]["target_sector"] = "X"
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(data)


def test_more_than_eight_steps_rejected():
    data = valid_plan_dict()
    data["steps"] += [
        step(8, "wait", {"seconds": 1}),
        step(9, "wait", {"seconds": 1}),
    ]
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(data)


def test_single_wait_over_ten_rejected():
    data = valid_plan_dict()
    data["steps"][2]["arguments"]["seconds"] = 11
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(data)


def test_total_wait_over_fifteen_rejected():
    data = valid_plan_dict()
    data["steps"][2]["arguments"]["seconds"] = 8
    data["steps"].insert(3, step(4, "wait", {"seconds": 8}))
    for i, s in enumerate(data["steps"], start=1):
        s["order"] = i
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(data)


def test_non_contiguous_order_rejected():
    data = valid_plan_dict()
    data["steps"][3]["order"] = 9
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(data)


def test_duplicate_order_rejected():
    data = valid_plan_dict()
    data["steps"][1]["order"] = 1
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(data)


def test_extra_field_rejected():
    data = valid_plan_dict()
    data["confidence"] = 0.9
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(data)


def test_extra_argument_field_rejected():
    data = valid_plan_dict()
    data["steps"][0]["arguments"]["mode"] = "fast"
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(data)


def test_ready_with_empty_steps_rejected():
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate({"status": "ready", "summary": "s", "steps": []})


def test_cannot_plan_with_steps_rejected():
    data = valid_plan_dict()
    data["status"] = "cannot_plan"
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate(data)


def test_cannot_plan_with_empty_steps_accepted():
    plan = ExecutionPlan.model_validate(
        {"status": "cannot_plan", "summary": "no safe route", "steps": []}
    )
    assert plan.status == "cannot_plan"
