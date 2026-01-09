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
class InvertEffect(BaseEffect):
    key = "invert"

    def apply_moviepy(self, clip: "VideoClip") -> "VideoClip":
        import numpy as np

        def _invert(img):
            arr = img.astype(np.uint8, copy=True)
            arr[..., :3] = 255 - arr[..., :3]
            return arr

        return clip.image_transform(_invert)

    def apply_qimage(self, img: "QImage") -> "QImage":
        arr, _ = to_rgba_np(img)        
        arr[..., 0:3] = 255 - arr[..., 0:3]                     
        return from_rgba_np(arr)
