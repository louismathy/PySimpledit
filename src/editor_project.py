import json

from PySide6 import QtWidgets

from moviepy import VideoFileClip, AudioFileClip

from models import ClipItem, AudioItem
from timeline import TimelineScene, ClipGraphicsItem, AudioGraphicsItem, MAX_VIDEO_LAYER


class EditorProjectMixin:
    def on_new_project(self):
        if self._confirm_discard():
            self.audio_engine.pause()
            self.clips.clear(); self.audios.clear()
            self.graphics_by_clip.clear(); self.audio_graphics_by_clip.clear()
            self.scene.clear(); self.scene = TimelineScene(self.pps); self.timeline.setScene(self.scene)
            if hasattr(self, "_theme_mode"):
                self.scene.set_theme(self._theme_mode)
                self.timeline.set_theme(self._theme_mode)
            self.project_path = None
            self.refresh_clip_list_labels(); self.refresh_audio_list_labels(); self._rebuild_sorted()
            self._on_timeline_changed(hard=True)
            self._refresh_effects_ui()

    def on_open_project(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Project", "", "Simpledit (*.sedit.json)")
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f: data = json.load(f)
            self.clips = [ClipItem(**c) for c in data.get("clips", [])]
            self.audios = [AudioItem(**a) for a in data.get("audios", [])]
            self.pps = float(data.get("pps", self.pps))
            self.graphics_by_clip.clear(); self.audio_graphics_by_clip.clear()
            self.scene.clear(); self.scene = TimelineScene(self.pps); self.timeline.setScene(self.scene)
            if hasattr(self, "_theme_mode"):
                self.scene.set_theme(self._theme_mode)
                self.timeline.set_theme(self._theme_mode)
            for c in self.clips:
                gi = self.scene.add_clip_item(c)
                gi.moved.connect(self.on_clip_moved)
                self.graphics_by_clip[self._gi_key(c)] = gi

            for a in self.audios:
                gi = self.scene.add_audio_item(a)
                gi.moved.connect(self.on_audio_moved)
                self.audio_graphics_by_clip[self._agi_key(a)] = gi

            self.refresh_clip_list_labels(); self.refresh_audio_list_labels()
            self.project_path = path; self._rebuild_sorted()
            self._on_timeline_changed(hard=True)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Laden fehlgeschlagen", str(e))

    def on_save_project(self):
        if not self.project_path:
            self.on_save_project_as(); return
        self._write_project(self.project_path)

    def on_save_project_as(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Project", "project.sedit.json", "Simpledit (*.sedit.json)")
        if not path: return
        if not path.endswith(".sedit.json"): path += ".sedit.json"
        self._write_project(path); self.project_path = path

    def _write_project(self, path: str):
        from dataclasses import asdict
        data = {"clips": [asdict(c) for c in self.clips], "audios": [asdict(a) for a in self.audios], "version": "2.4.1", "pps": self.pps}
        with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=2, ensure_ascii=False)

    def _confirm_discard(self) -> bool:
        if not self.clips and not self.audios: return True
        return QtWidgets.QMessageBox.question(self, "Discard Project?", "Discard current project?") == QtWidgets.QMessageBox.Yes

    def on_import(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select Videos", "", "Videos (*.mp4 *.mov *.mkv *.avi)")
        if not paths: return
        last_end = max([c.start_time + c.trimmed_length() for c in self.clips], default=0.0)
        for p in paths:
            try:
                clip = VideoFileClip(p); dur = float(clip.duration); clip.close()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Fehler beim Lesen", f"{p}\n\n{e}"); continue
            c = ClipItem(path=p, duration=dur, trim_in=0.0, trim_out=dur, start_time=last_end)
            last_end += c.trimmed_length(); self.clips.append(c)
            gi = self.scene.add_clip_item(c)
            gi.moved.connect(self.on_clip_moved)
            self.graphics_by_clip[self._gi_key(c)] = gi

        self.refresh_clip_list_labels()
        self._on_timeline_changed(hard=True)
        if self.list_clips.currentRow() == -1 and self.clips: self.list_clips.setCurrentRow(0)

    def on_import_audio(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select Audio", "", "Audio (*.mp3 *.wav *.m4a *.aac *.flac)")
        if not paths: return
        last_end = max([a.start_time + a.trimmed_length() for a in self.audios], default=0.0)
        for p in paths:
            try:
                ac = AudioFileClip(p); dur = float(ac.duration); ac.close()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Fehler beim Lesen (Audio)", f"{p}\n\n{e}"); continue
            a = AudioItem(path=p, duration=dur, trim_in=0.0, trim_out=dur, start_time=last_end, gain_db=0.0)
            last_end += a.trimmed_length(); self.audios.append(a)
        gi = self.scene.add_audio_item(a)
        gi.moved.connect(self.on_audio_moved)
        self.audio_graphics_by_clip[self._agi_key(a)] = gi

        self.refresh_audio_list_labels()
        self._on_timeline_changed(hard=True)
        if self.list_audio.currentRow() == -1 and self.audios: self.list_audio.setCurrentRow(0)

    def on_add_text(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Add Text Clip")
        layout = QtWidgets.QVBoxLayout(dlg)

        form = QtWidgets.QFormLayout()
        text_edit = QtWidgets.QPlainTextEdit()
        text_edit.setPlaceholderText("Type your text...")
        text_edit.setFixedHeight(120)
        dur_spin = QtWidgets.QDoubleSpinBox()
        dur_spin.setRange(0.1, 600.0)
        dur_spin.setDecimals(2)
        dur_spin.setSingleStep(0.5)
        dur_spin.setValue(3.0)
        size_spin = QtWidgets.QSpinBox()
        size_spin.setRange(10, 200)
        size_spin.setValue(64)
        form.addRow("Text:", text_edit)
        form.addRow("Duration (s):", dur_spin)
        form.addRow("Font Size:", size_spin)
        layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if hasattr(self, "_apply_dialog_theme"):
            self._apply_dialog_theme(dlg)

        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return

        text = text_edit.toPlainText().strip()
        if not text:
            QtWidgets.QMessageBox.warning(self, "Missing text", "Please enter some text.")
            return

        duration = float(dur_spin.value())
        last_end = max([c.start_time + c.trimmed_length() for c in self.clips], default=0.0)
        c = ClipItem(
            path="",
            duration=duration,
            trim_in=0.0,
            trim_out=duration,
            start_time=last_end,
            layer=MAX_VIDEO_LAYER,
            clip_type="text",
            text=text,
            text_size=int(size_spin.value()),
            text_color="#FFFFFF",
            bg_color="transparent",
        )
        self.clips.append(c)
        gi = self.scene.add_clip_item(c)
        gi.moved.connect(self.on_clip_moved)
        self.graphics_by_clip[self._gi_key(c)] = gi

        self.refresh_clip_list_labels()
        self._on_timeline_changed(hard=True)
        if self.clips:
            idx = self.clips.index(c)
            self.list_clips.setCurrentRow(idx)
            self._last_selection_kind = "clip"
            if hasattr(self, "_update_text_inspector"):
                self._update_text_inspector(c)

    def on_remove(self):
        kind = getattr(self, "_last_selection_kind", None)

        if kind == "audio":
            rowa = self.list_audio.currentRow()
            if 0 <= rowa < len(self.audios):
                a = self.audios.pop(rowa)
                gi = self.audio_graphics_by_clip.pop(self._agi_key(a), None)
                if gi: self.scene.removeItem(gi)
                self.refresh_audio_list_labels()
                self._on_timeline_changed(hard=True)
                return

        if kind == "clip":
            row = self.list_clips.currentRow()
            if 0 <= row < len(self.clips):
                c = self.clips.pop(row)
                gi = self.graphics_by_clip.pop(self._gi_key(c), None)
                if gi: self.scene.removeItem(gi)
                self.refresh_clip_list_labels()
                self._on_timeline_changed(hard=True)
                return

        rowa = self.list_audio.currentRow()
        if self.list_audio.selectedIndexes() and 0 <= rowa < len(self.audios):
            a = self.audios.pop(rowa)
            gi = self.audio_graphics_by_clip.pop(self._agi_key(a), None)
            if gi: self.scene.removeItem(gi)
            self.refresh_audio_list_labels()
            self._on_timeline_changed(hard=True)
            self._last_selection_kind = "audio"
            return

        row = self.list_clips.currentRow()
        if self.list_clips.selectedIndexes() and 0 <= row < len(self.clips):
            c = self.clips.pop(row)
            gi = self.graphics_by_clip.pop(self._gi_key(c), None)
            if gi: self.scene.removeItem(gi)
            self.refresh_clip_list_labels()
            self._on_timeline_changed(hard=True)
            self._last_selection_kind = "clip"
            return

        items = self.scene.selectedItems() if self.scene else []
        for it in items:
            if isinstance(it, AudioGraphicsItem):
                try:
                    idx = self.audios.index(it.model)
                except ValueError:
                    idx = -1
                if idx >= 0:
                    a = self.audios.pop(idx)
                    gi = self.audio_graphics_by_clip.pop(self._agi_key(a), None)
                    if gi: self.scene.removeItem(gi)
                    self.refresh_audio_list_labels()
                    self._on_timeline_changed(hard=True)
                    self._last_selection_kind = "audio"
                    return

        for it in items:
            if isinstance(it, ClipGraphicsItem):
                try:
                    idx = self.clips.index(it.model)
                except ValueError:
                    idx = -1
                if idx >= 0:
                    c = self.clips.pop(idx)
                    gi = self.graphics_by_clip.pop(self._gi_key(c), None)
                    if gi: self.scene.removeItem(gi)
                    self.refresh_clip_list_labels()
                    self._on_timeline_changed(hard=True)
                    self._last_selection_kind = "clip"
                    return
