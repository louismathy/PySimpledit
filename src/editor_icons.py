import os

from PySide6 import QtCore, QtGui


ACCENT_COLOR = QtGui.QColor("#1E6CFF")


def _icon_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "assets", "icons")


def load_tinted_icon(name: str, color: QtGui.QColor = ACCENT_COLOR, size: QtCore.QSize | None = None) -> QtGui.QIcon | None:
    path = os.path.join(_icon_dir(), name)
    if not os.path.exists(path):
        return None
    src = QtGui.QPixmap(path)
    if src.isNull():
        return None

    tinted = QtGui.QPixmap(src.size())
    tinted.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(tinted)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode_Source)
    painter.drawPixmap(0, 0, src)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), color)
    painter.end()

    if size is not None:
        tinted = tinted.scaled(size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

    return QtGui.QIcon(tinted)
