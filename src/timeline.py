from typing import List
import math

from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Qt, QRectF, QPointF, Signal

from models import ClipItem, AudioItem
from utils import fmt_time

# ------------------------------ Layout-Constants ------------------------------
TRACK_H = 64.0
TRACK_Y = 40.0
RULER_H = 32.0
AUDIO_TRACK_Y = TRACK_Y + TRACK_H + 24.0
AUDIO_TRACK_H = 40.0


# ------------------------------ Ruler & Playhead ------------------------------
class TimeRuler(QtWidgets.QGraphicsItem):
    def __init__(self, pixels_per_second: float):
        super().__init__()
        self.pps = pixels_per_second
        self.setZValue(100)

    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(0, 0, 1e7, RULER_H)

    def paint(self, p: QtGui.QPainter, option, widget=None):
        rect = option.exposedRect
        p.fillRect(rect, QtGui.QColor(28, 28, 32))
        p.setPen(QtGui.QColor(90, 90, 95))

        s_per_100px = 100.0 / max(1e-6, self.pps)
        if s_per_100px < 0.5:
            major = 1.0
        elif s_per_100px < 2:
            major = 2.0
        elif s_per_100px < 6:
            major = 5.0
        else:
            major = 10.0
        minor = major / 5

        start_s = max(0.0, rect.left() / self.pps)
        end_s = max(0.0, rect.right() / self.pps)

        max_ticks = 220
        visible_seconds = end_s - start_s
        est_ticks = int(visible_seconds / ((10.0 / self.pps) if self.pps > 0 else 1))
        if est_ticks > max_ticks:
            major *= math.ceil(est_ticks / max_ticks)
            minor = major / 5

        # Minor ticks
        x0 = math.floor(start_s / minor) * minor
        t = x0
        while t <= end_s:
            x = t * self.pps
            h = 6 if (abs((t / major) - round(t / major)) > 1e-6) else 10
            p.drawLine(QtCore.QLineF(x, RULER_H - h, x, RULER_H))
            t += minor

        # Major labels
        p.setPen(QtGui.QColor(200, 200, 205))
        first_major = math.floor(start_s / major) * major
        t = first_major
        while t <= end_s + major:
            x = t * self.pps
            p.drawLine(QtCore.QLineF(x, 0, x, RULER_H))
            p.drawText(QtCore.QPointF(x + 4, 14), fmt_time(t))
            t += major


class Playhead(QtWidgets.QGraphicsLineItem):
    def __init__(self):
        super().__init__()
        self.setZValue(90)
        pen = QtGui.QPen(QtGui.QColor(255, 70, 70))
        pen.setWidthF(1.5)
        self.setPen(pen)

    def set_x(self, x: float, scene_h: float):
        self.setLine(x, 0, x, scene_h)


# ------------------------------ Clip-Graphics ------------------------------
class ClipGraphicsItem(QtWidgets.QGraphicsObject):
    moved = Signal(object)   # schon vorhanden
    clicked = Signal(object) # NEU: ClipItem-Objekt

    def __init__(self, clip: ClipItem, pps: float, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = clip
        self.pps = pps
        self._rect = QRectF()
        self._dragging = False

        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsSelectable
            | QtWidgets.QGraphicsItem.ItemIsMovable
            | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setCacheMode(QtWidgets.QGraphicsItem.DeviceCoordinateCache)
        self.setZValue(10)

        self.brush = QtGui.QBrush(QtGui.QColor(70, 120, 200, 180))
        self.pen = QtGui.QPen(QtGui.QColor(20, 50, 110))
        self.pen.setWidthF(1.0)

        self.snap_eps = 6.0
        self._label_cache = QtGui.QStaticText()
        self._label_cache.setTextFormat(Qt.PlainText)
        self._refresh_label()
        self.update_geometry()

    def _refresh_label(self):
        text = QtCore.QFileInfo(self.model.path).fileName() + f"  [{self.model.trim_in:.2f}–{self.model.safe_out():.2f}s]"
        self._label_cache.setText(text)

    def boundingRect(self) -> QtCore.QRectF:
        return self._rect

    def update_geometry(self):
        w = max(12.0, self.model.trimmed_length() * self.pps)
        self.prepareGeometryChange()
        self._rect = QRectF(0, TRACK_Y, w, TRACK_H)
        self.setPos(self.model.start_time * self.pps, 0)

    def paint(self, p: QtGui.QPainter, option, widget=None):
        r = self._rect
        p.setRenderHint(QtGui.QPainter.Antialiasing, False)

        # Brush und Pen
        p.setBrush(self.brush)

        if self.isSelected():
            sel_pen = QtGui.QPen(QtGui.QColor(255, 200, 0), 2.0)  # Gelber Rand
            p.setPen(sel_pen)
        else:
            p.setPen(self.pen)

        p.drawRect(r)

        # Label
        p.setPen(Qt.white)
        p.drawStaticText(r.left() + 8, r.top() + 6, self._label_cache)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.model)  # <- NEU: Signal abfeuern

        sc: "TimelineScene" = self.scene()
        if sc:
            sc.build_snap_targets(exclude_item=self)
        self._dragging = True
        return super().mousePressEvent(e)


    def mouseReleaseEvent(self, e):
        sc: "TimelineScene" = self.scene()
        if sc:
            sc.clear_snap_targets()
        if self._dragging:
            self._dragging = False
            self.model.start_time = max(0.0, self.pos().x() / self.pps)
            self.moved.emit(self.model)
        return super().mouseReleaseEvent(e)

    def _snap_x(self, x: float) -> float:
        scene = self.scene()
        targets = getattr(scene, "snap_targets", [0.0]) if scene else [0.0]
        for t in targets:
            if abs(x - t) <= self.snap_eps:
                return t

        grid = 0.1 * self.pps
        if grid > 1:
            xg = round(x / grid) * grid
            if abs(x - xg) <= self.snap_eps:
                return xg
        return x

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionChange:
            new_pos: QPointF = value
            new_pos.setY(0)
            return QPointF(self._snap_x(new_pos.x()), 0)
        return super().itemChange(change, value)


class AudioGraphicsItem(QtWidgets.QGraphicsObject):
    moved = Signal(object)
    clicked = Signal(object)  # NEU: AudioItem
    def __init__(self, clip: AudioItem, pps: float, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = clip
        self.pps = pps
        self._rect = QRectF()
        self._dragging = False

        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsSelectable
            | QtWidgets.QGraphicsItem.ItemIsMovable
            | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setCacheMode(QtWidgets.QGraphicsItem.DeviceCoordinateCache)
        self.setZValue(8)

        self.brush = QtGui.QBrush(QtGui.QColor(60, 180, 120, 180))
        self.pen = QtGui.QPen(QtGui.QColor(20, 90, 70))
        self.pen.setWidthF(1.0)

        self.snap_eps = 6.0
        self._label_cache = QtGui.QStaticText()
        self._label_cache.setTextFormat(Qt.PlainText)
        self._refresh_label()
        self.update_geometry()

    def _refresh_label(self):
        base = QtCore.QFileInfo(self.model.path).fileName()
        self._label_cache.setText(
            f"{base}  [{self.model.trim_in:.2f}–{self.model.safe_out():.2f}s]  {self.model.gain_db:+.1f} dB"
        )

    def boundingRect(self) -> QtCore.QRectF:
        return self._rect

    def update_geometry(self):
        w = max(12.0, self.model.trimmed_length() * self.pps)
        self.prepareGeometryChange()
        self._rect = QRectF(0, AUDIO_TRACK_Y, w, AUDIO_TRACK_H)
        self.setPos(self.model.start_time * self.pps, 0)

    def paint(self, p: QtGui.QPainter, option, widget=None):
        r = self._rect
        p.setRenderHint(QtGui.QPainter.Antialiasing, False)

        # Standard-Füllung
        p.setBrush(self.brush)
        p.setPen(self.pen)
        p.drawRect(r)

        # Gelbe Outline bei Auswahl
        if self.isSelected():
            sel_pen = QtGui.QPen(QtGui.QColor(255, 215, 0), 2.5, Qt.SolidLine)
            p.setPen(sel_pen)
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawRect(r)

        # Text
        p.setPen(Qt.white)
        p.drawStaticText(r.left() + 8, r.top() + 6, self._label_cache)


    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.model)  # AudioItem nach außen geben
        sc: "TimelineScene" = self.scene()
        if sc:
            sc.build_snap_targets(exclude_item=self)
        self._dragging = True
        return super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        sc: "TimelineScene" = self.scene()
        if sc:
            sc.clear_snap_targets()
        if self._dragging:
            self._dragging = False
            self.model.start_time = max(0.0, self.pos().x() / self.pps)
            self.moved.emit(self.model)

        if e.button() == Qt.LeftButton and not self._dragging:
            self.clicked.emit(self.model)
        return super().mouseReleaseEvent(e)

    def _snap_x(self, x: float) -> float:
        scene = self.scene()
        targets = getattr(scene, "snap_targets", [0.0]) if scene else [0.0]
        for t in targets:
            if abs(x - t) <= self.snap_eps:
                return t

        grid = 0.1 * self.pps
        if grid > 1:
            xg = round(x / grid) * grid
            if abs(x - xg) <= self.snap_eps:
                return xg
        return x

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionChange:
            new_pos: QPointF = value
            new_pos.setY(0)
            return QPointF(self._snap_x(new_pos.x()), 0)
        return super().itemChange(change, value)


# ------------------------------ Scene/View --------------------------------------
class TimelineScene(QtWidgets.QGraphicsScene):
    def __init__(self, pps: float):
        super().__init__()
        self.pps = pps
        self.setSceneRect(0, 0, 20000, AUDIO_TRACK_Y + AUDIO_TRACK_H + 40)
        self.setBackgroundBrush(QtGui.QColor(20, 20, 24))

        self.ruler = TimeRuler(self.pps)
        self.addItem(self.ruler)

        self.playhead = Playhead()
        self.addItem(self.playhead)
        self.update_playhead_x(0)

        self.snap_targets: List[float] = [0.0]

    def build_snap_targets(self, exclude_item=None):
        targets = [0.0]
        try:
            targets.append(self.playhead.line().x1())
        except Exception:
            pass
        for it in self.items():
            if it is exclude_item:
                continue
            if isinstance(it, (ClipGraphicsItem, AudioGraphicsItem)):
                left = it.pos().x()
                right = left + it.boundingRect().width()
                targets.extend([left, right])
        self.snap_targets = targets

    def clear_snap_targets(self):
        self.snap_targets = [0.0]

    def update_pps(self, pps: float):
        self.pps = pps
        self.ruler.pps = pps
        for it in self.items():
            if isinstance(it, (ClipGraphicsItem, AudioGraphicsItem)):
                it.pps = pps
                it.update_geometry()
        self.invalidate(self.sceneRect())

    def update_playhead_x(self, t_sec: float):
        x = t_sec * self.pps
        self.playhead.set_x(x, self.sceneRect().height())

    def add_clip_item(self, clip: ClipItem):
        gi = ClipGraphicsItem(clip, self.pps)
        self.addItem(gi)
        return gi

    def add_audio_item(self, clip: AudioItem):
        gi = AudioGraphicsItem(clip, self.pps)
        self.addItem(gi)
        return gi


class TimelineView(QtWidgets.QGraphicsView):
    time_changed = Signal(float)  # seconds

    def __init__(self, scene: TimelineScene):
        super().__init__(scene)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.MinimalViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setCacheMode(QtWidgets.QGraphicsView.CacheBackground)
        self.setOptimizationFlag(QtWidgets.QGraphicsView.DontSavePainterState, True)
        self.setOptimizationFlag(QtWidgets.QGraphicsView.DontAdjustForAntialiasing, True)
        self.setRenderHint(QtGui.QPainter.Antialiasing, False)
        self.setRenderHint(QtGui.QPainter.TextAntialiasing, False)

        self.scene().setItemIndexMethod(QtWidgets.QGraphicsScene.NoIndex)

        try:
            from PySide6.QtOpenGLWidgets import QOpenGLWidget
            self.setViewport(QOpenGLWidget())
        except Exception:
            pass

    def wheelEvent(self, e: QtGui.QWheelEvent):
        if QtWidgets.QApplication.keyboardModifiers() & Qt.ControlModifier:
            delta = e.angleDelta().y()
            factor = 1.2 if delta > 0 else 1 / 1.2
            self._zoom_at_cursor(factor)
        else:
            super().wheelEvent(e)

    def _zoom_at_cursor(self, factor: float):
        scene: TimelineScene = self.scene()
        pps0 = scene.pps
        pps1 = max(5.0, min(1500.0, pps0 * factor))
        if abs(pps1 - pps0) < 1e-3:
            return

        cursor_view = self.mapFromGlobal(QtGui.QCursor.pos())
        cursor_scene = self.mapToScene(cursor_view)
        t = max(0.0, cursor_scene.x() / pps0)

        scene.update_pps(pps1)

        new_x = t * pps1
        dx = new_x - cursor_scene.x()
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + int(dx))

    def mousePressEvent(self, e: QtGui.QMouseEvent):
        if e.button() == Qt.LeftButton and e.position().y() <= RULER_H + 8:
            p = self.mapToScene(e.pos())
            t = max(0.0, p.x() / self.scene().pps)
            self.time_changed.emit(t)
            e.accept()
            return
        super().mousePressEvent(e)
