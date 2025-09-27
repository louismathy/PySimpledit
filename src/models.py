from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List

# Optional: wenn du Effekte pro Clip speichern willst
try:
    from effects import EffectConfig
except Exception:
    # Fallback, falls effects noch nicht importierbar ist
    @dataclass
    class EffectConfig:  # type: ignore
        type: str
        params: dict = field(default_factory=dict)


@dataclass
class ClipItem:
    path: str
    duration: float
    trim_in: float = 0.0
    trim_out: Optional[float] = None
    start_time: float = 0.0
    effects: List[EffectConfig] = field(default_factory=list)

    def safe_out(self) -> float:
        """Return the current trim-out capped by duration."""
        return min(self.duration, self.trim_out if self.trim_out is not None else self.duration)

    def trimmed_length(self) -> float:
        """Return visible length (out - in), clamped to >= 0."""
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
