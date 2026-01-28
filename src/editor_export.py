import os
import math

from PySide6 import QtWidgets, QtCore

from moviepy import (
    VideoFileClip, AudioFileClip, ColorClip, ImageClip, CompositeVideoClip,
    concatenate_videoclips, CompositeAudioClip, TextClip
)

from effects import EffectConfig, build_chain
from render_settings import RenderSettingsDialog
from text_render import render_text_qimage, qimage_to_rgba_array
from utils import make_subclip, make_audio_subclip, set_start_compat, set_audio_compat, set_duration_compat


class EditorExportMixin:
    def on_open_render_settings(self):
        dlg = RenderSettingsDialog(self)
        if hasattr(self, "_apply_dialog_theme"):
            self._apply_dialog_theme(dlg)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self.render_settings = dlg.get_settings()

    def _target_resolution(self, setting: str, default=(1280, 720)):
        mapping = {
            "720p": (1280, 720),
            "1080p": (1920, 1080),
            "1440p": (2560, 1440),
            "4K": (3840, 2160),
        }
        return mapping.get(setting, default)

    def on_export(self):
        if not self.clips and not self.audios:
            QtWidgets.QMessageBox.information(self, "Nothing to export", "Please add clips/audio first.")
            return

        out = self.out_path.text().strip() or "simpledit-export.mp4"
        try:
            print(f"[render] settings={self.render_settings}")
        except Exception:
            pass

        if getattr(self, "_export_thread", None) is not None:
            try:
                if self._export_thread.isRunning():
                    QtWidgets.QMessageBox.warning(self, "Export", "Export is already running.")
                    return
            except RuntimeError:
                self._export_thread = None

        est_bytes = self._estimate_export_bytes()
        est_units = self._bytes_to_units(est_bytes)
        est_mb = est_bytes / (1024 * 1024)
        progress = QtWidgets.QProgressDialog(
            f"Rendering... (0.0MB/{est_mb:.1f}MB)",
            "",
            0,
            est_units,
            self,
        )
        progress.setWindowTitle("Export")
        progress.setCancelButton(None)
        progress.setWindowModality(QtCore.Qt.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        progress.show()

        self._export_progress = progress
        self._export_progress_value = 0
        self._export_out_path = out
        self._export_est_bytes = est_bytes
        self._export_bytes_per_unit = self._bytes_per_unit()
        self._export_size_timer = QtCore.QTimer(self)
        self._export_size_timer.setInterval(300)

        def _tick_size():
            prog = getattr(self, "_export_progress", None)
            if not prog:
                return
            size = 0
            try:
                if os.path.exists(out):
                    size = os.path.getsize(out)
            except Exception:
                size = 0
            units = min(est_units, int(size / self._export_bytes_per_unit))
            if units > self._export_progress_value:
                self._export_progress_value = units
                prog.setValue(units)
            prog.setLabelText(
                f"Rendering... ({size / (1024 * 1024):.1f}MB/{est_mb:.1f}MB)"
            )

        self._export_size_timer.timeout.connect(_tick_size)
        self._export_size_timer.start()

        class _ExportWorker(QtCore.QObject):
            finished = QtCore.Signal(str)
            failed = QtCore.Signal(str)

            def __init__(self, parent, out_path: str):
                super().__init__()
                self._parent = parent
                self._out_path = out_path

            @QtCore.Slot()
            def run(self):
                try:
                    final = self._parent._render_moviepy_sequence()

                    settings = self._parent.render_settings
                    codec = "libx264" if "264" in settings["codec"] else \
                            "libx265" if "265" in settings["codec"] else \
                            "prores" if "prores" in settings["codec"] else "vp9"

                    final.write_videofile(
                        self._out_path,
                        codec=codec,
                        audio_codec="aac",
                        audio_bitrate=settings["audio_bitrate"],
                        preset=settings["preset"],
                        fps=None if settings["fps"] == "Auto" else int(settings["fps"]),
                        threads=0,
                        temp_audiofile="~temp-audio.m4a",
                        remove_temp=True,
                        logger=None,
                    )

                    try:
                        final.close()
                    except Exception:
                        pass

                    cache = getattr(self._parent, "_export_clip_cache", None) or {}
                    for _p, _clip in cache.items():
                        try:
                            _clip.close()
                        except Exception:
                            pass
                    self._parent._export_clip_cache = None

                    self.finished.emit(self._out_path)
                except Exception as exc:
                    cache = getattr(self._parent, "_export_clip_cache", None) or {}
                    for _p, _clip in cache.items():
                        try:
                            _clip.close()
                        except Exception:
                            pass
                    self._parent._export_clip_cache = None
                    self.failed.emit(str(exc))

        self._export_thread = QtCore.QThread(self)
        self._export_worker = _ExportWorker(self, out)
        self._export_worker.moveToThread(self._export_thread)
        self._export_thread.started.connect(self._export_worker.run)
        self._export_worker.finished.connect(self._on_export_finished)
        self._export_worker.failed.connect(self._on_export_failed)
        self._export_worker.finished.connect(self._export_thread.quit)
        self._export_worker.failed.connect(self._export_thread.quit)
        self._export_thread.finished.connect(self._export_worker.deleteLater)
        self._export_thread.finished.connect(self._export_thread.deleteLater)
        self._export_thread.start()

    def _on_export_finished(self, out_path: str):
        progress = getattr(self, "_export_progress", None)
        if progress:
            progress.setValue(progress.maximum())
            progress.close()
        self._export_progress = None
        self._export_progress_value = 0
        self._export_thread = None
        self._export_worker = None
        timer = getattr(self, "_export_size_timer", None)
        if timer:
            timer.stop()
        self._export_size_timer = None
        self._export_out_path = None
        self._export_est_bytes = None
        self._export_bytes_per_unit = None
        QtWidgets.QMessageBox.information(self, "Done", f"Export written: {os.path.abspath(out_path)}")

    def _on_export_failed(self, msg: str):
        progress = getattr(self, "_export_progress", None)
        if progress:
            progress.close()
        self._export_progress = None
        self._export_progress_value = 0
        self._export_thread = None
        self._export_worker = None
        timer = getattr(self, "_export_size_timer", None)
        if timer:
            timer.stop()
        self._export_size_timer = None
        self._export_out_path = None
        self._export_est_bytes = None
        self._export_bytes_per_unit = None
        QtWidgets.QMessageBox.critical(self, "Export error", msg)

    def _bytes_per_unit(self) -> int:
        return int((1024 * 1024) / 10)

    def _bytes_to_units(self, total_bytes: int) -> int:
        return max(1, int(math.ceil(total_bytes / self._bytes_per_unit())))

    def _estimate_export_bytes(self) -> int:
        duration = max(0.1, float(self.timeline_length()))
        settings = self.render_settings
        res = settings.get("resolution", "Auto")
        if res == "Auto":
            target_w, target_h = 1280, 720
        else:
            target_w, target_h = self._target_resolution(res)

        base_mbps = 12.0
        if target_h >= 2160:
            base_mbps = 80.0
        elif target_h >= 1440:
            base_mbps = 35.0
        elif target_h >= 1080:
            base_mbps = 14.0
        elif target_h >= 720:
            base_mbps = 8.0
        else:
            base_mbps = 4.5

        codec = settings.get("codec", "")
        if "265" in codec or "hevc" in codec.lower():
            base_mbps *= 0.75
        elif "vp9" in codec.lower():
            base_mbps *= 0.8
        elif "prores" in codec.lower():
            base_mbps *= 6.0

        audio_bitrate = settings.get("audio_bitrate", "192k")
        audio_kbps = 192.0
        try:
            audio_kbps = float(str(audio_bitrate).lower().replace("k", ""))
        except Exception:
            audio_kbps = 192.0

        total_mbps = max(1.0, base_mbps + (audio_kbps / 1000.0))
        total_mbps *= 1.5
        if duration < 10.0:
            total_mbps *= 1.35
        elif duration < 30.0:
            total_mbps *= 1.2
        est_bytes = int(duration * (total_mbps * 1_000_000 / 8.0))
        return max(1_000_000, est_bytes)

    def _render_moviepy_sequence(self):
        clips = [c for c in self.clips if c.trimmed_length() > 1e-6]
        settings = self.render_settings
        base_size = (1280, 720)
        if settings["resolution"] != "Auto":
            base_size = self._target_resolution(settings["resolution"])
        clip_cache: dict[str, VideoFileClip] = {}
        text_cache: dict[tuple, "np.ndarray"] = {}
        text_mode = settings.get("text_render", "TextClip (Pillow)")
        if not clips:
            total = self.timeline_length()
            video = ColorClip(size=base_size, color=(0, 0, 0), duration=max(0.1, total))
        else:
            boundaries = {0.0}
            for c in clips:
                boundaries.add(c.start_time)
                boundaries.add(c.start_time + c.trimmed_length())

            times = sorted(boundaries)
            v_segments = []
            for t0, t1 in zip(times, times[1:]):
                if t1 - t0 <= 1e-6:
                    continue
                t_mid = (t0 + t1) * 0.5
                c = self._clip_at_time(t_mid)
                if not c:
                    v_segments.append(ColorClip(size=base_size, color=(0, 0, 0), duration=t1 - t0))
                    continue
                if c.is_text():
                    base = self._clip_below_video_at_time(t_mid, c.layer)
                    if base:
                        base_clip = clip_cache.get(base.path)
                        if base_clip is None:
                            base_clip = VideoFileClip(base.path)
                            clip_cache[base.path] = base_clip
                        base_local_start = base.trim_in + (t0 - base.start_time)
                        base_local_end = base_local_start + (t1 - t0)
                        base_sub = make_subclip(base_clip, base_local_start, base_local_end)
                    else:
                        base_sub = ColorClip(size=base_size, color=(0, 0, 0), duration=t1 - t0)

                    overlay_w = base_sub.w if hasattr(base_sub, "w") else base_size[0]
                    overlay_h = base_sub.h if hasattr(base_sub, "h") else base_size[1]
                    if text_mode == "Pre-render PNG (Qt)":
                        cache_key = (
                            overlay_w,
                            overlay_h,
                            c.text,
                            c.text_size,
                            c.text_color,
                            c.bg_color,
                            getattr(c, "text_font", ""),
                            getattr(c, "text_method", "caption"),
                            getattr(c, "text_align", "center"),
                            getattr(c, "text_v_align", "center"),
                            getattr(c, "text_stroke_color", "#000000"),
                            getattr(c, "text_stroke_width", 0),
                        )
                        arr = text_cache.get(cache_key)
                        if arr is None:
                            if text_mode == "Pre-render PNG (Qt)":
                                pad = max(4, int(c.text_size * 0.2))
                                target_w = min(overlay_w, max(1, overlay_w))
                                target_h = min(overlay_h, max(1, overlay_h))
                                if str(getattr(c, "text_method", "caption")).lower() == "label":
                                    try:
                                        from PySide6 import QtGui
                                        from text_render import _font_family_for_path
                                        family = _font_family_for_path(getattr(c, "text_font", ""), "SF Pro Display")
                                        font = QtGui.QFont(family, max(10, int(c.text_size)))
                                        metrics = QtGui.QFontMetrics(font)
                                        bounds = metrics.boundingRect(c.text or "")
                                        target_w = min(overlay_w, max(1, bounds.width() + pad * 2))
                                        target_h = min(overlay_h, max(1, bounds.height() + pad * 2))
                                    except Exception:
                                        pass
                            img = render_text_qimage(
                                c.text,
                                target_w,
                                target_h,
                                bg_color=c.bg_color,
                                text_color=c.text_color,
                                font_path=getattr(c, "text_font", ""),
                                text_align=getattr(c, "text_align", "center"),
                                text_v_align=getattr(c, "text_v_align", "center"),
                                stroke_color=getattr(c, "text_stroke_color", "#000000"),
                                stroke_width=getattr(c, "text_stroke_width", 0),
                                method=getattr(c, "text_method", "caption"),
                                font_size=c.text_size,
                            )
                            arr = qimage_to_rgba_array(img)
                            text_cache[cache_key] = arr
                        text_sub = ImageClip(arr)
                    else:
                        bg = None if str(c.bg_color).lower() in {"transparent", "none", ""} else c.bg_color
                        font_path = getattr(c, "text_font", "") or None
                        if text_mode == "TextClip (tight box)":
                            cache_key = (
                                "tight",
                                c.text,
                                c.text_size,
                                c.text_color,
                                c.bg_color,
                                getattr(c, "text_font", ""),
                                getattr(c, "text_method", "caption"),
                                getattr(c, "text_align", "center"),
                                getattr(c, "text_v_align", "center"),
                                getattr(c, "text_stroke_color", "#000000"),
                                getattr(c, "text_stroke_width", 0),
                            )
                            size_entry = text_cache.get(cache_key)
                            if size_entry is None:
                                try:
                                    measure = TextClip(
                                        text=c.text or "",
                                        font_size=int(c.text_size * 2),
                                        color=str(c.text_color or "#FFFFFF"),
                                        method="label",
                                        text_align=str(getattr(c, "text_align", "center")),
                                        horizontal_align=str(getattr(c, "text_align", "center")),
                                        vertical_align=str(getattr(c, "text_v_align", "center")),
                                        font=font_path,
                                        bg_color=bg,
                                        stroke_color=str(getattr(c, "text_stroke_color", "#000000")),
                                        stroke_width=int(getattr(c, "text_stroke_width", 0)),
                                    )
                                    size_entry = (int(measure.w), int(measure.h))
                                finally:
                                    try:
                                        measure.close()
                                    except Exception:
                                        pass
                                text_cache[cache_key] = size_entry
                            w, h = size_entry
                            pad = max(4, int(c.text_size * 0.2))
                            w = int(min(overlay_w, w + pad * 2))
                            h = int(min(overlay_h, h + pad * 2))
                            text_kwargs = dict(
                                text=c.text or "",
                                font_size=int(c.text_size * 2),
                                color=str(c.text_color or "#FFFFFF"),
                                method="label",
                                text_align=str(getattr(c, "text_align", "center")),
                                horizontal_align=str(getattr(c, "text_align", "center")),
                                vertical_align=str(getattr(c, "text_v_align", "center")),
                                font=font_path,
                                bg_color=bg,
                                stroke_color=str(getattr(c, "text_stroke_color", "#000000")),
                                stroke_width=int(getattr(c, "text_stroke_width", 0)),
                                size=(w, h),
                            )
                            text_sub = TextClip(**text_kwargs)
                            hpos = str(getattr(c, "text_align", "center"))
                            vpos = str(getattr(c, "text_v_align", "center"))
                            if hpos == "left":
                                x = 0
                            elif hpos == "right":
                                x = int(overlay_w - w)
                            else:
                                x = int((overlay_w - w) * 0.5)
                            if vpos == "top":
                                y = 0
                            elif vpos == "bottom":
                                y = int(overlay_h - h)
                            else:
                                y = int((overlay_h - h) * 0.5)
                                y -= max(1, int(c.text_size * 0.4))
                            text_sub = text_sub.with_position((x, y))
                        else:
                            text_kwargs = dict(
                                text=c.text or "",
                                font_size=int(c.text_size * 2),
                                color=str(c.text_color or "#FFFFFF"),
                            method=str(getattr(c, "text_method", "caption")),
                            text_align=str(getattr(c, "text_align", "center")),
                            horizontal_align=str(getattr(c, "text_align", "center")),
                            vertical_align=str(getattr(c, "text_v_align", "center")),
                            font=font_path,
                            bg_color=bg,
                                stroke_color=str(getattr(c, "text_stroke_color", "#000000")),
                                stroke_width=int(getattr(c, "text_stroke_width", 0)),
                            )
                            text_kwargs["size"] = (int(overlay_w), int(overlay_h))
                            text_sub = TextClip(**text_kwargs)
                    text_sub = set_duration_compat(text_sub, t1 - t0)
                    sub = CompositeVideoClip([base_sub, text_sub], size=(overlay_w, overlay_h))
                    sub = set_duration_compat(sub, t1 - t0)
                else:
                    base = clip_cache.get(c.path)
                    if base is None:
                        base = VideoFileClip(c.path)
                        clip_cache[c.path] = base
                    local_start = c.trim_in + (t0 - c.start_time)
                    local_end = local_start + (t1 - t0)
                    sub = make_subclip(base, local_start, local_end)
                try:
                    effect_cfgs = [EffectConfig(**ec) for ec in (getattr(c, "effects", []) or [])]
                    for eff in build_chain(effect_cfgs):
                        sub = eff.apply_moviepy(sub)
                except Exception as _e:
                    print(_e)
                    pass
                v_segments.append(sub)

            video = v_segments[0] if len(v_segments) == 1 else concatenate_videoclips(v_segments, method="compose")

        extra_audio_clips = []
        for a in self._sorted_audio_by_start:
            ac = make_audio_subclip(AudioFileClip(a.path), a.trim_in, a.safe_out())
            if abs(a.gain_db) > 1e-6:
                ac = ac.volumex(10 ** (a.gain_db / 20.0))
            ac = set_start_compat(ac, a.start_time)
            extra_audio_clips.append(ac)

        if extra_audio_clips:
            tracks = []
            if video.audio is not None:
                tracks.append(video.audio)
            tracks.extend(extra_audio_clips)
            comp = CompositeAudioClip(tracks)
            video = set_audio_compat(video, comp)

        if settings["resolution"] != "Auto":
            target_w, target_h = self._target_resolution(settings["resolution"])
            video = video.resized(new_size=(target_w, target_h))

        self._export_clip_cache = clip_cache
        return video
