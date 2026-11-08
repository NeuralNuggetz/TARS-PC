"""TARS overlay: a small always-on-top pill at the top-center of the screen.

Collapsed : a slim rounded slab with TARS' four articulated segments, the name,
            and the current state (standby / listening / thinking / speaking).
Expanded  : the slab grows downward into a panel showing text (news, answers).
            It collapses by itself, on click, or when you say "hide that".

Qt needs the main thread, so the assistant runs in a worker thread and talks to
the window only through UiController's signals (thread safe).
"""
import html
import math
import re
import time

from PySide6.QtCore import (
    QEasingCurve, QObject, QPointF, QPropertyAnimation, QRect, QRectF, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QGuiApplication, QLinearGradient, QPainter,
    QPainterPath, QPen, QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QTextBrowser, QWidget

# ---- sizes (pixels) ----
MARGIN = 12          # transparent room around the card for the shadow
PILL_W, PILL_H = 228, 40
PANEL_W = 460
HEADER_H = 40
PADDING = 18
MAX_BODY_H = 260
RADIUS = 13

# state -> (label, accent colour)
STATES = {
    "idle": ("STANDBY", "#7b8494"),
    "listening": ("LISTENING", "#4cc9f0"),
    "thinking": ("THINKING", "#ffb454"),
    "speaking": ("SPEAKING", "#7ee2a8"),
}


def _pick_font() -> str:
    families = set(QFontDatabase.families())
    for name in ("Bahnschrift", "Segoe UI Variable Display", "Segoe UI"):
        if name in families:
            return name
    return QGuiApplication.font().family()


def format_body(title: str, text: str, accent: str) -> str:
    """Plain text -> small rich-text document. Lines starting with '- ' become bullets."""
    parts = []
    if title:
        parts.append(
            f"<div style='font-size:13pt; font-weight:600; color:#ffffff; "
            f"margin-bottom:6px;'>{html.escape(title)}</div>"
        )
    for raw in text.strip().splitlines():
        line = raw.strip()
        if not line:
            parts.append("<div style='height:6px;'></div>")
            continue
        bullet = re.match(r"^[-*•]\s+(.*)$", line)
        if bullet:
            parts.append(
                f"<div style='margin:5px 0;'><span style='color:{accent};'>&#9656;</span>"
                f"&nbsp;&nbsp;{html.escape(bullet.group(1))}</div>"
            )
        else:
            parts.append(f"<div style='margin:5px 0;'>{html.escape(line)}</div>")
    return "<body style='color:#cfd5de; font-size:10.5pt;'>" + "".join(parts) + "</body>"


class UiController(QObject):
    """Thread-safe handle the assistant thread uses to drive the window."""

    stateChanged = Signal(str)
    textRequested = Signal(str, str)
    collapseRequested = Signal()
    quitRequested = Signal()

    def set_state(self, state: str):
        self.stateChanged.emit(state)

    def show_text(self, title: str, text: str):
        self.textRequested.emit(title, text)

    def collapse(self):
        self.collapseRequested.emit()

    def quit(self):
        self.quitRequested.emit()


class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._font = _pick_font()
        self._state = "idle"
        self._expanded = False
        self._title = ""
        self._text = ""
        self._t0 = time.time()

        # text area (child widget, shown only when expanded)
        self.body = QTextBrowser(self)
        self.body.setFocusPolicy(Qt.NoFocus)
        self.body.setFrameShape(QTextBrowser.NoFrame)
        self.body.setOpenLinks(False)
        self.body.viewport().setAutoFillBackground(False)
        self.body.setStyleSheet(
            "QTextBrowser { background: transparent; border: none; color: #cfd5de;"
            " selection-background-color: rgba(76,201,240,90); }"
            "QScrollBar:vertical { background: transparent; width: 6px; margin: 0; }"
            "QScrollBar::handle:vertical { background: rgba(255,255,255,55);"
            " border-radius: 3px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )
        body_font = QFont("Segoe UI", 10)
        self.body.setFont(body_font)
        self.body.hide()

        # animations
        self._grow = QPropertyAnimation(self, b"geometry")
        self._grow.setDuration(300)
        self._grow.setEasingCurve(QEasingCurve.OutCubic)
        self._grow.finished.connect(self._after_grow)

        self._auto_hide = QTimer(self)
        self._auto_hide.setSingleShot(True)
        self._auto_hide.timeout.connect(self.collapse)

        self._frames = QTimer(self)          # drives the segment animation
        self._frames.setInterval(33)
        self._frames.timeout.connect(self.update)
        self._frames.start()

        self.setGeometry(self._outer_rect(False))

    # ---------- geometry ----------
    def _outer_rect(self, expanded: bool, body_h: int = 0) -> QRect:
        card_w = PANEL_W if expanded else PILL_W
        card_h = HEADER_H + 6 + body_h + 14 if expanded else PILL_H
        w, h = card_w + 2 * MARGIN, card_h + 2 * MARGIN
        screen = QGuiApplication.primaryScreen().availableGeometry()
        return QRect(screen.x() + (screen.width() - w) // 2, screen.y(), w, h)

    def resizeEvent(self, event):
        body_w = PANEL_W - 2 * PADDING        # fixed width: text never reflows while animating
        x = (self.width() - body_w) // 2
        y = MARGIN + HEADER_H + 6
        h = max(0, self.height() - 2 * MARGIN - HEADER_H - 6 - 14)
        self.body.setGeometry(x, y, body_w, h)
        super().resizeEvent(event)

    # ---------- slots (called from the assistant thread via signals) ----------
    def set_state(self, state: str):
        if state in STATES:
            self._state = state
            self.update()

    def show_text(self, title: str, text: str):
        self._title, self._text = title, text
        self._open()

    def collapse(self):
        if not self._expanded:
            return
        self._expanded = False
        self._auto_hide.stop()
        self._animate_to(self._outer_rect(False))

    def _open(self):
        accent = STATES[self._state][1]
        self.body.setHtml(format_body(self._title, self._text, accent))
        self.body.document().setTextWidth(PANEL_W - 2 * PADDING - 8)
        body_h = min(MAX_BODY_H, int(self.body.document().size().height()) + 6)
        self._expanded = True
        self.body.show()
        self.body.verticalScrollBar().setValue(0)
        self._animate_to(self._outer_rect(True, body_h))
        seconds = min(45, max(10, len(self._text) * 0.055))
        self._auto_hide.start(int(seconds * 1000))

    def _animate_to(self, rect: QRect):
        self._grow.stop()
        self._grow.setStartValue(self.geometry())
        self._grow.setEndValue(rect)
        self._grow.start()

    def _after_grow(self):
        if not self._expanded:
            self.body.hide()

    # ---------- mouse ----------
    def mousePressEvent(self, event):
        y = event.position().y()
        if self._expanded:
            if y < MARGIN + HEADER_H:         # click the header to close
                self.collapse()
        elif self._text:
            self._open()                      # click the pill to reopen the last message

    def enterEvent(self, event):
        if self._expanded:
            self._auto_hide.stop()            # reading: do not close under the cursor

    def leaveEvent(self, event):
        if self._expanded:
            self._auto_hide.start(3000)

    # ---------- painting ----------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        t = time.time() - self._t0
        label, accent_hex = STATES[self._state]
        accent = QColor(accent_hex)
        card = QRectF(MARGIN, MARGIN, self.width() - 2 * MARGIN, self.height() - 2 * MARGIN)

        # soft shadow
        p.setPen(Qt.NoPen)
        for i in range(9):
            p.setBrush(QColor(0, 0, 0, 6))
            p.drawRoundedRect(card.adjusted(-i, -i + 3, i, i + 3), RADIUS + i, RADIUS + i)

        # slab
        grad = QLinearGradient(card.topLeft(), card.bottomLeft())
        grad.setColorAt(0.0, QColor("#262a32"))
        grad.setColorAt(1.0, QColor("#14171c"))
        p.setBrush(grad)
        edge = QColor(255, 255, 255, 30)
        if self._state != "idle":
            edge = QColor(accent.red(), accent.green(), accent.blue(), int(70 + 40 * math.sin(t * 3)))
        p.setPen(QPen(edge, 1))
        p.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)

        # top highlight, like brushed metal catching light
        p.setPen(QPen(QColor(255, 255, 255, 38), 1))
        p.drawLine(int(card.left() + RADIUS), int(card.top() + 1), int(card.right() - RADIUS), int(card.top() + 1))

        cy = card.top() + HEADER_H / 2
        self._draw_segments(p, card.left() + 16, cy, accent, t)

        # name
        name_font = QFont(self._font, 10)
        name_font.setWeight(QFont.Bold)
        name_font.setLetterSpacing(QFont.AbsoluteSpacing, 3.0)
        p.setFont(name_font)
        p.setPen(QColor("#eceff4"))
        p.drawText(QRectF(card.left() + 66, card.top(), 70, HEADER_H), Qt.AlignVCenter | Qt.AlignLeft, "TARS")

        # state label + LED
        state_font = QFont(self._font, 7)
        state_font.setWeight(QFont.DemiBold)
        state_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.6)
        p.setFont(state_font)
        p.setPen(accent)
        p.drawText(
            QRectF(card.left() + 120, card.top(), card.width() - 120 - 32, HEADER_H),
            Qt.AlignVCenter | Qt.AlignRight, label,
        )
        led = QPointF(card.right() - 16, cy)
        pulse = 0.55 + 0.45 * math.sin(t * 4) if self._state != "idle" else 0.35
        glow = QRadialGradient(led, 9)
        glow.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), int(150 * pulse)))
        glow.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(led, 9, 9)
        p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), int(110 + 145 * pulse)))
        p.drawEllipse(led, 3, 3)

        # divider under the header when the panel is open
        if self.height() > PILL_H + 2 * MARGIN + 8:
            p.setPen(QPen(QColor(255, 255, 255, 22), 1))
            y = int(card.top() + HEADER_H)
            p.drawLine(int(card.left() + 14), y, int(card.right() - 14), y)

    def _draw_segments(self, p: QPainter, x: float, cy: float, accent: QColor, t: float):
        """TARS' four vertical segments. They breathe, pulse, wave or dance by state."""
        w, gap = 7, 3
        for i in range(4):
            if self._state == "speaking":
                h = 9 + 10 * abs(math.sin(t * 5.5 + i * 1.3))
                alpha = 235
            elif self._state == "thinking":
                wave = max(0.0, math.sin(t * 3.2 - i * 0.9))
                h = 13 + 7 * wave
                alpha = 90 + 165 * wave
            elif self._state == "listening":
                h = 14 + 3 * math.sin(t * 3 + i * 0.5)
                alpha = 160 + 80 * math.sin(t * 3)
            else:
                h = 14
                alpha = 60 + 20 * math.sin(t * 1.2 + i * 0.4)
            alpha = max(0, min(255, int(alpha)))
            rect = QRectF(x + i * (w + gap), cy - h / 2, w, h)
            path = QPainterPath()
            path.addRoundedRect(rect, 2, 2)
            p.setPen(QPen(QColor(255, 255, 255, 40), 1))
            p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), alpha))
            p.drawPath(path)


def build():
    """Create the Qt app, the overlay window and its controller."""
    app = QApplication.instance() or QApplication([])
    overlay = Overlay()
    ctl = UiController()
    ctl.stateChanged.connect(overlay.set_state)
    ctl.textRequested.connect(overlay.show_text)
    ctl.collapseRequested.connect(overlay.collapse)
    ctl.quitRequested.connect(app.quit)
    overlay.show()
    return app, overlay, ctl