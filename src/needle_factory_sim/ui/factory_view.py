"""Factory View: 2x3 sector card grid, cargo HP bar and mission status."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ..models import FactoryState, SectorKind, SimulationStatus, TemperatureStatus

_TEMP_COLORS = {
    TemperatureStatus.COLD: "#3b6fd4",
    TemperatureStatus.SAFE: "#2f8f4e",
    TemperatureStatus.HOT: "#c43d3d",
}

_KIND_LABELS = {
    SectorKind.START: "Start",
    SectorKind.NORMAL: "Cold zone",
    SectorKind.DOOR: "Hot / Door",
    SectorKind.CONTAMINATED: "Hazard",
    SectorKind.GOAL: "Goal",
}

_STATUS_LABELS = {
    SimulationStatus.RUNNING: ("RUNNING", "#444444"),
    SimulationStatus.MISSION_SUCCESS: ("MISSION SUCCESS", "#1e7c35"),
    SimulationStatus.GOAL_REACHED_CLEANUP_REQUIRED: (
        "GOAL REACHED / CLEANUP REQUIRED",
        "#b8860b",
    ),
    SimulationStatus.GAME_OVER: ("GAME OVER — cargo destroyed", "#b02a2a"),
    SimulationStatus.EMERGENCY_STOPPED: ("EMERGENCY STOPPED", "#c05a1a"),
}


class SectorCard(QFrame):
    def __init__(self, sector_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sector_id = sector_id
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumSize(150, 110)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        self._title = QLabel()
        self._title.setStyleSheet("font-weight: bold; font-size: 14px; color: white;")
        self._temp = QLabel()
        self._temp.setStyleSheet("color: white;")
        self._flags = QLabel()
        self._flags.setStyleSheet("color: white;")
        self._flags.setWordWrap(True)
        self._robot = QLabel()
        self._robot.setStyleSheet("font-weight: bold; font-size: 13px; color: white;")
        for w in (self._title, self._temp, self._flags, self._robot):
            layout.addWidget(w)
        layout.addStretch(1)

    def update_from(self, state: FactoryState) -> None:
        sector = state.sectors[self.sector_id]
        temp_state = sector.temperature_state
        color = _TEMP_COLORS[temp_state]
        self.setStyleSheet(
            f"SectorCard {{ background-color: {color}; border-radius: 6px; }}"
        )
        self._title.setText(f"{sector.sector_id} — {_KIND_LABELS[sector.kind]}")
        self._temp.setText(
            f"{sector.current_temperature:.0f}°C → target {sector.target_temperature:.0f}°C"
            f"  [{temp_state.value}]"
        )
        flags: list[str] = []
        if sector.kind is SectorKind.DOOR:
            flags.append("Door: OPEN" if sector.door_open else "Door: CLOSED")
        if sector.kind is SectorKind.CONTAMINATED:
            if sector.needs_reset:
                flags.append("⚠ RESET REQUIRED")
            elif sector.used:
                flags.append("used")
            else:
                flags.append("contaminated zone")
        self._flags.setText("  ".join(flags))
        self._robot.setText("🤖 ROBOT + CARGO" if state.robot_sector == self.sector_id else "")


class WallCard(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumSize(150, 110)
        self.setStyleSheet("background-color: #555555; border-radius: 6px;")
        layout = QVBoxLayout(self)
        label = QLabel("X — Wall")
        label.setStyleSheet("font-weight: bold; color: #bbbbbb;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)


class FactoryView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        grid_holder = QWidget()
        grid = QGridLayout(grid_holder)
        grid.setSpacing(8)
        self._cards: dict[str, SectorCard] = {}
        # Fixed map: row 0 = S A B, row 1 = X C E
        for col, sid in enumerate(("S", "A", "B")):
            card = SectorCard(sid)
            self._cards[sid] = card
            grid.addWidget(card, 0, col)
        grid.addWidget(WallCard(), 1, 0)
        for col, sid in enumerate(("C", "E"), start=1):
            card = SectorCard(sid)
            self._cards[sid] = card
            grid.addWidget(card, 1, col)
        root.addWidget(grid_holder)

        self._hp_bar = QProgressBar()
        self._hp_bar.setRange(0, 100)
        self._hp_bar.setFormat("Cargo HP: %v / 100")
        root.addWidget(self._hp_bar)

        self._status_label = QLabel()
        self._status_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        root.addWidget(self._status_label)
        root.addStretch(1)

    def update_from(self, state: FactoryState) -> None:
        for card in self._cards.values():
            card.update_from(state)
        self._hp_bar.setValue(round(state.cargo_hp))
        text, color = _STATUS_LABELS[state.status]
        self._status_label.setText(f"Simulation: {text}")
        self._status_label.setStyleSheet(
            f"font-weight: bold; font-size: 14px; color: {color};"
        )
