import json

from PySide6 import QtWidgets

from moviepy import VideoFileClip, AudioFileClip

from models import ClipItem, AudioItem
from timeline import TimelineScene, ClipGraphicsItem, AudioGraphicsItem


class EditorProjectMixin:
    def on_new_project(self):
        if self._confirm_discard():
            self.audio_engine.pause()
            self.clips.clear(); self.audios.clear()
            self.graphics_by_clip.clear(); self.audio_graphics_by_clip.clear()
            self.scene.clear(); self.scene = TimelineScene(self.pps); self.timeline.setScene(self.scene)
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
