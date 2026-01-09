from __future__ import annotations
from typing import TYPE_CHECKING
import numpy as np
from .base import BaseEffect
from .registry import register_effect
from ._qimage_numpy import to_rgba_np, from_rgba_np

if TYPE_CHECKING:
    from moviepy.video.VideoClip import VideoClip
    from PySide6.QtGui import QImage


@register_effect
class ContrastEffect(BaseEffect):
    key = "contrast"

    def apply_moviepy(self, clip: "VideoClip") -> "VideoClip":
        factor = float(self.params.get("factor", 1.2))

        def _contrast(img):
                                    
            arr = img.astype(np.float32, copy=True)
            arr[..., :3] = np.clip((arr[..., :3] - 128.0) * factor + 128.0, 0, 255)
            return arr.astype(np.uint8)

        return clip.image_transform(_contrast)

    def apply_qimage(self, img: "QImage") -> "QImage":
        factor = float(self.params.get("factor", 1.2))
        arr, _ = to_rgba_np(img)               
        rgb = arr[..., 0:3].astype(np.float32)
        rgb = np.clip((rgb - 128.0) * factor + 128.0, 0, 255).astype(np.uint8)
        arr[..., 0:3] = rgb
        return from_rgba_np(arr)
