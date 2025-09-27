from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from moviepy.video.VideoClip import VideoClip
    from PySide6.QtGui import QImage

@dataclass
class EffectConfig:
    """Serializable effect configuration used by editor + export."""
    type: str
    params: Dict[str, Any] = field(default_factory=dict)

class BaseEffect:
    """Base class for all effects."""
    key: str = "base"  # unique registry key

    def __init__(self, **params: Any):
        self.params = params or {}

    # --- MoviePy side (export) ---
    def apply_moviepy(self, clip: "VideoClip") -> "VideoClip":
        """Return a new clip with this effect applied. Override in subclasses."""
        return clip

    # --- Preview side (QImage) ---
    def apply_qimage(self, img: "QImage") -> "QImage":
        """Return a new QImage with this effect applied. Override in subclasses."""
        return img

    # --- (De-)Serialization helpers ---
    @classmethod
    def from_config(cls, cfg: EffectConfig) -> "BaseEffect":
        return cls(**(cfg.params or {}))

    def to_config(self) -> EffectConfig:
        return EffectConfig(type=self.key, params=dict(self.params))
