"""Factory View: 2x3 sector card grid, cargo HP bar and mission status."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ..models import FactoryState, SectorKind, SimulationStatus, TemperatureStatus

# (gradient top, gradient bottom) per temperature band
_TEMP_GRADIENTS = {
    TemperatureStatus.COLD: ("#4180dd", "#2b57a8"),
    TemperatureStatus.SAFE: ("#31a468", "#1e7a4a"),
    TemperatureStatus.HOT: ("#dd5b5b", "#a83a3a"),
}

_KIND_ICONS = {
    SectorKind.START: "🏁",
    SectorKind.NORMAL: "❄",
    SectorKind.DOOR: "🚪",
    SectorKind.CONTAMINATED: "☣",
    SectorKind.GOAL: "🎯",
}

_KIND_LABELS = {
    SectorKind.START: "Start",
    SectorKind.NORMAL: "Cold zone",
    SectorKind.DOOR: "Hot / Door",
    SectorKind.CONTAMINATED: "Hazard",
    SectorKind.GOAL: "Goal",
}

# (label, pill background) per simulation status
_STATUS_PILLS = {
    SimulationStatus.RUNNING: ("RUNNING", "#39404d"),
    SimulationStatus.MISSION_SUCCESS: ("MISSION SUCCESS 🎉", "#1e7a4a"),
    SimulationStatus.GOAL_REACHED_CLEANUP_REQUIRED: (
        "GOAL REACHED · CLEANUP REQUIRED",
        "#9a7413",
    ),
    SimulationStatus.GAME_OVER: ("GAME OVER — CARGO DESTROYED", "#a83a3a"),
    SimulationStatus.EMERGENCY_STOPPED: ("EMERGENCY STOPPED", "#b35a1f"),
}

_ROBOT_BORDER = "#ffd54a"


class SectorCard(QFrame):
    def __init__(self, sector_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sector_id = sector_id
        self.setObjectName("sectorCard")
        self.setMinimumSize(170, 128)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self._title = QLabel()
        self._title.setStyleSheet("font-weight: bold; font-size: 14px; color: white;")
        self._band = QLabel()
        self._band.setStyleSheet(
            "background-color: rgba(0,0,0,0.35); color: white; font-size: 11px;"
            "font-weight: bold; border-radius: 8px; padding: 2px 8px;"
        )
        title_row.addWidget(self._title)
        title_row.addStretch(1)
        title_row.addWidget(self._band)

        temp_row = QHBoxLayout()
        temp_row.setSpacing(6)
        self._temp_big = QLabel()
        self._temp_big.setStyleSheet("font-size: 24px; font-weight: bold; color: white;")
        self._temp_target = QLabel()
        self._temp_target.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.85);")
        temp_row.addWidget(self._temp_big)
        temp_row.addWidget(self._temp_target)
        temp_row.addStretch(1)

        self._flags = QLabel()
        self._flags.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: rgba(255,255,255,0.95);"
        )
        self._flags.setWordWrap(True)

        self._robot = QLabel("🤖 ROBOT · CARGO")
        self._robot.setStyleSheet(
            "background-color: rgba(0,0,0,0.45); color: #ffe9a8; font-weight: bold;"
            "font-size: 12px; border-radius: 9px; padding: 3px 10px;"
        )
        self._robot.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addLayout(title_row)
        layout.addLayout(temp_row)
        layout.addWidget(self._flags)
        layout.addStretch(1)
        layout.addWidget(self._robot, alignment=Qt.AlignmentFlag.AlignLeft)

    def update_from(self, state: FactoryState) -> None:
        sector = state.sectors[self.sector_id]
        temp_state = sector.temperature_state
        top, bottom = _TEMP_GRADIENTS[temp_state]
        robot_here = state.robot_sector == self.sector_id
        border = (
            f"3px solid {_ROBOT_BORDER}" if robot_here else "1px solid rgba(255,255,255,0.14)"
        )
        self.setStyleSheet(
            "QFrame#sectorCard {"
            f" background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            f" stop:0 {top}, stop:1 {bottom});"
            f" border: {border}; border-radius: 10px;"
            "}"
        )
        self._title.setText(
            f"{_KIND_ICONS[sector.kind]} {sector.sector_id} · {_KIND_LABELS[sector.kind]}"
        )
        self._band.setText(temp_state.value)
        self._temp_big.setText(f"{sector.current_temperature:.0f}°C")
        transitioning = abs(sector.current_temperature - sector.target_temperature) >= 0.05
        arrow = (
            " ⬆" if sector.target_temperature > sector.current_temperature else " ⬇"
        ) if transitioning else ""
        self._temp_target.setText(f"→ target {sector.target_temperature:.0f}°C{arrow}")

        flags: list[str] = []
        if sector.kind is SectorKind.DOOR:
            flags.append("🚪 OPEN ✅" if sector.door_open else "🚪 CLOSED ⛔")
        if sector.kind is SectorKind.CONTAMINATED:
            if sector.needs_reset:
                flags.append("⚠ RESET REQUIRED")
            elif sector.used:
                flags.append("☣ in use")
            else:
                flags.append("☣ contaminated zone")
        self._flags.setText("   ".join(flags))
        self._robot.setVisible(robot_here)


class WallCard(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(170, 128)
        self.setStyleSheet(
            "background-color: #22252b; border: 2px dashed #3a4150; border-radius: 10px;"
        )
        layout = QVBoxLayout(self)
        label = QLabel("✕  Wall")
        label.setStyleSheet("font-weight: bold; color: #5b6270; border: none;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)


class FactoryView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(10)

        grid_holder = QWidget()
        grid = QGridLayout(grid_holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
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

        hp_row = QHBoxLayout()
        hp_row.setSpacing(8)
        hp_caption = QLabel("📦 Cargo")
        hp_caption.setStyleSheet("font-weight: bold;")
        self._hp_bar = QProgressBar()
        self._hp_bar.setRange(0, 100)
        self._hp_bar.setFormat("HP %v / 100")
        self._hp_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hp_row.addWidget(hp_caption)
        hp_row.addWidget(self._hp_bar, stretch=1)
        root.addLayout(hp_row)

        self._status_label = QLabel()
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._status_label)

    def update_from(self, state: FactoryState) -> None:
        for card in self._cards.values():
            card.update_from(state)

        # Round up while the cargo lives, so a sliver of HP never displays as 0
        # (and full HP is not shown until it really is full).
        hp = math.ceil(state.cargo_hp) if state.cargo_hp > 0 else 0
        self._hp_bar.setValue(hp)
        chunk = "#2fa066" if hp > 60 else ("#c99b2e" if hp > 30 else "#c94040")
        self._hp_bar.setStyleSheet(
            f"QProgressBar::chunk {{ background-color: {chunk}; border-radius: 6px; }}"
        )

        text, pill_bg = _STATUS_PILLS[state.status]
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"background-color: {pill_bg}; color: white; font-weight: bold;"
            "font-size: 14px; border-radius: 12px; padding: 6px 16px;"
        )
