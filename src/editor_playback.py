import time
import traceback
from dataclasses import replace
from typing import Optional

from PySide6 import QtWidgets, QtGui, QtCore

from models import ClipItem, AudioItem
from utils import fmt_time, debug_log


class EditorPlaybackMixin:
    def _text_render_size(self) -> tuple[int, int]:
        settings = getattr(self, "render_settings", {})
        res = settings.get("resolution", "Auto")
        mapping = {
            "720p": (1280, 720),
            "1080p": (1920, 1080),
            "1440p": (2560, 1440),
            "4K": (3840, 2160),
        }
        return mapping.get(res, (1280, 720))

    def _text_preview_font_size(self, clip: ClipItem, target_w: int, target_h: int) -> int:
        export_w, export_h = self._text_render_size()
        if export_w <= 0 or export_h <= 0:
            return max(8, int(clip.text_size))
        scale = min(target_w / export_w, target_h / export_h)
        return max(8, int(round(clip.text_size * scale)))

    def step_frame(self, direction: int):
        fps = self.preview_fps if self.preview_fps and self.preview_fps > 0 else 30
        dt = 1.0 / fps
        self.seek(self.current_time + (dt * direction), from_player=False)

    def on_preview_quality_changed(self, text: str):
        mapping = {"Auto": 0, "720p": 720, "540p": 540, "360p": 360, "240p": 240, "144p": 144}
        self.preview_height = mapping.get(text, 360)
        c = self._clip_at_time(self.current_time)
        if c:
            if c.is_text():
                base = self._clip_below_video_at_time(self.current_time, c.layer)
                if base:
                    local = base.trim_in + (self.current_time - base.start_time)
                    w = self.video_widget.width()
                    h = self.video_widget.height()
                    req = (base.path, round(local, 4), w, h, self.preview_height)
                    self._pending_text_overlay = c
                    self._pending_text_overlay_req = req
                    self._request_frame(base.path, local)
                else:
                    self._pending_text_overlay = None
                    self._pending_text_overlay_req = None
                    self._render_text_preview(c)
            else:
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
        if checked:
            self._set_action_icon(self.action_audio_toggle, "audio_on.png")
        else:
            self._set_action_icon(self.action_audio_toggle, "audio_off.png")
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
            self._set_action_icon(self.action_play, "pause.png" if self.playing else "play.png")
            debug_log(f"play.toggle playing={self.playing} t={self.current_time:.3f}")
            if hasattr(self, "_thumb_pause"):
                self._thumb_pause = self.playing
                if self.playing:
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

            if self.playing:
                self._last_tick_ns = time.perf_counter_ns()
                self.play_timer.start()

                if self.audio_enabled:
                    self.audio_engine.play(self.current_time)
            else:
                self.play_timer.stop()
                self._last_tick_ns = None
                self.audio_engine.pause()
                try:
                    self.refresh_clip_list_labels()
                except Exception:
                    pass
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
        if self.playing:
            now_ns = time.perf_counter_ns()
            if getattr(self, "_last_tick_ns", None) is None:
                self._last_tick_ns = now_ns
                return
            dt = (now_ns - self._last_tick_ns) / 1e9
            self._last_tick_ns = now_ns
            if dt < 0:
                dt = 0
            if dt > 0.5:
                debug_log(f"tick.lag dt={dt:.3f} t={self.current_time:.3f}")
            expected = self.current_time + dt
            if self.audio_enabled:
                try:
                    at = float(self.audio_engine.time())
                except Exception:
                    at = expected
                if at >= self.current_time and abs(at - expected) < 0.5:
                    self.seek(at, from_player=True)
                else:
                    self.seek(expected, from_player=True)
            else:
                self.seek(expected, from_player=True)

    def _clip_at_time(self, t: float) -> Optional[ClipItem]:
        best = None
        best_layer = -1
        best_start = -1.0
        for c in self.clips:
            if t < c.start_time or t >= c.start_time + c.trimmed_length() - 1e-6:
                continue
            layer = getattr(c, "layer", 1)
            if layer > best_layer or (layer == best_layer and c.start_time >= best_start):
                best = c
                best_layer = layer
                best_start = c.start_time
        return best

    def _clip_below_at_time(self, t: float, top_layer: int) -> Optional[ClipItem]:
        best = None
        best_layer = -1
        best_start = -1.0
        for c in self.clips:
            if t < c.start_time or t >= c.start_time + c.trimmed_length() - 1e-6:
                continue
            layer = getattr(c, "layer", 1)
            if layer >= top_layer:
                continue
            if layer > best_layer or (layer == best_layer and c.start_time >= best_start):
                best = c
                best_layer = layer
                best_start = c.start_time
        return best

    def _clip_below_video_at_time(self, t: float, top_layer: int) -> Optional[ClipItem]:
        best = None
        best_layer = -1
        best_start = -1.0
        for c in self.clips:
            if c.is_text():
                continue
            if t < c.start_time or t >= c.start_time + c.trimmed_length() - 1e-6:
                continue
            layer = getattr(c, "layer", 1)
            if layer >= top_layer:
                continue
            if layer > best_layer or (layer == best_layer and c.start_time >= best_start):
                best = c
                best_layer = layer
                best_start = c.start_time
        return best

    def _audio_at_time(self, t: float) -> Optional[AudioItem]:
        if not getattr(self, "_sorted_audio_by_start", None): return None
        i = bisect.bisect_right(self._sorted_audio_starts, t) - 1
        if i >= 0:
            a = self._sorted_audio_by_start[i]
            if t < a.start_time + a.trimmed_length() - 1e-6: return a
        return None

    def seek(self, t: float, from_player: bool=False):
        t0 = time.perf_counter()
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
            if c.is_text():
                base = self._clip_below_video_at_time(self.current_time, c.layer)
                if base:
                    local = base.trim_in + (self.current_time - base.start_time)
                    w = self.video_widget.width()
                    h = self.video_widget.height()
                    req = (base.path, round(local, 4), w, h, self.preview_height)
                    self._pending_text_overlay = c
                    self._pending_text_overlay_req = req
                    self._request_frame(base.path, local)
                else:
                    self._pending_text_overlay = None
                    self._pending_text_overlay_req = None
                    self._render_text_preview(c)
            else:
                self._pending_text_overlay = None
                self._pending_text_overlay_req = None
                local = c.trim_in + (self.current_time - c.start_time)
                self._request_frame(c.path, local)
            self._last_preview_at_ms = now_ms
        elif not c and need_preview:
            self._set_black_preview()
            self._last_preview_at_ms = now_ms

        if self.audio_enabled and not from_player:
            self.audio_engine.seek(self.current_time)

        dt = time.perf_counter() - t0
        if dt > 0.08:
            c = self._clip_at_time(self.current_time)
            kind = "none"
            if c:
                kind = "text" if c.is_text() else "video"
            debug_log(f"seek.slow dt={dt:.3f} kind={kind} t={self.current_time:.3f}")

    def _request_frame(self, path: str, t_local: float):
        w = self.video_widget.width()
        h = self.video_widget.height()
        req = (path, round(t_local, 4), w, h, self.preview_height)
        if getattr(self, "_last_frame_req", None) == req:
            return
        self._last_frame_req = req
        self.frame_thread.request(path, t_local, w, h, self.preview_height)

    def _render_text_preview(self, clip: ClipItem):
        from text_render import render_text_qimage
        self._pending_text_overlay = None
        self._pending_text_overlay_req = None
        target_w = max(1, self.video_widget.width())
        target_h = max(1, self.video_widget.height())
        font_size = self._text_preview_font_size(clip, target_w, target_h)
        img = render_text_qimage(
            clip.text,
            target_w,
            target_h,
            bg_color=clip.bg_color,
            text_color=clip.text_color,
            font_path=getattr(clip, "text_font", ""),
            text_align=getattr(clip, "text_align", "center"),
            text_v_align=getattr(clip, "text_v_align", "center"),
            stroke_color=getattr(clip, "text_stroke_color", "#000000"),
            stroke_width=getattr(clip, "text_stroke_width", 0),
            method=getattr(clip, "text_method", "caption"),
            font_size=font_size,
        )
        self._on_frame_ready(img)

    def _set_black_preview(self):
        w = max(1, self.video_widget.width())
        h = max(1, self.video_widget.height())
        img = QtGui.QImage(w, h, QtGui.QImage.Format_RGB32)
        img.fill(QtGui.QColor(0, 0, 0))
        self._last_preview_qimg = img
        pix = QtGui.QPixmap.fromImage(img)
        if isinstance(self.video_widget, QtWidgets.QLabel):
            self.video_widget.setPixmap(pix)

    def _on_frame_ready(self, qimg: QtGui.QImage):
        img = qimg
        pending = getattr(self, "_pending_text_overlay", None)
        pending_req = getattr(self, "_pending_text_overlay_req", None)
        if pending and pending_req == getattr(self, "_last_frame_req", None):
            img = self._composite_text_on_image(img, pending)
        self._last_preview_qimg = img

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
        if hasattr(self, "_maybe_refresh_effects_browser"):
            self._maybe_refresh_effects_browser()

    def _on_frame_error(self, msg: str):
        if isinstance(self.video_widget, QtWidgets.QLabel):
            self.video_widget.setText(f"Frame could not be loaded:\n{msg}")

    def _composite_text_on_image(self, base: QtGui.QImage, clip: ClipItem) -> QtGui.QImage:
        from text_render import render_text_qimage
        target_w = max(1, base.width())
        target_h = max(1, base.height())
        font_size = self._text_preview_font_size(clip, target_w, target_h)
        text_img = render_text_qimage(
            clip.text,
            target_w,
            target_h,
            bg_color=clip.bg_color,
            text_color=clip.text_color,
            font_path=getattr(clip, "text_font", ""),
            text_align=getattr(clip, "text_align", "center"),
            text_v_align=getattr(clip, "text_v_align", "center"),
            stroke_color=getattr(clip, "text_stroke_color", "#000000"),
            stroke_width=getattr(clip, "text_stroke_width", 0),
            method=getattr(clip, "text_method", "caption"),
            font_size=font_size,
        )
        out = QtGui.QImage(base)
        painter = QtGui.QPainter(out)
        painter.drawImage(0, 0, text_img)
        painter.end()
        return out

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
                new_c = replace(
                    c,
                    trim_in=local,
                    trim_out=old_out,
                    start_time=t,
                    effects=list(c.effects or []),
                )
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
