import queue
import threading
from typing import Optional, Tuple

from PySide6 import QtCore, QtGui
from moviepy import VideoFileClip


class FramePreviewer(QtCore.QThread):
       
    frame_ready = QtCore.Signal(QtGui.QImage)
    frame_error = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue: "queue.Queue[Tuple[str, float, int, int, int]]" = queue.Queue(maxsize=1)
        self._stop = threading.Event()
        self._current_key = None                  
        self._clip: Optional[VideoFileClip] = None

    def run(self):
        while not self._stop.is_set():
            try:
                path, t, wid, hei, pref_h = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                key = (path, pref_h)
                if key != self._current_key:
                                                 
                    if self._clip is not None:
                        try:
                            self._clip.close()
                        except Exception:
                            pass
                                                                                               
                    target = (None, pref_h) if pref_h and pref_h > 0 else None
                    self._clip = VideoFileClip(path, target_resolution=target)
                    self._current_key = key

                clip = self._clip
                if clip is None:
                    raise RuntimeError("Clip not opened")

                                          
                t = max(0.0, min(t, float(clip.duration)))

                                   
                frame = clip.get_frame(t)                     
                h, w, _ = frame.shape

                                          
                qimg = QtGui.QImage(frame.data, w, h, 3 * w, QtGui.QImage.Format.Format_RGB888).copy()

                                                                    
                if wid > 0 and hei > 0:
                    qimg_scaled = qimg.scaled(wid, hei, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                    final = QtGui.QImage(wid, hei, QtGui.QImage.Format.Format_RGB32)
                    final.fill(QtCore.Qt.black)
                    painter = QtGui.QPainter(final)
                    x = (wid - qimg_scaled.width()) // 2
                    y = (hei - qimg_scaled.height()) // 2
                    painter.drawImage(x, y, qimg_scaled)
                    painter.end()
                    qimg = final

                self.frame_ready.emit(qimg)

            except Exception as e:
                self.frame_error.emit(str(e))

    def request(self, path: str, t: float, widget_width: int, widget_height: int, pref_height: int):

           
                                                                     
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._queue.put((path, t, widget_width, widget_height, pref_height))

    def stop(self):
        self._stop.set()
        try:
            if self._clip is not None:
                self._clip.close()
        except Exception:
            pass
