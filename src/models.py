from __future__ import annotations
from dataclasses import dataclass, field
import os
from typing import Optional, List

                                                     
try:
    from effects import EffectConfig
except Exception:
                                                         
    @dataclass
    class EffectConfig:                
        type: str
        params: dict = field(default_factory=dict)


@dataclass
class ClipItem:
    path: str
    duration: float
    trim_in: float = 0.0
    trim_out: Optional[float] = None
    start_time: float = 0.0
    layer: int = 0
    effects: List[EffectConfig] = field(default_factory=list)
    clip_type: str = "video"
    text: str = ""
    text_size: int = 64
    text_color: str = "#FFFFFF"
    bg_color: str = "transparent"

    def is_text(self) -> bool:
        return self.clip_type == "text" or not self.path

    def display_name(self) -> str:
        if self.is_text():
            snippet = (self.text or "").strip().replace("\n", " ")
            if not snippet:
                snippet = "Empty"
            if len(snippet) > 24:
                snippet = snippet[:24].rstrip() + "..."
            return f"Text: {snippet}"
        return os.path.basename(self.path) if self.path else "Untitled"

    def safe_out(self) -> float:
                                                             
        return min(self.duration, self.trim_out if self.trim_out is not None else self.duration)

    def trimmed_length(self) -> float:
                                                                
        return max(0.0, self.safe_out() - self.trim_in)


@dataclass
class AudioItem:
    path: str
    duration: float
    trim_in: float = 0.0
    trim_out: Optional[float] = None
    start_time: float = 0.0
    gain_db: float = 0.0

    def safe_out(self) -> float:
        return min(self.duration, self.trim_out if self.trim_out is not None else self.duration)

    def trimmed_length(self) -> float:
        return max(0.0, self.safe_out() - self.trim_in)
