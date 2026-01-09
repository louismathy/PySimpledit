from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from moviepy.video.VideoClip import VideoClip
    from PySide6.QtGui import QImage

@dataclass
class EffectConfig:
                                                                    
    type: str
    params: Dict[str, Any] = field(default_factory=dict)

class BaseEffect:
                                     
    key: str = "base"                       

    def __init__(self, **params: Any):
        self.params = params or {}

                                   
    def apply_moviepy(self, clip: "VideoClip") -> "VideoClip":
                                                                                 
        return clip

                                   
    def apply_qimage(self, img: "QImage") -> "QImage":
                                                                                   
        return img

                                        
    @classmethod
    def from_config(cls, cfg: EffectConfig) -> "BaseEffect":
        return cls(**(cfg.params or {}))

    def to_config(self) -> EffectConfig:
        return EffectConfig(type=self.key, params=dict(self.params))
