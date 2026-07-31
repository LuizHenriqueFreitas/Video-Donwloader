# ui/components/range_slider.py

""" Here you will find:
    - Slider settings and implementations:
        - mouse events functions;
        - draw markers, colors and bar geometry functions;
        - logic operations about set start and end markers;

"""

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QBrush, QPen

""" Selection slider with two markes (start/ end) of clip limits;
    The values are integer (seconds);
    Emit a signal when one or both markers are moved;
    Also show a optional indicator of player playhed position.
"""
class RangeSlider(QWidget):
    rangeChanged = Signal(int, int)
    startChanged = Signal(int)
    endChanged = Signal(int)
    sliderPressed = Signal()

    HANDLE_RADIUS = 8
    GROOVE_HEIGHT = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._maximum = 100
        self._start = 0
        self._end = 100
        self._playhead = None
        self._active_handle = None

        self.setMinimumHeight(36)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)


    """ ==============
            APIs

        function names are sufficent to understando what they do
      ============== """
    def setMaximum(self, maximum: int):
        self._maximum = max(1, int(maximum))
        self._start = 0
        self._end = self._maximum
        self._playhead = None
        self.update()
        self.rangeChanged.emit(self._start, self._end)

    def maximum(self) -> int:
        return self._maximum

    def start(self) -> int:
        return self._start

    def end(self) -> int:
        return self._end

    def setStart(self, value: int):
        value = self._clamp(value)
        if value > self._end:
            value = self._end
        if value != self._start:
            self._start = value
            self.update()
            self.startChanged.emit(self._start)
            self.rangeChanged.emit(self._start, self._end)

    def setEnd(self, value: int):
        value = self._clamp(value)
        if value < self._start:
            value = self._start
        if value != self._end:
            self._end = value
            self.update()
            self.endChanged.emit(self._end)
            self.rangeChanged.emit(self._start, self._end)

    def setPlayhead(self, value):
        self._playhead = None if value is None else self._clamp(value)
        self.update()


    """ ==================
            GEOMETRY
        
        i don't know how to describe this function
        over even if it's necessary
      ================= """
    def _clamp(self, value):
        return max(0, min(self._maximum, int(round(value))))

    def _track_rect(self):
        r = self.HANDLE_RADIUS
        return QRectF(r, (self.height() - self.GROOVE_HEIGHT) / 2,
                      self.width() - 2 * r, self.GROOVE_HEIGHT)

    def _value_to_x(self, value):
        track = self._track_rect()
        if self._maximum <= 0:
            return track.left()
        ratio = value / self._maximum
        return track.left() + ratio * track.width()

    def _x_to_value(self, x):
        track = self._track_rect()
        if track.width() <= 0:
            return 0
        ratio = (x - track.left()) / track.width()
        return self._clamp(ratio * self._maximum)


    """ =====================
        MOUSE OPERATIONS
      ==================== """
    def mousePressEvent(self, event):
        x = event.position().x()
        start_x = self._value_to_x(self._start)
        end_x = self._value_to_x(self._end)

        # choose mouse closer marker
        if abs(x - start_x) <= abs(x - end_x):
            self._active_handle = "start"
        else:
            self._active_handle = "end"

        self.sliderPressed.emit()
        self._move_active(x)

    def mouseMoveEvent(self, event):
        if self._active_handle:
            self._move_active(event.position().x())

    def mouseReleaseEvent(self, event):
        self._active_handle = None

    def _move_active(self, x):
        value = self._x_to_value(x)
        if self._active_handle == "start":
            self.setStart(value)
        elif self._active_handle == "end":
            self.setEnd(value)


    """ ===================
            PAINT UI    
      =================== """
    # painting implementation
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track = self._track_rect()

        # background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#3a3a3a")))
        painter.drawRoundedRect(track, 3, 3)

        # slected region
        start_x = self._value_to_x(self._start)
        end_x = self._value_to_x(self._end)
        sel = QRectF(start_x, track.top(), max(0.0, end_x - start_x), track.height())
        painter.setBrush(QBrush(QColor("#4CAF50")))
        painter.drawRoundedRect(sel, 3, 3)

        # playhead
        if self._playhead is not None:
            px = self._value_to_x(self._playhead)
            painter.setPen(QPen(QColor("#FFC107"), 2))
            painter.drawLine(QPointF(px, track.top() - 6),
                             QPointF(px, track.bottom() + 6))

        # markers
        self._draw_handle(painter, start_x)
        self._draw_handle(painter, end_x)

    # aditional function
    def _draw_handle(self, painter, x):
        cy = self.height() / 2
        r = self.HANDLE_RADIUS
        painter.setPen(QPen(QColor("#1e1e1e"), 1))
        painter.setBrush(QBrush(QColor("#eeeeee")))
        painter.drawEllipse(QPointF(x, cy), r, r)
