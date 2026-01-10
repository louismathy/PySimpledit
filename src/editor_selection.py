import os
from typing import Optional

from PySide6 import QtWidgets

from models import ClipItem, AudioItem
from timeline import ClipGraphicsItem, AudioGraphicsItem


class EditorSelectionMixin:
    def current_clip(self) -> Optional[ClipItem]:
        row = self.list_clips.currentRow()
        if 0 <= row < len(self.clips):
            return self.clips[row]
        return None

    def current_audio(self) -> Optional[AudioItem]:
        row = self.list_audio.currentRow()
        if 0 <= row < len(self.audios):
            return self.audios[row]
        return None

    def refresh_clip_list_labels(self):
        selected = self.current_clip()

        self.list_clips.blockSignals(True)
        self.list_clips.clear()
        for c in self.clips:
            self.list_clips.addItem(
                f"{os.path.basename(c.path)}  t={c.start_time:.2f}s  [{c.trim_in:.2f}-{c.safe_out():.2f}s]"
            )
        self.list_clips.blockSignals(False)

        if selected and selected in self.clips:
            self.list_clips.setCurrentRow(self.clips.index(selected))

    def refresh_audio_list_labels(self):
        selected = self.current_audio()

        self.list_audio.blockSignals(True)
        self.list_audio.clear()
        for a in self.audios:
            self.list_audio.addItem(
                f"{os.path.basename(a.path)}  t={a.start_time:.2f}s  [{a.trim_in:.2f}-{a.safe_out():.2f}s]  {a.gain_db:+.1f} dB"
            )
        self.list_audio.blockSignals(False)

        if selected and selected in self.audios:
            self.list_audio.setCurrentRow(self.audios.index(selected))

    def on_select_clip(self, row: int):
        self._last_selection_kind = "clip"
        self.list_audio.blockSignals(True)
        self.list_audio.clearSelection()
        self.list_audio.blockSignals(False)

        if not (0 <= row < len(self.clips)):
            self.lbl_path.setText("-")
            self.lbl_duration.setText("-")
            self.spin_trim_in.setValue(0.0)
            self.spin_trim_out.setValue(0.0)
            self.spin_start.setValue(0.0)
            return

        c = self.clips[row]
        self.lbl_path.setText(c.path)
        self.lbl_duration.setText(f"{c.duration:.3f}s")
        self.spin_trim_in.setMaximum(c.duration)
        self.spin_trim_out.setMaximum(c.duration)
        self.spin_trim_in.setValue(c.trim_in)
        self.spin_trim_out.setValue(c.safe_out())
        self.spin_start.setValue(c.start_time)

        self._request_frame(c.path, c.trim_in)
        self._refresh_effects_ui()

    def _select_clip_from_timeline(self, clip: ClipItem):
        try:
            idx = self.clips.index(clip)
            self.list_clips.setCurrentRow(idx)
            self.list_clips.setFocus()
        except ValueError:
            pass

    def _select_audio_from_timeline(self, audio: AudioItem):
        try:
            idx = self.audios.index(audio)
            self.list_audio.setCurrentRow(idx)
            self.list_clips.setFocus()
        except ValueError:
            pass

    def on_apply_from_inspector(self):
        c = self.current_clip()
        if not c: return
        ti = float(self.spin_trim_in.value())
        to = float(self.spin_trim_out.value())
        st = float(self.spin_start.value())
        if not (0.0 <= ti < to <= c.duration+1e-6):
            QtWidgets.QMessageBox.warning(self, "Invalid", "Check trim values: 0 <= In < Out <= Duration.")
            return
        c.trim_in, c.trim_out, c.start_time = ti, to, max(0.0, st)
        gi = self.graphics_by_clip.get(self._gi_key(c))
        self._refresh_effects_ui()
        if gi:
            gi.update_geometry(); gi._refresh_label()
        self.refresh_clip_list_labels()
        self._on_timeline_changed(hard=True)
        self._request_frame(c.path, c.trim_in)

    def on_select_audio(self, row: int):
        self._last_selection_kind = "audio"
        self.list_clips.blockSignals(True)
        self.list_clips.clearSelection()
        self.list_clips.blockSignals(False)

        if not (0 <= row < len(self.audios)):
            self.lbl_apath.setText("-")
            self.lbl_adur.setText("-")
            self.spin_ain.setValue(0.0)
            self.spin_aout.setValue(0.0)
            self.spin_astart.setValue(0.0)
            self.spin_again.setValue(0.0)
            return

        a = self.audios[row]
        self.lbl_apath.setText(a.path)
        self.lbl_adur.setText(f"{a.duration:.3f}s")
        self.spin_ain.setMaximum(a.duration)
        self.spin_aout.setMaximum(a.duration)
        self.spin_ain.setValue(a.trim_in)
        self.spin_aout.setValue(a.safe_out())
        self.spin_astart.setValue(a.start_time)
        self.spin_again.setValue(a.gain_db)

    def on_apply_audio(self):
        a = self.current_audio()
        if not a: return
        ti = float(self.spin_ain.value())
        to = float(self.spin_aout.value())
        st = float(self.spin_astart.value())
        if not (0.0 <= ti < to <= a.duration+1e-6):
            QtWidgets.QMessageBox.warning(self, "Invalid", "Check audio trim: 0 <= In < Out <= Duration.")
            return
        a.trim_in, a.trim_out, a.start_time, a.gain_db = ti, to, max(0.0, st), float(self.spin_again.value())
        gi = self.audio_graphics_by_clip.get(self._agi_key(a))
        if gi:
            gi.update_geometry(); gi._refresh_label()
        self.refresh_audio_list_labels()
        self._on_timeline_changed(hard=True)

    def on_remove_audio(self):
        row = self.list_audio.currentRow()
        if not (0 <= row < len(self.audios)): return
        a = self.audios.pop(row)
        gi = self.audio_graphics_by_clip.pop(self._agi_key(a), None)
        if gi: self.scene.removeItem(gi)
        self.refresh_audio_list_labels()
        self._on_timeline_changed(hard=True)
        self._refresh_effects_ui()

    def on_clip_moved(self, clip: ClipItem):
        self.refresh_clip_list_labels()
        self._on_timeline_changed(hard=False)

    def on_audio_moved(self, audio: AudioItem):
        self.refresh_audio_list_labels()
        self._on_timeline_changed(hard=False)

    def _on_scene_selection_changed(self):
        items = self.scene.selectedItems()
        if not items:
            self.list_clips.blockSignals(True)
            self.list_audio.blockSignals(True)
            self.list_clips.clearSelection()
            self.list_audio.clearSelection()
            self.list_clips.blockSignals(False)
            self.list_audio.blockSignals(False)
            return

        it = items[0]

        if isinstance(it, ClipGraphicsItem):
            clip = it.model
            try:
                idx = self.clips.index(clip)
            except ValueError:
                idx = -1
            if idx >= 0:
                self.list_clips.blockSignals(True)
                self.list_clips.setCurrentRow(idx)
                self.list_clips.blockSignals(False)
                self.list_clips.setFocus()

        elif isinstance(it, AudioGraphicsItem):
            aud = it.model
            try:
                idx = self.audios.index(aud)
            except ValueError:
                idx = -1
            if idx >= 0:
                self.list_audio.blockSignals(True)
                self.list_audio.setCurrentRow(idx)
                self.list_audio.blockSignals(False)
                self.list_audio.setFocus()
