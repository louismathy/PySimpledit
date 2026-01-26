import os

from PySide6 import QtWidgets

from moviepy import (
    VideoFileClip, AudioFileClip, ColorClip,
    concatenate_videoclips, CompositeAudioClip
)

from effects import EffectConfig, build_chain
from render_settings import RenderSettingsDialog
from utils import make_subclip, make_audio_subclip, set_start_compat, set_audio_compat


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
            final = self._render_moviepy_sequence()

            settings = self.render_settings
            codec = "libx264" if "264" in settings["codec"] else \
                    "libx265" if "265" in settings["codec"] else \
                    "prores" if "prores" in settings["codec"] else "vp9"

            final.write_videofile(
                out,
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
            except:
                pass

            QtWidgets.QMessageBox.information(self, "Done", f"Export written: {os.path.abspath(out)}")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Export error", str(e))

    def _render_moviepy_sequence(self):
        clips = [c for c in self.clips if c.trimmed_length() > 1e-6]
        if not clips:
            total = self.timeline_length()
            video = ColorClip(size=(1280, 720), color=(0, 0, 0), duration=max(0.1, total))
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
                    v_segments.append(ColorClip(size=(1280, 720), color=(0, 0, 0), duration=t1 - t0))
                    continue
                base = VideoFileClip(c.path)
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

        settings = self.render_settings
        if settings["resolution"] != "Auto":
            target_w, target_h = self._target_resolution(settings["resolution"])
            video = video.resized(new_size=(target_w, target_h))

        return video
