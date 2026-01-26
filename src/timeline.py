from typing import List
import math

from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Qt, QRectF, QPointF, Signal

from models import ClipItem, AudioItem
from utils import fmt_time

                                                                                
VIDEO_TRACK_H = 64.0
VIDEO_TRACK_GAP = 12.0
VIDEO_TRACK_COUNT = 2
MAX_VIDEO_LAYER = VIDEO_TRACK_COUNT - 1
TRACK_Y = 40.0
RULER_H = 32.0
AUDIO_TRACK_Y = TRACK_Y + (VIDEO_TRACK_COUNT * VIDEO_TRACK_H) + ((VIDEO_TRACK_COUNT - 1) * VIDEO_TRACK_GAP) + 24.0
AUDIO_TRACK_H = 40.0


def _layer_offset(layer: int) -> float:
    layer = max(0, min(MAX_VIDEO_LAYER, int(layer)))
    return (MAX_VIDEO_LAYER - layer) * (VIDEO_TRACK_H + VIDEO_TRACK_GAP)


def _layer_from_offset(offset: float) -> int:
    slots = [i * (VIDEO_TRACK_H + VIDEO_TRACK_GAP) for i in range(VIDEO_TRACK_COUNT)]
    nearest_idx = min(range(len(slots)), key=lambda i: abs(offset - slots[i]))
    return MAX_VIDEO_LAYER - nearest_idx


                                                                                
class TimeRuler(QtWidgets.QGraphicsItem):
    def __init__(self, pixels_per_second: float):
        super().__init__()
        self.pps = pixels_per_second
        self.setZValue(100)

    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(0, 0, 1e7, RULER_H)

    def paint(self, p: QtGui.QPainter, option, widget=None):
        rect = option.exposedRect
        colors = getattr(self.scene(), "theme_colors", {})
        p.fillRect(rect, colors.get("ruler_bg", QtGui.QColor(245, 247, 251)))
        p.setPen(colors.get("ruler_minor", QtGui.QColor(206, 216, 236)))

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

                     
        x0 = math.floor(start_s / minor) * minor
        t = x0
        while t <= end_s:
            x = t * self.pps
            h = 6 if (abs((t / major) - round(t / major)) > 1e-6) else 10
            p.drawLine(QtCore.QLineF(x, RULER_H - h, x, RULER_H))
            t += minor

                      
        p.setPen(colors.get("ruler_major", QtGui.QColor(70, 78, 96)))
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
        pen = QtGui.QPen(QtGui.QColor(255, 95, 95))
        pen.setWidthF(1.5)
        self.setPen(pen)

    def set_x(self, x: float, scene_h: float):
        self.setLine(x, 0, x, scene_h)


class ClipGraphicsItem(QtWidgets.QGraphicsObject):
    moved = Signal(object)                    
    clicked = Signal(object)                  

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
        self.setCacheMode(QtWidgets.QGraphicsItem.ItemCoordinateCache)
        self.setZValue(10)

        self.brush = QtGui.QBrush()
        self.pen = QtGui.QPen()
        self.pen.setWidth(0)
        self.apply_theme()

        self.snap_eps = 6.0
        self._label_cache = QtGui.QStaticText()
        self._label_cache.setTextFormat(Qt.PlainText)
        self._refresh_label()
        self.update_geometry()

    def _refresh_label(self):
        text = QtCore.QFileInfo(self.model.path).fileName() + f"  [{self.model.trim_in:.2f}-{self.model.safe_out():.2f}s]"
        self._label_cache.setText(text)

    def boundingRect(self) -> QtCore.QRectF:
        return self._rect

    def update_geometry(self):
        w = max(12.0, round(self.model.trimmed_length() * self.pps))
        self.prepareGeometryChange()
        self._rect = QRectF(0, TRACK_Y, w, VIDEO_TRACK_H)
        layer = getattr(self.model, "layer", MAX_VIDEO_LAYER)
        layer = max(0, min(MAX_VIDEO_LAYER, int(layer)))
        self.model.layer = layer
        self.setPos(self.model.start_time * self.pps, _layer_offset(layer))

    def paint(self, p: QtGui.QPainter, option, widget=None):
        r = self._rect
        p.setRenderHint(QtGui.QPainter.Antialiasing, False)
        p.setBrush(self.brush)
        if self.isSelected():
            sel_pen = QtGui.QPen(self._theme_color("clip_selected", QtGui.QColor(30, 108, 255)), 2.0)
            p.setPen(sel_pen)
        else:
            p.setPen(self.pen)
        p.drawRect(r)
        p.setPen(self._theme_color("text", QtGui.QColor(27, 31, 42)))
        p.drawStaticText(r.left() + 8, r.top() + 6, self._label_cache)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.model)
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
            snapped_x = self._snap_x(new_pos.x())
            layer = _layer_from_offset(new_pos.y())
            snapped_y = _layer_offset(layer)
            self.model.layer = layer
            return QPointF(snapped_x, snapped_y)
        return super().itemChange(change, value)

    def _theme_color(self, key: str, fallback: QtGui.QColor) -> QtGui.QColor:
        colors = getattr(self.scene(), "theme_colors", {}) if self.scene() else {}
        return colors.get(key, fallback)

    def apply_theme(self):
        self.brush = QtGui.QBrush(self._theme_color("clip_fill", QtGui.QColor(210, 230, 255, 200)))
        self.pen = QtGui.QPen(self._theme_color("clip_outline", QtGui.QColor(125, 165, 230, 200)))
        self.pen.setWidth(0)



class AudioGraphicsItem(QtWidgets.QGraphicsObject):
    moved = Signal(object)
    clicked = Signal(object)             

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
        self.setCacheMode(QtWidgets.QGraphicsItem.ItemCoordinateCache)
        self.setZValue(8)

        self.brush = QtGui.QBrush()
        self.pen = QtGui.QPen()
        self.pen.setWidth(0)
        self.apply_theme()

        self.snap_eps = 6.0
        self._label_cache = QtGui.QStaticText()
        self._label_cache.setTextFormat(Qt.PlainText)
        self._refresh_label()
        self.update_geometry()

    def _refresh_label(self):
        base = QtCore.QFileInfo(self.model.path).fileName()
        self._label_cache.setText(
            f"{base}  [{self.model.trim_in:.2f}-{self.model.safe_out():.2f}s]  {self.model.gain_db:+.1f} dB"
        )

    def boundingRect(self) -> QtCore.QRectF:
        return self._rect

    def update_geometry(self):
        w = max(12.0, round(self.model.trimmed_length() * self.pps))
        self.prepareGeometryChange()
        self._rect = QRectF(0, AUDIO_TRACK_Y, w, AUDIO_TRACK_H)
        self.setPos(self.model.start_time * self.pps, 0)

    def paint(self, p: QtGui.QPainter, option, widget=None):
        r = self._rect
        p.setRenderHint(QtGui.QPainter.Antialiasing, False)
        p.setBrush(self.brush)
        p.setPen(self.pen)
        p.drawRect(r)
        if self.isSelected():
            sel_pen = QtGui.QPen(self._theme_color("clip_selected", QtGui.QColor(30, 108, 255)), 2.5, Qt.SolidLine)
            p.setPen(sel_pen)
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawRect(r)
        p.setPen(self._theme_color("text", QtGui.QColor(27, 31, 42)))
        p.drawStaticText(r.left() + 8, r.top() + 6, self._label_cache)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.model)
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
            self.model.layer = _layer_from_offset(self.pos().y())
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
                                                                               
            return QPointF(self._snap_x(new_pos.x()), 0)
        return super().itemChange(change, value)

    def _theme_color(self, key: str, fallback: QtGui.QColor) -> QtGui.QColor:
        colors = getattr(self.scene(), "theme_colors", {}) if self.scene() else {}
        return colors.get(key, fallback)

    def apply_theme(self):
        self.brush = QtGui.QBrush(self._theme_color("audio_fill", QtGui.QColor(203, 238, 225, 200)))
        self.pen = QtGui.QPen(self._theme_color("audio_outline", QtGui.QColor(110, 190, 150, 200)))
        self.pen.setWidth(0)





                                                                                  
class TimelineScene(QtWidgets.QGraphicsScene):
    def __init__(self, pps: float):
        super().__init__()
        self.pps = pps
        self.setSceneRect(0, 0, 20000, AUDIO_TRACK_Y + AUDIO_TRACK_H + 40)
        self.theme_colors = {}
        self.set_theme("light")

        self.ruler = TimeRuler(self.pps)
        self.addItem(self.ruler)

        self.playhead = Playhead()
        self.addItem(self.playhead)
        self.update_playhead_x(0)

        self.snap_targets: List[float] = [0.0]

    def set_theme(self, mode: str):
        if mode == "dark":
            self.theme_colors = {
                "scene_bg": QtGui.QColor(20, 24, 32),
                "ruler_bg": QtGui.QColor(24, 28, 36),
                "ruler_minor": QtGui.QColor(54, 62, 78),
                "ruler_major": QtGui.QColor(210, 220, 235),
                "text": QtGui.QColor(230, 237, 247),
                "clip_fill": QtGui.QColor(40, 74, 120, 120),
                "clip_outline": QtGui.QColor(80, 130, 210, 180),
                "audio_fill": QtGui.QColor(35, 100, 80, 120),
                "audio_outline": QtGui.QColor(70, 160, 130, 180),
                "clip_selected": QtGui.QColor(110, 170, 255),
            }
        else:
            self.theme_colors = {
                "scene_bg": QtGui.QColor(245, 247, 251),
                "ruler_bg": QtGui.QColor(245, 247, 251),
                "ruler_minor": QtGui.QColor(206, 216, 236),
                "ruler_major": QtGui.QColor(70, 78, 96),
                "text": QtGui.QColor(27, 31, 42),
                "clip_fill": QtGui.QColor(210, 230, 255, 200),
                "clip_outline": QtGui.QColor(125, 165, 230, 200),
                "audio_fill": QtGui.QColor(203, 238, 225, 200),
                "audio_outline": QtGui.QColor(110, 190, 150, 200),
                "clip_selected": QtGui.QColor(30, 108, 255),
            }
        self.setBackgroundBrush(self.theme_colors["scene_bg"])
        for it in self.items():
            if isinstance(it, (ClipGraphicsItem, AudioGraphicsItem)):
                it.apply_theme()
        self.invalidate(self.sceneRect())

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
                                               
        self.update_playhead_x(self.parent().current_time if hasattr(self.parent(), "current_time") else 0.0)


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
    time_changed = Signal(float)           

    def __init__(self, scene: TimelineScene):
        super().__init__(scene)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.MinimalViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.set_theme("light")

    def set_theme(self, mode: str):
        if mode == "dark":
            self.setStyleSheet(
                """
                QGraphicsView {
                    background: #141821;
                    border: 1px solid #2A3345;
                    border-radius: 12px;
                }
                QScrollBar:horizontal {
                    background: transparent;
                    height: 10px;
                    margin: 4px;
                }
                QScrollBar::handle:horizontal {
                    background: #3A455E;
                    border-radius: 5px;
                    min-width: 20px;
                }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                    width: 0px;
                }
                """
            )
        else:
            self.setStyleSheet(
                """
                QGraphicsView {
                    background: #F5F7FB;
                    border: 1px solid #E3E8F2;
                    border-radius: 12px;
                }
                QScrollBar:horizontal {
                    background: transparent;
                    height: 10px;
                    margin: 4px;
                }
                QScrollBar::handle:horizontal {
                    background: #D2DBEF;
                    border-radius: 5px;
                    min-width: 20px;
                }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                    width: 0px;
                }
                """
            )
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

                                                
        scene.update_playhead_x(self.window().current_time)


    def mousePressEvent(self, e: QtGui.QMouseEvent):
        if e.button() == Qt.LeftButton and e.position().y() <= RULER_H + 8:
            p = self.mapToScene(e.pos())
            t = max(0.0, p.x() / self.scene().pps)
            self.time_changed.emit(t)
            e.accept()
            return
        super().mousePressEvent(e)
