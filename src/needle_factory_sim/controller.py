"""Deterministic FactoryController — the only component allowed to mutate FactoryState.

Every action validates against the live state and returns an ActionResult.
A rejected action never changes state.
"""

from __future__ import annotations

from .constants import (
    ADJACENCY,
    CARGO_DAMAGE_HP_PER_SECOND,
    CARGO_MAX_HP,
    TEMP_SETPOINT_MAX_C,
    TEMP_SETPOINT_MIN_C,
    TEMPERATURE_RATE_C_PER_SECOND,
)
from .models import (
    ActionResult,
    FactoryState,
    SectorKind,
    SimulationStatus,
    TemperatureStatus,
)


class FactoryController:
    def __init__(self) -> None:
        self.state = FactoryState.initial()

    # ------------------------------------------------------------------ guards

    def _reject(self, action: str, code: str, message: str) -> ActionResult:
        return ActionResult(
            accepted=False,
            action=action,
            state_changed=False,
            error_code=code,
            message=message,
        )

    def _guard_normal_action(self, action: str) -> ActionResult | None:
        """Common preconditions for every normal (non e-stop, non sim-reset) action."""
        if self.state.status is SimulationStatus.EMERGENCY_STOPPED:
            return self._reject(
                action, "EMERGENCY_STOPPED", "Simulation is emergency-stopped. Reset to continue."
            )
        if self.state.status is SimulationStatus.GAME_OVER:
            return self._reject(action, "GAME_OVER", "Cargo destroyed. Reset the simulation.")
        if self.state.cargo_hp <= 0:
            return self._reject(action, "CARGO_DESTROYED", "Cargo HP is 0.")
        return None

    # ------------------------------------------------------------------ actions

    def move_robot(self, target_sector: str) -> ActionResult:
        action = "move_robot"
        guard = self._guard_normal_action(action)
        if guard:
            return guard
        if target_sector not in self.state.sectors:
            return self._reject(action, "INVALID_SECTOR", f"Unknown sector '{target_sector}'.")
        current = self.state.robot_sector
        if target_sector == current:
            return self._reject(
                action, "NOT_ADJACENT", f"Robot is already in sector {current}."
            )
        if target_sector not in ADJACENCY[current]:
            return self._reject(
                action,
                "NOT_ADJACENT",
                f"Sector {target_sector} is not adjacent to current sector {current}.",
            )
        target = self.state.sectors[target_sector]
        if target.temperature_state is not TemperatureStatus.SAFE:
            return self._reject(
                action,
                "UNSAFE_TEMPERATURE",
                f"Sector {target_sector} temperature {target.current_temperature:.1f}°C "
                f"is {target.temperature_state.value}, not safe for cargo.",
            )
        if target.kind is SectorKind.DOOR and not target.door_open:
            return self._reject(
                action, "DOOR_CLOSED", f"Sector {target_sector} door is closed."
            )

        origin = self.state.sectors[current]
        if origin.kind is SectorKind.CONTAMINATED and origin.used:
            origin.needs_reset = True
        self.state.robot_sector = target_sector
        if target.kind is SectorKind.CONTAMINATED:
            target.used = True
        self._update_mission_status()
        return ActionResult(
            accepted=True,
            action=action,
            state_changed=True,
            message=f"Robot moved {current} → {target_sector}.",
            details={"robot_sector": target_sector, "status": self.state.status.value},
        )

    def set_temperature(self, sector_id: str, target_c: int) -> ActionResult:
        action = "set_temperature"
        guard = self._guard_normal_action(action)
        if guard:
            return guard
        if sector_id not in self.state.sectors:
            return self._reject(action, "INVALID_SECTOR", f"Unknown sector '{sector_id}'.")
        if not isinstance(target_c, (int, float)) or isinstance(target_c, bool):
            return self._reject(action, "INVALID_TEMPERATURE", "Target temperature must be a number.")
        if not (TEMP_SETPOINT_MIN_C <= target_c <= TEMP_SETPOINT_MAX_C):
            return self._reject(
                action,
                "INVALID_TEMPERATURE",
                f"Target {target_c}°C outside allowed range "
                f"{TEMP_SETPOINT_MIN_C}–{TEMP_SETPOINT_MAX_C}°C.",
            )
        sector = self.state.sectors[sector_id]
        sector.target_temperature = float(target_c)
        return ActionResult(
            accepted=True,
            action=action,
            state_changed=True,
            message=f"Sector {sector_id} target temperature set to {target_c}°C "
            f"(current {sector.current_temperature:.1f}°C, transitioning gradually).",
            details={"sector_id": sector_id, "target_temperature": float(target_c)},
        )

    def toggle_door(self, sector_id: str, open: bool) -> ActionResult:  # noqa: A002
        action = "toggle_door"
        guard = self._guard_normal_action(action)
        if guard:
            return guard
        sector = self.state.sectors.get(sector_id)
        if sector is None or sector.kind is not SectorKind.DOOR:
            return self._reject(action, "INVALID_SECTOR", f"Sector '{sector_id}' has no door.")
        sector.door_open = bool(open)
        return ActionResult(
            accepted=True,
            action=action,
            state_changed=True,
            message=f"Sector {sector_id} door is now {'OPEN' if open else 'CLOSED'}.",
            details={"sector_id": sector_id, "door_open": bool(open)},
        )

    def reset_sector(self, sector_id: str) -> ActionResult:
        action = "reset_sector"
        guard = self._guard_normal_action(action)
        if guard:
            return guard
        sector = self.state.sectors.get(sector_id)
        if sector is None or sector.kind is not SectorKind.CONTAMINATED:
            return self._reject(
                action, "INVALID_SECTOR", f"Sector '{sector_id}' is not a resettable sector."
            )
        if self.state.robot_sector == sector_id:
            return self._reject(
                action, "RESET_WHILE_INSIDE", f"Robot is inside sector {sector_id}."
            )
        if not sector.needs_reset:
            return self._reject(
                action, "RESET_NOT_REQUIRED", f"Sector {sector_id} does not need a reset."
            )
        sector.used = False
        sector.needs_reset = False
        self._update_mission_status()
        return ActionResult(
            accepted=True,
            action=action,
            state_changed=True,
            message=f"Sector {sector_id} contamination reset.",
            details={"sector_id": sector_id, "status": self.state.status.value},
        )

    def emergency_stop(self) -> ActionResult:
        action = "emergency_stop"
        if self.state.status is SimulationStatus.EMERGENCY_STOPPED:
            return self._reject(
                action, "EMERGENCY_STOPPED", "Simulation is already emergency-stopped."
            )
        self.state.status = SimulationStatus.EMERGENCY_STOPPED
        return ActionResult(
            accepted=True,
            action=action,
            state_changed=True,
            message="EMERGENCY STOP. Simulation halted; reset to continue.",
            details={"status": self.state.status.value},
        )

    def reset_simulation(self) -> ActionResult:
        self.state = FactoryState.initial()
        return ActionResult(
            accepted=True,
            action="reset_simulation",
            state_changed=True,
            message="Simulation reset to initial state.",
            details={"status": self.state.status.value},
        )

    # ------------------------------------------------------------------ time

    def advance_time(self, elapsed_seconds: float) -> None:
        """Advance temperature transitions and cargo damage by real elapsed time."""
        if elapsed_seconds <= 0:
            return
        if self.state.status is SimulationStatus.EMERGENCY_STOPPED:
            return
        max_delta = TEMPERATURE_RATE_C_PER_SECOND * elapsed_seconds
        for sector in self.state.sectors.values():
            diff = sector.target_temperature - sector.current_temperature
            if diff:
                step = min(abs(diff), max_delta)
                sector.current_temperature += step if diff > 0 else -step

        if self.state.cargo_hp > 0:
            robot_sector = self.state.sectors[self.state.robot_sector]
            if robot_sector.temperature_state is not TemperatureStatus.SAFE:
                self.state.cargo_hp = max(
                    0.0, self.state.cargo_hp - CARGO_DAMAGE_HP_PER_SECOND * elapsed_seconds
                )
                if self.state.cargo_hp <= 0:
                    self.state.status = SimulationStatus.GAME_OVER

    # ------------------------------------------------------------------ status

    def _update_mission_status(self) -> None:
        if self.state.status in (
            SimulationStatus.EMERGENCY_STOPPED,
            SimulationStatus.GAME_OVER,
        ):
            return
        if self.state.cargo_hp <= 0:
            self.state.status = SimulationStatus.GAME_OVER
            return
        goal = next(
            s for s in self.state.sectors.values() if s.kind is SectorKind.GOAL
        )
        if self.state.robot_sector == goal.sector_id:
            pending_reset = any(
                s.needs_reset for s in self.state.sectors.values()
                if s.kind is SectorKind.CONTAMINATED
            )
            self.state.status = (
                SimulationStatus.GOAL_REACHED_CLEANUP_REQUIRED
                if pending_reset
                else SimulationStatus.MISSION_SUCCESS
            )
        else:
            self.state.status = SimulationStatus.RUNNING

    # ------------------------------------------------------------------ misc

    @property
    def cargo_max_hp(self) -> float:
        return CARGO_MAX_HP
