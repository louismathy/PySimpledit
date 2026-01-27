import queue
import threading
import time
from typing import Optional, Tuple

from PySide6 import QtCore, QtGui
from moviepy import VideoFileClip
from utils import debug_log


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
                    open_start = time.perf_counter()
                    target = (None, pref_h) if pref_h and pref_h > 0 else None
                    self._clip = VideoFileClip(path, target_resolution=target, audio=False)
                    self._current_key = key
                    open_dt = time.perf_counter() - open_start
                    if open_dt > 0.5:
                        debug_log(f"preview.open.slow dt={open_dt:.3f} path={path}")

                clip = self._clip
                if clip is None:
                    raise RuntimeError("Clip not opened")

                                          
                t = max(0.0, min(t, float(clip.duration)))

                                   
                frame_start = time.perf_counter()
                frame = clip.get_frame(t)
                frame_dt = time.perf_counter() - frame_start
                if frame_dt > 0.5:
                    debug_log(f"preview.frame.slow dt={frame_dt:.3f} t={t:.3f} path={path}")
                h, w, _ = frame.shape

                                          
                qimg = QtGui.QImage(frame.data, w, h, 3 * w, QtGui.QImage.Format.Format_RGB888).copy()

                                                                    
                if wid > 0 and hei > 0:
                    if qimg.width() != wid or qimg.height() != hei:
                        scale_start = time.perf_counter()
                        qimg_scaled = qimg.scaled(
                            wid, hei, QtCore.Qt.KeepAspectRatio, QtCore.Qt.FastTransformation
                        )
                        if qimg_scaled.width() == wid and qimg_scaled.height() == hei:
                            qimg = qimg_scaled
                        else:
                            final = QtGui.QImage(wid, hei, QtGui.QImage.Format.Format_RGB32)
                            final.fill(QtCore.Qt.black)
                            painter = QtGui.QPainter(final)
                            x = (wid - qimg_scaled.width()) // 2
                            y = (hei - qimg_scaled.height()) // 2
                            painter.drawImage(x, y, qimg_scaled)
                            painter.end()
                            qimg = final
                        scale_dt = time.perf_counter() - scale_start
                        if scale_dt > 0.2:
                            debug_log(f"preview.scale.slow dt={scale_dt:.3f} size={wid}x{hei}")

                self.frame_ready.emit(qimg)

            except Exception as e:
                debug_log(f"preview.error {e}")
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
