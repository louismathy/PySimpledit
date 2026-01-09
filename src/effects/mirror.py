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
class MirrorEffect(BaseEffect):
    key = "mirror"

    def apply_moviepy(self, clip: "VideoClip") -> "VideoClip":
        import numpy as np

        def _mirror(img):
                             
            return np.ascontiguousarray(img[:, ::-1, :])

        return clip.image_transform(_mirror)

    def apply_qimage(self, img: "QImage") -> "QImage":
        arr, _ = to_rgba_np(img)
        arr = np.ascontiguousarray(arr[:, ::-1, :])                   
        return from_rgba_np(arr)
