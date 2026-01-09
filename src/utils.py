import math
from typing import Any
from moviepy import VideoFileClip, AudioFileClip

                                                          

def fmt_time(t: float) -> str:

       
    if t < 0:
        t = 0.0
    m = int(t // 60)
    s = t - 60 * m
    return f"{m:02d}:{s:05.2f}"


                                                                     
                                                                          
                                                          

def make_subclip(clip: VideoFileClip, start: float, end: float) -> VideoFileClip:

       
    return clip.subclipped(start, end) if hasattr(clip, "subclipped") else clip.subclip(start, end)


def make_audio_subclip(clip: AudioFileClip, start: float, end: float) -> AudioFileClip:

       
    return clip.subclipped(start, end) if hasattr(clip, "subclipped") else clip.subclip(start, end)


def set_start_compat(clip: Any, t: float):

       
    return clip.with_start(t) if hasattr(clip, "with_start") else clip.set_start(t)


def set_audio_compat(video: Any, audio: Any):

       
    return video.with_audio(audio) if hasattr(video, "with_audio") else video.set_audio(audio)


                                                                                 

def db_to_linear(db: float) -> float:
                                              
    return 10 ** (db / 20.0)


def clamp(val: float, lo: float, hi: float) -> float:
                                   
    return max(lo, min(hi, val))
