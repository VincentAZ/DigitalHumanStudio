"""Small line-plot widget (one y axis, fixed series colours, hover crosshair)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QWidget

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d13438"}
GRID = QColor("#e4e3df")
AXIS = QColor("#b9b8b1")
INK = QColor("#0b0b0b")
INK_SOFT = QColor("#52514e")


class LinePlot(QWidget):
    def __init__(self, title: str = "", y_label: str = "", parent=None):
        super().__init__(parent)
        self.title = title
        self.y_label = y_label
        self.series: list[tuple[str, list[float], list[float]]] = []
        self.hover_x = None
        self.setMouseTracking(True)
        self.setMinimumHeight(160)

    def set_series(self, series: list[tuple[str, list[float], list[float]]]):
        self.series = [(name, list(xs), list(ys)) for name, xs, ys in series[:6]]
        self.update()

    def _bounds(self):
        xs = [x for _, sx, _ in self.series for x in sx]
        ys = [y for _, _, sy in self.series for y in sy if y == y]
        if not xs or not ys:
            return None
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        if x1 == x0:
            x1 = x0 + 1
        if y1 == y0:
            y1 = y0 + 1
        pad = (y1 - y0) * 0.08
        return x0, x1, y0 - pad, y1 + pad

    def _plot_rect(self) -> QRectF:
        return QRectF(56, 26, max(self.width() - 72, 10), max(self.height() - 58, 10))

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fcfcfb"))
        rect = self._plot_rect()
        painter.setPen(INK)
        painter.setFont(QFont(self.font().family(), 10, QFont.Weight.DemiBold))
        painter.drawText(QPointF(8, 17), self.title)
        bounds = self._bounds()
        if bounds is None:
            painter.setPen(INK_SOFT)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "no data")
            return
        x0, x1, y0, y1 = bounds

        def to_px(x, y):
            return QPointF(rect.left() + (x - x0) / (x1 - x0) * rect.width(),
                           rect.bottom() - (y - y0) / (y1 - y0) * rect.height())

        painter.setFont(QFont(self.font().family(), 8))
        for i in range(5):
            y = y0 + (y1 - y0) * i / 4
            point = to_px(x0, y)
            painter.setPen(QPen(GRID, 1))
            painter.drawLine(QPointF(rect.left(), point.y()), QPointF(rect.right(), point.y()))
            painter.setPen(INK_SOFT)
            painter.drawText(QRectF(0, point.y() - 8, 50, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{y:.3g}")
        for i in range(5):
            x = x0 + (x1 - x0) * i / 4
            point = to_px(x, y0)
            painter.setPen(INK_SOFT)
            painter.drawText(QRectF(point.x() - 30, rect.bottom() + 4, 60, 14), Qt.AlignmentFlag.AlignCenter, f"{x:.4g}")
        painter.setPen(QPen(AXIS, 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        for index, (name, xs, ys) in enumerate(self.series):
            colour = QColor(SERIES[index % len(SERIES)])
            painter.setPen(QPen(colour, 2))
            points = [to_px(x, y) for x, y in zip(xs, ys) if y == y]
            for a, b in zip(points[:-1], points[1:]):
                painter.drawLine(a, b)
        if len(self.series) >= 2:
            x = rect.left()
            for index, (name, _, _) in enumerate(self.series):
                painter.setPen(QPen(QColor(SERIES[index % len(SERIES)]), 3))
                painter.drawLine(QPointF(x, 22), QPointF(x + 14, 22))
                painter.setPen(INK_SOFT)
                painter.drawText(QPointF(x + 18, 26), name)
                x += 26 + painter.fontMetrics().horizontalAdvance(name)
        if self.hover_x is not None:
            painter.setPen(QPen(AXIS, 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(self.hover_x, rect.top()), QPointF(self.hover_x, rect.bottom()))

    def mouseMoveEvent(self, event):
        bounds = self._bounds()
        rect = self._plot_rect()
        pos = event.position()
        if bounds is None or not rect.contains(pos):
            self.hover_x = None
            QToolTip.hideText()
            self.update()
            return
        x0, x1, _, _ = bounds
        x = x0 + (pos.x() - rect.left()) / rect.width() * (x1 - x0)
        lines = []
        for name, xs, ys in self.series:
            if not xs:
                continue
            index = min(range(len(xs)), key=lambda i: abs(xs[i] - x))
            lines.append(f"{name}: {ys[index]:.4g} (x={xs[index]:.4g})")
        self.hover_x = pos.x()
        QToolTip.showText(event.globalPosition().toPoint(), "\n".join(lines), self)
        self.update()

    def leaveEvent(self, _event):
        self.hover_x = None
        self.update()
