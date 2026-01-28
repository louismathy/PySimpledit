import json
import os
import tempfile
from typing import Optional, Tuple

from PySide6 import QtWidgets, QtCore

from moviepy import VideoFileClip, AudioFileClip

from models import ClipItem, AudioItem
from timeline import TimelineScene, ClipGraphicsItem, AudioGraphicsItem, MAX_VIDEO_LAYER
from utils import make_audio_subclip, debug_log


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
                clip = VideoFileClip(p, audio=False); dur = float(clip.duration); clip.close()
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
        font_combo = QtWidgets.QComboBox()
        font_combo.addItem("Default", "")
        try:
            from text_render import list_available_fonts
            for label, path in list_available_fonts():
                font_combo.addItem(label, path)
        except Exception:
            pass
        form.addRow("Text:", text_edit)
        form.addRow("Duration (s):", dur_spin)
        form.addRow("Font Size:", size_spin)
        form.addRow("Font:", font_combo)
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
            text_font=str(font_combo.currentData() or ""),
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

    def _subtitle_source_from_selection(self) -> Optional[Tuple[str, float, float, float]]:
        items = self.scene.selectedItems() if self.scene else []
        for it in items:
            if isinstance(it, ClipGraphicsItem):
                clip = it.model
                if clip and not clip.is_text():
                    return (clip.path, clip.start_time, clip.trim_in, clip.safe_out())
            if isinstance(it, AudioGraphicsItem):
                aud = it.model
                if aud:
                    return (aud.path, aud.start_time, aud.trim_in, aud.safe_out())

        c = self.current_clip() if hasattr(self, "current_clip") else None
        if c and not c.is_text():
            return (c.path, c.start_time, c.trim_in, c.safe_out())
        a = self.current_audio() if hasattr(self, "current_audio") else None
        if a:
            return (a.path, a.start_time, a.trim_in, a.safe_out())

        return None

    def _extract_audio_for_subtitles(self, path: str, start: float, end: float) -> str:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tmp_path = tmp.name
        tmp.close()
        clip = None
        sub = None
        try:
            clip = AudioFileClip(path)
            sub = make_audio_subclip(clip, start, end)
            sub.write_audiofile(
                tmp_path,
                fps=16000,
                nbytes=2,
                codec="pcm_s16le",
                ffmpeg_params=["-ac", "1"],
                logger=None,
            )
        finally:
            try:
                if sub:
                    sub.close()
            except Exception:
                pass
            try:
                if clip:
                    clip.close()
            except Exception:
                pass
        return tmp_path

    def _wrap_subtitle_text(self, text: str, max_chars: int) -> str:
        text = (text or "").strip()
        if not text or max_chars <= 0 or len(text) <= max_chars:
            return text
        words = text.split()
        if not words:
            return text
        lines = []
        current = words[0]
        for word in words[1:]:
            if len(current) + 1 + len(word) <= max_chars:
                current += " " + word
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return "\n".join(lines)

    def _apply_subtitle_segments(
        self,
        segments: list[dict],
        start_time: float,
        text_size: int,
        max_chars: int,
    ) -> list[ClipItem]:
        default_font = ""
        try:
            from text_render import list_available_fonts
            fonts = list_available_fonts()
            if fonts:
                default_font = fonts[0][1]
        except Exception:
            pass
        created: list[ClipItem] = []
        for seg in segments:
            seg_start = float(seg.get("start", 0.0))
            seg_end = float(seg.get("end", 0.0))
            if seg_end < seg_start:
                seg_start, seg_end = seg_end, seg_start
            duration = seg_end - seg_start
            if duration <= 0.05:
                continue
            text = self._wrap_subtitle_text(str(seg.get("text", "")).strip(), max_chars)
            if not text:
                continue
            c = ClipItem(
                path="",
                duration=duration,
                trim_in=0.0,
                trim_out=duration,
                start_time=start_time + max(0.0, seg_start),
                layer=MAX_VIDEO_LAYER,
                clip_type="text",
                text=text,
                text_size=int(text_size),
                text_color="#FFFFFF",
                text_font=default_font,
                bg_color="transparent",
            )
            created.append(c)
        return created

    def on_auto_subtitles(self):
        source = self._subtitle_source_from_selection()
        if not source:
            QtWidgets.QMessageBox.information(
                self,
                "Auto Subtitles",
                "Select a video or audio item in the timeline or list first.",
            )
            return

        src_path, src_start_time, src_trim_in, src_trim_out = source
        if not src_path or not os.path.exists(src_path):
            QtWidgets.QMessageBox.warning(self, "Auto Subtitles", "The source file was not found.")
            return

        if (src_trim_out - src_trim_in) <= 0.05:
            QtWidgets.QMessageBox.warning(self, "Auto Subtitles", "Trim range is too short to transcribe.")
            return

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Auto Generate Subtitles")
        layout = QtWidgets.QVBoxLayout(dlg)

        form = QtWidgets.QFormLayout()
        model_combo = QtWidgets.QComboBox()
        model_combo.addItems(["tiny", "base", "small", "medium", "large"])
        model_combo.setCurrentText("small")
        lang_combo = QtWidgets.QComboBox()
        lang_combo.setEditable(True)
        lang_combo.addItems(["Auto", "en", "de", "es", "fr", "it", "pt", "ja", "zh"])
        lang_combo.setCurrentText("Auto")
        size_spin = QtWidgets.QSpinBox()
        size_spin.setRange(10, 200)
        size_spin.setValue(56)
        wrap_spin = QtWidgets.QSpinBox()
        wrap_spin.setRange(20, 120)
        wrap_spin.setValue(42)
        form.addRow("Model:", model_combo)
        form.addRow("Language:", lang_combo)
        form.addRow("Font Size:", size_spin)
        form.addRow("Max Chars/Line:", wrap_spin)
        layout.addLayout(form)

        info = QtWidgets.QLabel("Uses the Whisper model (openai-whisper).")
        info.setWordWrap(True)
        layout.addWidget(info)

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

        model_name = model_combo.currentText().strip() or "small"
        lang_text = lang_combo.currentText().strip()
        language = None if lang_text.lower() in {"auto", ""} else lang_text
        font_size = int(size_spin.value())
        max_chars = int(wrap_spin.value())

        if getattr(self, "_subtitle_thread", None) and self._subtitle_thread.isRunning():
            QtWidgets.QMessageBox.warning(self, "Auto Subtitles", "Subtitle generation is already running.")
            return

        progress = QtWidgets.QProgressDialog("Transcribing audio with Whisper...", "", 0, 100, self)
        progress.setWindowTitle("Auto Subtitles")
        progress.setCancelButton(None)
        progress.setWindowModality(QtCore.Qt.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()

        try:
            audio_path = self._extract_audio_for_subtitles(src_path, src_trim_in, src_trim_out)
        except Exception as e:
            progress.close()
            QtWidgets.QMessageBox.critical(self, "Auto Subtitles", str(e))
            return

        self._subtitle_progress = progress
        self._subtitle_progress_timer = QtCore.QTimer(self)
        self._subtitle_progress_timer.setInterval(200)
        self._subtitle_progress_elapsed = QtCore.QElapsedTimer()
        self._subtitle_progress_elapsed.start()
        self._subtitle_progress_expected = max(1.0, float(src_trim_out - src_trim_in))

        def _tick_progress():
            prog = getattr(self, "_subtitle_progress", None)
            if not prog:
                return
            elapsed = float(self._subtitle_progress_elapsed.elapsed()) / 1000.0
            frac = min(0.95, elapsed / self._subtitle_progress_expected)
            prog.setValue(int(frac * 100))

        self._subtitle_progress_timer.timeout.connect(_tick_progress)
        self._subtitle_progress_timer.start()
        self._subtitle_job = {
            "audio_path": audio_path,
            "start_time": src_start_time,
            "font_size": font_size,
            "max_chars": max_chars,
        }

        class _WhisperWorker(QtCore.QObject):
            finished = QtCore.Signal(list)
            failed = QtCore.Signal(str)

            def __init__(self, a_path: str, model: str, lang: Optional[str]):
                super().__init__()
                self._a_path = a_path
                self._model = model
                self._lang = lang

            @QtCore.Slot()
            def run(self):
                try:
                    from subtitle_whisper import transcribe_whisper
                    segments = transcribe_whisper(self._a_path, self._model, self._lang)
                    self.finished.emit(segments)
                except Exception as exc:
                    self.failed.emit(str(exc))

        self._subtitle_thread = QtCore.QThread(self)
        self._subtitle_worker = _WhisperWorker(audio_path, model_name, language)
        self._subtitle_worker.moveToThread(self._subtitle_thread)
        self._subtitle_thread.started.connect(self._subtitle_worker.run)
        self._subtitle_worker.finished.connect(self._on_subtitle_job_finished)
        self._subtitle_worker.failed.connect(self._on_subtitle_job_failed)
        self._subtitle_worker.finished.connect(self._subtitle_thread.quit)
        self._subtitle_worker.failed.connect(self._subtitle_thread.quit)
        self._subtitle_thread.start()

    def _finalize_subtitle_job(self):
        progress = getattr(self, "_subtitle_progress", None)
        if progress:
            progress.close()
        self._subtitle_progress = None
        timer = getattr(self, "_subtitle_progress_timer", None)
        if timer:
            timer.stop()
        self._subtitle_progress_timer = None
        self._subtitle_progress_elapsed = None
        self._subtitle_progress_expected = None

        thread = getattr(self, "_subtitle_thread", None)
        worker = getattr(self, "_subtitle_worker", None)
        if worker:
            worker.deleteLater()
        if thread:
            thread.deleteLater()
        self._subtitle_thread = None
        self._subtitle_worker = None

        job = getattr(self, "_subtitle_job", None) or {}
        audio_path = job.get("audio_path")
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception:
                pass
        self._subtitle_job = None

    def _on_subtitle_job_failed(self, msg: str):
        self._finalize_subtitle_job()
        QtWidgets.QMessageBox.critical(self, "Auto Subtitles", msg)

    def _on_subtitle_job_finished(self, segments: list):
        job = getattr(self, "_subtitle_job", None) or {}
        start_time = float(job.get("start_time", 0.0))
        font_size = int(job.get("font_size", 56))
        max_chars = int(job.get("max_chars", 42))

        created = self._apply_subtitle_segments(segments, start_time, font_size, max_chars)
        progress = getattr(self, "_subtitle_progress", None)
        if progress:
            progress.setValue(100)
        self._finalize_subtitle_job()

        if not created:
            QtWidgets.QMessageBox.information(self, "Auto Subtitles", "No speech segments were detected.")
            return

        for c in created:
            self.clips.append(c)
            gi = self.scene.add_clip_item(c)
            gi.moved.connect(self.on_clip_moved)
            self.graphics_by_clip[self._gi_key(c)] = gi

        self.refresh_clip_list_labels()
        self._on_timeline_changed(hard=True)
        self._last_selection_kind = "clip"
        if self.clips:
            try:
                idx = self.clips.index(created[0])
                self.list_clips.setCurrentRow(idx)
            except ValueError:
                pass
    def on_remove(self):
        debug_log("remove.start")
        if getattr(self, "playing", False):
            try:
                self.on_toggle_play()
            except Exception:
                pass
        try:
            if hasattr(self, "audio_engine"):
                self.audio_engine.stop()
        except Exception:
            pass

        kind = getattr(self, "_last_selection_kind", None)

        if kind == "audio":
            rowa = self.list_audio.currentRow()
            if 0 <= rowa < len(self.audios):
                a = self.audios.pop(rowa)
                gi = self.audio_graphics_by_clip.pop(self._agi_key(a), None)
                if gi: self.scene.removeItem(gi)
                self.refresh_audio_list_labels()
                self._on_timeline_changed(hard=True)
                debug_log("remove.audio.list")
                return

        if kind == "clip":
            row = self.list_clips.currentRow()
            if 0 <= row < len(self.clips):
                c = self.clips.pop(row)
                gi = self.graphics_by_clip.pop(self._gi_key(c), None)
                if gi: self.scene.removeItem(gi)
                self.refresh_clip_list_labels()
                try:
                    if hasattr(self, "_thumb_pool"):
                        self._thumb_pool.clear()
                except Exception:
                    pass
                try:
                    if hasattr(self, "_thumb_inflight"):
                        self._thumb_inflight.clear()
                except Exception:
                    pass
                self._on_timeline_changed(hard=True)
                debug_log("remove.clip.list")
                return

        rowa = self.list_audio.currentRow()
        if self.list_audio.selectedIndexes() and 0 <= rowa < len(self.audios):
            a = self.audios.pop(rowa)
            gi = self.audio_graphics_by_clip.pop(self._agi_key(a), None)
            if gi: self.scene.removeItem(gi)
            self.refresh_audio_list_labels()
            self._on_timeline_changed(hard=True)
            self._last_selection_kind = "audio"
            debug_log("remove.audio.selection")
            return

        row = self.list_clips.currentRow()
        if self.list_clips.selectedIndexes() and 0 <= row < len(self.clips):
            c = self.clips.pop(row)
            gi = self.graphics_by_clip.pop(self._gi_key(c), None)
            if gi: self.scene.removeItem(gi)
            self.refresh_clip_list_labels()
            try:
                if hasattr(self, "_thumb_pool"):
                    self._thumb_pool.clear()
            except Exception:
                pass
            try:
                if hasattr(self, "_thumb_inflight"):
                    self._thumb_inflight.clear()
            except Exception:
                pass
            self._on_timeline_changed(hard=True)
            self._last_selection_kind = "clip"
            debug_log("remove.clip.selection")
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
                    debug_log("remove.audio.timeline_item")
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
                    debug_log("remove.clip.timeline_item")
                    return
