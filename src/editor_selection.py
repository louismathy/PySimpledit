import os
from typing import Optional

from PySide6 import QtWidgets, QtCore, QtGui

from models import ClipItem, AudioItem
from timeline import ClipGraphicsItem, AudioGraphicsItem
from editor_thumbnails import ThumbnailWorker


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
            label = f"{c.display_name()}  t={c.start_time:.2f}s  [{c.trim_in:.2f}-{c.safe_out():.2f}s]"
            item = QtWidgets.QListWidgetItem(label)
            thumb_key = self._thumb_key(c)
            item.setData(QtCore.Qt.UserRole, thumb_key)
            item.setSizeHint(QtCore.QSize(0, 72))
            cached = self._thumb_cache.get(thumb_key)
            if cached:
                item.setIcon(QtGui.QIcon(cached))
            else:
                if c.is_text():
                    pix = self._render_text_thumbnail(c)
                    if pix is not None:
                        self._thumb_cache[thumb_key] = pix
                        item.setIcon(QtGui.QIcon(pix))
                    else:
                        item.setIcon(QtGui.QIcon(self._placeholder_thumbnail()))
                else:
                    fallback = self._cached_thumbnail_for_path(c.path)
                    if fallback is not None:
                        self._thumb_cache[thumb_key] = fallback
                        item.setIcon(QtGui.QIcon(fallback))
                    else:
                        item.setIcon(QtGui.QIcon(self._placeholder_thumbnail()))
                        self._queue_thumbnail(c)
            self.list_clips.addItem(item)
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

    def _thumb_key(self, clip: ClipItem) -> str:
        if clip.is_text():
            return (
                f"text|{clip.text}|{clip.text_size}|{clip.text_color}|{clip.bg_color}|"
                f"{clip.text_font}|{clip.text_method}|{clip.text_align}|{clip.text_v_align}|"
                f"{clip.text_stroke_color}|{clip.text_stroke_width}"
            )
        return f"{clip.path}|{clip.trim_in:.3f}"

    def _placeholder_thumbnail(self) -> QtGui.QPixmap:
        size = self.list_clips.iconSize()
        img = QtGui.QImage(size, QtGui.QImage.Format_RGB32)
        img.fill(QtGui.QColor("#E9EEF7"))
        pix = QtGui.QPixmap.fromImage(img)
        return pix

    def _queue_thumbnail(self, clip: ClipItem):
        if clip.is_text():
            return
        if getattr(self, "_thumb_pause", False):
            return
        key = self._thumb_key(clip)
        if key in self._thumb_inflight:
            return
        self._thumb_inflight.add(key)
        worker = ThumbnailWorker(key, clip.path, clip.trim_in, self.list_clips.iconSize(), self._thumb_signals)
        self._thumb_pool.start(worker)

    def _cached_thumbnail_for_path(self, path: str) -> Optional[QtGui.QPixmap]:
        if not path:
            return None
        prefix = f"{path}|"
        for key, pix in self._thumb_cache.items():
            if isinstance(key, str) and key.startswith(prefix):
                return pix
        return None

    def _render_text_thumbnail(self, clip: ClipItem) -> Optional[QtGui.QPixmap]:
        try:
            from text_render import render_text_qimage
            size = self.list_clips.iconSize()
            img = render_text_qimage(
                clip.text,
                size.width(),
                size.height(),
                bg_color=clip.bg_color,
                text_color=clip.text_color,
                font_path=getattr(clip, "text_font", ""),
                text_align=getattr(clip, "text_align", "center"),
                text_v_align=getattr(clip, "text_v_align", "center"),
                stroke_color=getattr(clip, "text_stroke_color", "#000000"),
                stroke_width=getattr(clip, "text_stroke_width", 0),
                method=getattr(clip, "text_method", "caption"),
                font_size=max(10, int(clip.text_size * 0.45)),
            )
            return QtGui.QPixmap.fromImage(img)
        except Exception:
            return None

    def _on_thumbnail_ready(self, key: str, img: QtGui.QImage):
        self._thumb_inflight.discard(key)
        if img.isNull():
            return
        pix = QtGui.QPixmap.fromImage(img)
        self._thumb_cache[key] = pix
        for i in range(self.list_clips.count()):
            item = self.list_clips.item(i)
            if item and item.data(QtCore.Qt.UserRole) == key:
                item.setIcon(QtGui.QIcon(pix))

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
            self._update_text_inspector(None)
            return

        c = self.clips[row]
        self.lbl_path.setText("Text Clip" if c.is_text() else c.path)
        self.lbl_duration.setText(f"{c.duration:.3f}s")
        self.spin_trim_in.setMaximum(c.duration)
        self.spin_trim_out.setMaximum(c.duration)
        self.spin_trim_in.setValue(c.trim_in)
        self.spin_trim_out.setValue(c.safe_out())
        self.spin_start.setValue(c.start_time)

        if c.is_text():
            if hasattr(self, "_render_text_preview"):
                self._render_text_preview(c)
        else:
            self._request_frame(c.path, c.trim_in)
        self._refresh_effects_ui()
        self._update_text_inspector(c)

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
        if c.is_text():
            if hasattr(self, "_render_text_preview"):
                self._render_text_preview(c)
        else:
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
            self._update_text_inspector(None)
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
        self._update_text_inspector(None)

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

    def on_apply_text(self):
        c = self.current_clip()
        if not c or not c.is_text():
            return
        if hasattr(self, "text_edit"):
            c.text = self.text_edit.toPlainText()
        if hasattr(self, "spin_text_size"):
            c.text_size = int(self.spin_text_size.value())
        if hasattr(self, "combo_text_font"):
            c.text_font = str(self.combo_text_font.currentData() or "")
        if hasattr(self, "combo_text_align"):
            c.text_align = str(self.combo_text_align.currentText())
        if hasattr(self, "combo_text_valign"):
            c.text_v_align = str(self.combo_text_valign.currentText())
        if hasattr(self, "combo_text_method"):
            c.text_method = str(self.combo_text_method.currentText())
        if hasattr(self, "edit_text_color"):
            c.text_color = str(self.edit_text_color.text().strip() or "#FFFFFF")
        if hasattr(self, "edit_text_bg"):
            c.bg_color = str(self.edit_text_bg.text().strip() or "transparent")
        if hasattr(self, "edit_text_stroke"):
            c.text_stroke_color = str(self.edit_text_stroke.text().strip() or "#000000")
        if hasattr(self, "spin_text_stroke"):
            c.text_stroke_width = int(self.spin_text_stroke.value())
        gi = self.graphics_by_clip.get(self._gi_key(c))
        if gi:
            gi._refresh_label()
            gi.update()
        self.refresh_clip_list_labels()
        self._on_timeline_changed(hard=True)
        if hasattr(self, "_render_text_preview"):
            self._render_text_preview(c)

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
            self._update_text_inspector(None)
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
            self._update_text_inspector(clip)

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
            self._update_text_inspector(None)

    def _update_text_inspector(self, clip: Optional[ClipItem]):
        if not hasattr(self, "text_edit"):
            return
        is_text = bool(clip and clip.is_text())
        self.text_edit.setEnabled(is_text)
        self.spin_text_size.setEnabled(is_text)
        if hasattr(self, "combo_text_font"):
            self.combo_text_font.setEnabled(is_text)
        if hasattr(self, "combo_text_align"):
            self.combo_text_align.setEnabled(is_text)
        if hasattr(self, "combo_text_valign"):
            self.combo_text_valign.setEnabled(is_text)
        if hasattr(self, "combo_text_method"):
            self.combo_text_method.setEnabled(is_text)
        if hasattr(self, "edit_text_color"):
            self.edit_text_color.setEnabled(is_text)
        if hasattr(self, "edit_text_bg"):
            self.edit_text_bg.setEnabled(is_text)
        if hasattr(self, "edit_text_stroke"):
            self.edit_text_stroke.setEnabled(is_text)
        if hasattr(self, "spin_text_stroke"):
            self.spin_text_stroke.setEnabled(is_text)
        self.btn_apply_text.setEnabled(is_text)
        if is_text:
            self.text_edit.blockSignals(True)
            self.text_edit.setPlainText(clip.text)
            self.text_edit.blockSignals(False)
            self.spin_text_size.blockSignals(True)
            self.spin_text_size.setValue(int(clip.text_size))
            self.spin_text_size.blockSignals(False)
            if hasattr(self, "combo_text_font"):
                self.combo_text_font.blockSignals(True)
                desired = getattr(clip, "text_font", "")
                idx = self.combo_text_font.findData(desired)
                if idx < 0:
                    idx = 0
                self.combo_text_font.setCurrentIndex(idx)
                self.combo_text_font.blockSignals(False)
            if hasattr(self, "combo_text_align"):
                self.combo_text_align.blockSignals(True)
                self.combo_text_align.setCurrentText(getattr(clip, "text_align", "center"))
                self.combo_text_align.blockSignals(False)
            if hasattr(self, "combo_text_valign"):
                self.combo_text_valign.blockSignals(True)
                self.combo_text_valign.setCurrentText(getattr(clip, "text_v_align", "center"))
                self.combo_text_valign.blockSignals(False)
            if hasattr(self, "combo_text_method"):
                self.combo_text_method.blockSignals(True)
                self.combo_text_method.setCurrentText(getattr(clip, "text_method", "caption"))
                self.combo_text_method.blockSignals(False)
            if hasattr(self, "edit_text_color"):
                self.edit_text_color.blockSignals(True)
                self.edit_text_color.setText(getattr(clip, "text_color", "#FFFFFF"))
                self.edit_text_color.blockSignals(False)
            if hasattr(self, "edit_text_bg"):
                self.edit_text_bg.blockSignals(True)
                self.edit_text_bg.setText(getattr(clip, "bg_color", "transparent"))
                self.edit_text_bg.blockSignals(False)
            if hasattr(self, "edit_text_stroke"):
                self.edit_text_stroke.blockSignals(True)
                self.edit_text_stroke.setText(getattr(clip, "text_stroke_color", "#000000"))
                self.edit_text_stroke.blockSignals(False)
            if hasattr(self, "spin_text_stroke"):
                self.spin_text_stroke.blockSignals(True)
                self.spin_text_stroke.setValue(int(getattr(clip, "text_stroke_width", 0)))
                self.spin_text_stroke.blockSignals(False)
        else:
            self.text_edit.blockSignals(True)
            self.text_edit.setPlainText("")
            self.text_edit.blockSignals(False)
            self.spin_text_size.blockSignals(True)
            self.spin_text_size.setValue(64)
            self.spin_text_size.blockSignals(False)
            if hasattr(self, "combo_text_font"):
                self.combo_text_font.blockSignals(True)
                self.combo_text_font.setCurrentIndex(0)
                self.combo_text_font.blockSignals(False)
            if hasattr(self, "combo_text_align"):
                self.combo_text_align.blockSignals(True)
                self.combo_text_align.setCurrentText("center")
                self.combo_text_align.blockSignals(False)
            if hasattr(self, "combo_text_valign"):
                self.combo_text_valign.blockSignals(True)
                self.combo_text_valign.setCurrentText("center")
                self.combo_text_valign.blockSignals(False)
            if hasattr(self, "combo_text_method"):
                self.combo_text_method.blockSignals(True)
                self.combo_text_method.setCurrentText("caption")
                self.combo_text_method.blockSignals(False)
            if hasattr(self, "edit_text_color"):
                self.edit_text_color.blockSignals(True)
                self.edit_text_color.setText("#FFFFFF")
                self.edit_text_color.blockSignals(False)
            if hasattr(self, "edit_text_bg"):
                self.edit_text_bg.blockSignals(True)
                self.edit_text_bg.setText("transparent")
                self.edit_text_bg.blockSignals(False)
            if hasattr(self, "edit_text_stroke"):
                self.edit_text_stroke.blockSignals(True)
                self.edit_text_stroke.setText("#000000")
                self.edit_text_stroke.blockSignals(False)
            if hasattr(self, "spin_text_stroke"):
                self.spin_text_stroke.blockSignals(True)
                self.spin_text_stroke.setValue(0)
                self.spin_text_stroke.blockSignals(False)
