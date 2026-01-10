from typing import Optional

from PySide6 import QtGui

from models import ClipItem, AudioItem


class EditorCoreMixin:
    def _jump_to_start(self):
        try:
            self.timeline.horizontalScrollBar().setValue(self.timeline.horizontalScrollBar().minimum())
        except Exception:
            pass
        self.seek(0.0, from_player=False)

    def closeEvent(self, e: QtGui.QCloseEvent):
        try:
            self.audio_engine.stop()
            self.frame_thread.stop(); self.frame_thread.quit(); self.frame_thread.wait(800)
        except Exception:
            pass
        return super().closeEvent(e)

    def _setup_spin(self, s):
        s.setDecimals(3); s.setSingleStep(0.05); s.setRange(0.0, 100000.0)

    def _gi_key(self, c: ClipItem) -> int: return id(c)
    def _agi_key(self, a: AudioItem) -> int: return id(a)

    def _rebuild_sorted(self):
        self._sorted_by_start = sorted(self.clips, key=lambda c: c.start_time)
        self._sorted_starts = [c.start_time for c in self._sorted_by_start]
        self._sorted_audio_by_start = sorted(self.audios, key=lambda a: a.start_time)
        self._sorted_audio_starts = [a.start_time for a in self._sorted_audio_by_start]

    def _on_timeline_changed(self, hard: bool = True):
        self._rebuild_sorted()
