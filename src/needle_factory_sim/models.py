"""Factory state models, controller result model, and the Cloud ExecutionPlan schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .constants import (
    CARGO_MAX_HP,
    INITIAL_TEMPERATURES,
    PLAN_MAX_SINGLE_WAIT_S,
    PLAN_MAX_STEPS,
    PLAN_MAX_TOTAL_WAIT_S,
    SAFE_TEMP_MAX_C,
    SAFE_TEMP_MIN_C,
    TEMP_SETPOINT_MAX_C,
    TEMP_SETPOINT_MIN_C,
)

SectorId = Literal["S", "A", "B", "C", "E"]


class SectorKind(str, Enum):
    START = "START"
    NORMAL = "NORMAL"
    DOOR = "DOOR"
    CONTAMINATED = "CONTAMINATED"
    GOAL = "GOAL"


class TemperatureStatus(str, Enum):
    COLD = "COLD"
    SAFE = "SAFE"
    HOT = "HOT"


class SimulationStatus(str, Enum):
    RUNNING = "RUNNING"
    MISSION_SUCCESS = "MISSION_SUCCESS"
    GOAL_REACHED_CLEANUP_REQUIRED = "GOAL_REACHED_CLEANUP_REQUIRED"
    GAME_OVER = "GAME_OVER"
    EMERGENCY_STOPPED = "EMERGENCY_STOPPED"


def temperature_status(current_c: float) -> TemperatureStatus:
    if current_c < SAFE_TEMP_MIN_C:
        return TemperatureStatus.COLD
    if current_c > SAFE_TEMP_MAX_C:
        return TemperatureStatus.HOT
    return TemperatureStatus.SAFE


SECTOR_KINDS: dict[str, SectorKind] = {
    "S": SectorKind.START,
    "A": SectorKind.NORMAL,
    "B": SectorKind.DOOR,
    "C": SectorKind.CONTAMINATED,
    "E": SectorKind.GOAL,
}


@dataclass
class SectorState:
    sector_id: str
    kind: SectorKind
    current_temperature: float
    target_temperature: float
    door_open: bool | None = None  # only meaningful for DOOR sectors
    used: bool = False  # only meaningful for CONTAMINATED sectors
    needs_reset: bool = False  # only meaningful for CONTAMINATED sectors

    @property
    def temperature_state(self) -> TemperatureStatus:
        return temperature_status(self.current_temperature)


@dataclass
class FactoryState:
    sectors: dict[str, SectorState] = field(default_factory=dict)
    robot_sector: str = "S"
    cargo_hp: float = CARGO_MAX_HP
    status: SimulationStatus = SimulationStatus.RUNNING

    @classmethod
    def initial(cls) -> "FactoryState":
        sectors = {
            sid: SectorState(
                sector_id=sid,
                kind=SECTOR_KINDS[sid],
                current_temperature=INITIAL_TEMPERATURES[sid],
                target_temperature=INITIAL_TEMPERATURES[sid],
                door_open=False if SECTOR_KINDS[sid] is SectorKind.DOOR else None,
            )
            for sid in INITIAL_TEMPERATURES
        }
        return cls(sectors=sectors)


class ActionResult(BaseModel):
    accepted: bool
    action: str
    state_changed: bool
    error_code: str | None = None
    message: str
    details: dict[str, Any] | None = None


# --------------------------------------------------------------------------
# Cloud ExecutionPlan schema (strict, typed, extra=forbid)
# --------------------------------------------------------------------------


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MoveRobotArgs(_StrictModel):
    target_sector: SectorId


class SetTemperatureArgs(_StrictModel):
    sector_id: SectorId
    target_c: int = Field(ge=TEMP_SETPOINT_MIN_C, le=TEMP_SETPOINT_MAX_C)


class ToggleDoorArgs(_StrictModel):
    sector_id: Literal["B"]
    open: bool


class ResetSectorArgs(_StrictModel):
    sector_id: Literal["C"]


class WaitArgs(_StrictModel):
    seconds: int = Field(ge=1, le=PLAN_MAX_SINGLE_WAIT_S)


class MoveRobotStep(_StrictModel):
    order: int = Field(ge=1)
    action: Literal["move_robot"]
    arguments: MoveRobotArgs
    reason: str


class SetTemperatureStep(_StrictModel):
    order: int = Field(ge=1)
    action: Literal["set_temperature"]
    arguments: SetTemperatureArgs
    reason: str


class ToggleDoorStep(_StrictModel):
    order: int = Field(ge=1)
    action: Literal["toggle_door"]
    arguments: ToggleDoorArgs
    reason: str


class ResetSectorStep(_StrictModel):
    order: int = Field(ge=1)
    action: Literal["reset_sector"]
    arguments: ResetSectorArgs
    reason: str


class WaitStep(_StrictModel):
    order: int = Field(ge=1)
    action: Literal["wait"]
    arguments: WaitArgs
    reason: str


PlanStep = Annotated[
    Union[MoveRobotStep, SetTemperatureStep, ToggleDoorStep, ResetSectorStep, WaitStep],
    Field(discriminator="action"),
]


class ExecutionPlan(_StrictModel):
    status: Literal["ready", "cannot_plan"]
    summary: str
    steps: list[PlanStep]

    @model_validator(mode="after")
    def _check_plan_rules(self) -> "ExecutionPlan":
        if self.status == "cannot_plan":
            if self.steps:
                raise ValueError("cannot_plan requires an empty steps array")
            return self
        if not self.steps:
            raise ValueError("ready plan requires at least one step")
        if len(self.steps) > PLAN_MAX_STEPS:
            raise ValueError(f"plan exceeds max steps ({PLAN_MAX_STEPS})")
        orders = [step.order for step in self.steps]
        if orders != list(range(1, len(orders) + 1)):
            raise ValueError("step order must be contiguous starting at 1 with no duplicates")
        total_wait = sum(
            step.arguments.seconds for step in self.steps if isinstance(step, WaitStep)
        )
        if total_wait > PLAN_MAX_TOTAL_WAIT_S:
            raise ValueError(f"total wait exceeds {PLAN_MAX_TOTAL_WAIT_S} seconds")
        return self
