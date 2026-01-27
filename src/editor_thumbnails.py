from __future__ import annotations

from typing import Tuple

from PySide6 import QtCore, QtGui
from moviepy import VideoFileClip


class ThumbnailSignals(QtCore.QObject):
    ready = QtCore.Signal(str, QtGui.QImage)


class ThumbnailWorker(QtCore.QRunnable):
    def __init__(self, key: str, path: str, t_local: float, target_size: QtCore.QSize, signals: ThumbnailSignals):
        super().__init__()
        self._key = key
        self._path = path
        self._t_local = t_local
        self._target_size = target_size
        self._signals = signals

    def run(self):
        try:
            clip = VideoFileClip(self._path, audio=False)
            try:
                frame = clip.get_frame(self._t_local)
            finally:
                clip.close()

            h, w = frame.shape[:2]
            bytes_per_line = frame.strides[0]
            img = QtGui.QImage(frame.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888).copy()
            img = _scale_and_crop(img, self._target_size)
            self._signals.ready.emit(self._key, img)
        except Exception:
            pass


def _scale_and_crop(img: QtGui.QImage, target: QtCore.QSize) -> QtGui.QImage:
    if img.isNull():
        return img
    scaled = img.scaled(target, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)
    x = max(0, (scaled.width() - target.width()) // 2)
    y = max(0, (scaled.height() - target.height()) // 2)
    return scaled.copy(x, y, target.width(), target.height())
