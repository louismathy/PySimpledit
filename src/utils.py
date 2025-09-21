import math
from typing import Any
from moviepy import VideoFileClip, AudioFileClip

# ---------------------- Zeitformat ----------------------

def fmt_time(t: float) -> str:
    """
    Formatiert Sekunden als mm:ss.ss (clamped auf >= 0).
    Beispiel: 73.42 -> '01:13.42'
    """
    if t < 0:
        t = 0.0
    m = int(t // 60)
    s = t - 60 * m
    return f"{m:02d}:{s:05.2f}"


# ---------------------- MoviePy Kompat-Helper ----------------------
# MoviePy 2.x hat neue Methodennamen (subclipped, with_start, with_audio).
# Diese Wrapper machen den Code kompatibel zu 1.x und 2.x.

def make_subclip(clip: VideoFileClip, start: float, end: float) -> VideoFileClip:
    """
    Schneidet einen VideoClip zwischen start und end heraus.
    Nutzt subclipped() wenn vorhanden, sonst subclip().
    """
    return clip.subclipped(start, end) if hasattr(clip, "subclipped") else clip.subclip(start, end)


def make_audio_subclip(clip: AudioFileClip, start: float, end: float) -> AudioFileClip:
    """
    Schneidet einen AudioClip zwischen start und end heraus.
    Nutzt subclipped() wenn vorhanden, sonst subclip().
    """
    return clip.subclipped(start, end) if hasattr(clip, "subclipped") else clip.subclip(start, end)


def set_start_compat(clip: Any, t: float):
    """
    Setzt Startzeit eines (Audio/Video-)Clips auf der Timeline.
    Nutzt with_start() wenn vorhanden, sonst set_start().
    """
    return clip.with_start(t) if hasattr(clip, "with_start") else clip.set_start(t)


def set_audio_compat(video: Any, audio: Any):
    """
    Hängt eine Audio-Spur an einen VideoClip.
    Nutzt with_audio() wenn vorhanden, sonst set_audio().
    """
    return video.with_audio(audio) if hasattr(video, "with_audio") else video.set_audio(audio)


# ---------------------- Sonstige kleine Helfer (optional) ----------------------

def db_to_linear(db: float) -> float:
    """Wandelt dB in linearen Gain-Faktor um."""
    return 10 ** (db / 20.0)


def clamp(val: float, lo: float, hi: float) -> float:
    """Clamped einen Wert val in [lo, hi]."""
    return max(lo, min(hi, val))
