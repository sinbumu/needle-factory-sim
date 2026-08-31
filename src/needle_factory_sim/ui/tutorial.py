"""First-launch tutorial: coach-mark overlay that dims the window and walks
through the real widgets one by one. Shown automatically only on the very
first launch (QSettings flag); afterwards only via the Tutorial button.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass
class TutorialStep:
    widget: QWidget
    title: str
    body: str


class TutorialOverlay(QWidget):
    """Semi-transparent overlay with a cutout around the current step's widget."""

    finished = Signal()

    def __init__(self, parent: QWidget, steps: list[TutorialStep]) -> None:
        super().__init__(parent)
        self._steps = steps
        self._index = 0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        parent.installEventFilter(self)

        self._card = QFrame(self)
        self._card.setObjectName("tutorialCard")
        self._card.setStyleSheet(
            "QFrame#tutorialCard { background-color: #232730; border: 1px solid #4f8cff;"
            " border-radius: 10px; }"
        )
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(6)
        # Fixed-width wrapped body + SetFixedSize lets the layout compute the
        # true wrapped height, so long step texts are never clipped.
        card_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        self._title = QLabel()
        self._title.setStyleSheet("font-weight: bold; font-size: 14px; color: #e8eaf0;")
        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setFixedWidth(312)
        self._body.setStyleSheet("color: #c6cdd9; font-size: 13px;")
        self._counter = QLabel()
        self._counter.setStyleSheet("color: #9aa3b2; font-size: 11px;")

        buttons = QHBoxLayout()
        self._skip_btn = QPushButton("Skip")
        self._back_btn = QPushButton("Back")
        self._next_btn = QPushButton("Next")
        self._next_btn.setObjectName("executeButton")  # accent style from theme
        buttons.addWidget(self._skip_btn)
        buttons.addStretch(1)
        buttons.addWidget(self._back_btn)
        buttons.addWidget(self._next_btn)

        card_layout.addWidget(self._title)
        card_layout.addWidget(self._body)
        card_layout.addWidget(self._counter)
        card_layout.addLayout(buttons)

        self._skip_btn.clicked.connect(self._finish)
        self._back_btn.clicked.connect(self._back)
        self._next_btn.clicked.connect(self._next)

    # ------------------------------------------------------------------ flow

    def start(self) -> None:
        self._index = 0
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.setFocus()
        self._apply_step()

    def _finish(self) -> None:
        self.hide()
        self.finished.emit()

    def _next(self) -> None:
        if self._index >= len(self._steps) - 1:
            self._finish()
            return
        self._index += 1
        self._apply_step()

    def _back(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._apply_step()

    def _apply_step(self) -> None:
        step = self._steps[self._index]
        self._title.setText(step.title)
        self._body.setText(step.body)
        self._counter.setText(f"Step {self._index + 1} / {len(self._steps)}")
        self._back_btn.setEnabled(self._index > 0)
        self._next_btn.setText("Done" if self._index == len(self._steps) - 1 else "Next")
        self._card.adjustSize()
        self._place_card()
        self.update()

    # ------------------------------------------------------------------ layout

    def _target_rect(self) -> QRect:
        widget = self._steps[self._index].widget
        if not widget.isVisible() or widget.width() <= 0 or widget.height() <= 0:
            # Nothing sensible to spotlight — highlight nothing rather than
            # cutting a bogus hole out of the overlay.
            return QRect()
        top_left = widget.mapTo(self.parentWidget(), QPoint(0, 0))
        return QRect(top_left, widget.size()).adjusted(-6, -6, 6, 6)

    def _place_card(self) -> None:
        target = self._target_rect()
        margin = 12
        card = self._card
        card.adjustSize()
        w, h = card.width(), card.height()
        # Prefer below the target, then above, then beside; clamp to overlay.
        x = min(max(target.left(), margin), self.width() - w - margin)
        if target.bottom() + margin + h <= self.height():
            y = target.bottom() + margin
        elif target.top() - margin - h >= 0:
            y = target.top() - margin - h
        else:
            y = max(margin, (self.height() - h) // 2)
            if target.right() + margin + w <= self.width():
                x = target.right() + margin
            elif target.left() - margin - w >= 0:
                x = target.left() - margin - w
        card.move(int(x), int(y))

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.parentWidget() and event.type() == QEvent.Type.Resize and self.isVisible():
            self.setGeometry(self.parentWidget().rect())
            self._place_card()
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------ paint

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        overlay_path = QPainterPath()
        overlay_path.addRect(self.rect())
        target = self._target_rect()
        if target.isNull():
            painter.fillPath(overlay_path, QColor(0, 0, 0, 170))
            return
        cutout = QPainterPath()
        cutout.addRoundedRect(target, 8, 8)
        painter.fillPath(overlay_path.subtracted(cutout), QColor(0, 0, 0, 170))
        painter.setPen(QPen(QColor("#4f8cff"), 2))
        painter.drawRoundedRect(target, 8, 8)

    # ------------------------------------------------------------------ input

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._finish()
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._next()
        elif event.key() == Qt.Key.Key_Left:
            self._back()
        elif event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            # Keep focus inside the tour: tabbing through to the controls
            # underneath would let them be activated blind.
            event.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        # Swallow clicks so the UI underneath is not triggered mid-tutorial.
        event.accept()
