import bisect
import time
import traceback
from typing import Optional

from PySide6 import QtWidgets, QtGui, QtCore

from models import ClipItem, AudioItem
from utils import fmt_time


class EditorPlaybackMixin:
    def on_preview_quality_changed(self, text: str):
        mapping = {"Auto": 0, "720p": 720, "540p": 540, "360p": 360, "240p": 240, "144p": 144}
        self.preview_height = mapping.get(text, 360)
        c = self._clip_at_time(self.current_time)
        if c:
            local = c.trim_in + (self.current_time - c.start_time)
            self._request_frame(c.path, local)

    def on_preview_fps_changed(self, text: str):
        try:
            self.preview_fps = int(text)
        except ValueError:
            self.preview_fps = 30

    def on_toggle_audio_enabled(self, checked: bool):
        self.audio_enabled = checked
        self.action_audio_toggle.setText("Audio: On" if checked else "Audio: Off")
        if not checked:
            self.audio_engine.pause()
        else:
            if self.playing:
                self.audio_engine.play(self.current_time)

    def on_toggle_play(self):
        try:
            has_anything = bool(self._clip_at_time(self.current_time) or self._audio_at_time(self.current_time))
            if not self.playing and not has_anything:
                self.action_play.setText("Play")
                return

            self.playing = not self.playing
            self.action_play.setText("Pause" if self.playing else "Play")

            if self.playing:
                self._last_tick_ns = time.perf_counter_ns()
                self.play_timer.start()

                if self.audio_enabled:
                    self.audio_engine.play(self.current_time)
            else:
                self.play_timer.stop()
                self._last_tick_ns = None
                self.audio_engine.pause()
        except Exception as e:
            traceback.print_exc()
            self.playing = False
            self.play_timer.stop()
            try:
                self.audio_engine.pause()
            except:
                pass
            self.action_play.setText("Play")

    def _tick_playback(self):
        if self.playing and self.audio_enabled:
            t = self.audio_engine.time()
            self.seek(t, from_player=True)
            return

        if self.playing and not self.audio_enabled:
            now_ns = time.perf_counter_ns()
            if getattr(self, "_last_tick_ns", None) is None:
                self._last_tick_ns = now_ns
                return
            dt = (now_ns - self._last_tick_ns) / 1e9
            self._last_tick_ns = now_ns
            if dt < 0:
                dt = 0
            self.seek(self.current_time + dt, from_player=True)

    def _clip_at_time(self, t: float) -> Optional[ClipItem]:
        if not getattr(self, "_sorted_by_start", None): return None
        i = bisect.bisect_right(self._sorted_starts, t) - 1
        if i >= 0:
            c = self._sorted_by_start[i]
            if t < c.start_time + c.trimmed_length() - 1e-6: return c
        return None

    def _audio_at_time(self, t: float) -> Optional[AudioItem]:
        if not getattr(self, "_sorted_audio_by_start", None): return None
        i = bisect.bisect_right(self._sorted_audio_starts, t) - 1
        if i >= 0:
            a = self._sorted_audio_by_start[i]
            if t < a.start_time + a.trimmed_length() - 1e-6: return a
        return None

    def seek(self, t: float, from_player: bool=False):
        self.current_time = max(0.0, t)
        self.lbl_time.setText(fmt_time(self.current_time))
        self.scene.update_playhead_x(self.current_time)

        now_ms = QtCore.QTime.currentTime().msecsSinceStartOfDay()
        if not hasattr(self, "_last_preview_at_ms"):
            self._last_preview_at_ms = -1

        c = self._clip_at_time(self.current_time)
        need_preview = False
        if not from_player:
            need_preview = True
        else:
            interval = int(1000 / self.preview_fps)
            if now_ms - self._last_preview_at_ms >= interval:
                need_preview = True

        if c and need_preview:
            local = c.trim_in + (self.current_time - c.start_time)
            self._request_frame(c.path, local)
            self._last_preview_at_ms = now_ms

        if self.audio_enabled and not from_player:
            self.audio_engine.seek(self.current_time)

    def _request_frame(self, path: str, t_local: float):
        self.frame_thread.request(path, t_local, self.video_widget.width(), self.video_widget.height(), self.preview_height)

    def _on_frame_ready(self, qimg: QtGui.QImage):
        img = qimg

        c = self._clip_at_time(self.current_time)
        if c and getattr(c, "effects", None):
            from effects import apply_chain_qimage
            try:
                img = apply_chain_qimage(img, c.effects)
            except Exception as e:
                print("[effects] preview error:", e)

        pix = QtGui.QPixmap.fromImage(img)
        if isinstance(self.video_widget, QtWidgets.QLabel):
            self.video_widget.setPixmap(pix)

    def _on_frame_error(self, msg: str):
        if isinstance(self.video_widget, QtWidgets.QLabel):
            self.video_widget.setText(f"Frame could not be loaded:\n{msg}")

    def mark_in(self):
        c = self.current_clip()
        if not c: return
        if not (c.start_time <= self.current_time <= c.start_time + c.trimmed_length()): return
        new_ti = c.trim_in + (self.current_time - c.start_time)
        new_ti = max(0.0, min(new_ti, c.safe_out()-0.05))
        c.trim_in = new_ti
        gi = self.graphics_by_clip.get(self._gi_key(c))
        if gi:
            gi.update_geometry(); gi._refresh_label()
        self.refresh_clip_list_labels()
        self._on_timeline_changed(hard=True)

    def mark_out(self):
        c = self.current_clip()
        if not c: return
        if not (c.start_time <= self.current_time <= c.start_time + c.trimmed_length()): return
        new_to = c.trim_in + (self.current_time - c.start_time)
        new_to = max(c.trim_in+0.05, min(new_to, c.duration))
        c.trim_out = new_to
        gi = self.graphics_by_clip.get(self._gi_key(c))
        if gi:
            gi.update_geometry(); gi._refresh_label()
        self.refresh_clip_list_labels()
        self._on_timeline_changed(hard=True)

    def split_at_playhead(self):
        t = self.current_time
        c = self._clip_at_time(t)
        if c:
            local = c.trim_in + (t - c.start_time); eps = 1e-4
            if c.trim_in + eps < local < c.safe_out() - eps:
                old_out = c.safe_out(); c.trim_out = local
                new_c = ClipItem(path=c.path, duration=c.duration, trim_in=local, trim_out=old_out, start_time=t)
                self.clips.append(new_c)
                gi = self.scene.add_clip_item(new_c)
                gi.moved.connect(self.on_clip_moved)

                self.graphics_by_clip[self._gi_key(new_c)] = gi
                gi_left = self.graphics_by_clip.get(self._gi_key(c))
                if gi_left:
                    gi_left.update_geometry(); gi_left._refresh_label()
                gi.update_geometry(); gi._refresh_label()
                self.refresh_clip_list_labels()
                self._on_timeline_changed(hard=True)
                return
        a = self._audio_at_time(t)
        if a:
            local = a.trim_in + (t - a.start_time); eps = 1e-4
            if a.trim_in + eps < local < a.safe_out() - eps:
                old_out = a.safe_out(); a.trim_out = local
                new_a = AudioItem(path=a.path, duration=a.duration, trim_in=local, trim_out=old_out, start_time=t, gain_db=a.gain_db)
                self.audios.append(new_a)
                gi = self.scene.add_audio_item(new_a)
                gi.moved.connect(self.on_audio_moved)

                self.audio_graphics_by_clip[self._agi_key(new_a)] = gi
                gi_left = self.audio_graphics_by_clip.get(self._agi_key(a))
                if gi_left:
                    gi_left.update_geometry(); gi_left._refresh_label()
                gi.update_geometry(); gi._refresh_label()
                self.refresh_audio_list_labels()
                self._on_timeline_changed(hard=True)

    def timeline_length(self) -> float:
        end_v = max([c.start_time + c.trimmed_length() for c in self.clips], default=0.0)
        end_a = max([a.start_time + a.trimmed_length() for a in self.audios], default=0.0)
        return max(end_v, end_a)
