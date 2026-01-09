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
class SepiaEffect(BaseEffect):
    key = "sepia"

    def apply_moviepy(self, clip: "VideoClip") -> "VideoClip":
        import numpy as np

        def _sepia(img):
            arr = img.astype(np.float32, copy=True)                             
            r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]

            tr = 0.393*r + 0.769*g + 0.189*b
            tg = 0.349*r + 0.686*g + 0.168*b
            tb = 0.272*r + 0.534*g + 0.131*b

            out = np.empty_like(arr, dtype=np.uint8)
            out[..., 0] = np.clip(tr, 0, 255).astype(np.uint8)
            out[..., 1] = np.clip(tg, 0, 255).astype(np.uint8)
            out[..., 2] = np.clip(tb, 0, 255).astype(np.uint8)

            if arr.shape[-1] == 4:                            
                out[..., 3] = arr[..., 3]

            return out


        return clip.image_transform(_sepia)


    def apply_qimage(self, img: "QImage") -> "QImage":
        from ._qimage_numpy import to_rgba_np, from_rgba_np
        arr, _ = to_rgba_np(img)
        r, g, b = arr[..., 2], arr[..., 1], arr[..., 0]
        tr = 0.393*r + 0.769*g + 0.189*b
        tg = 0.349*r + 0.686*g + 0.168*b
        tb = 0.272*r + 0.534*g + 0.131*b
        arr[..., 2] = np.clip(tr, 0, 255)
        arr[..., 1] = np.clip(tg, 0, 255)
        arr[..., 0] = np.clip(tb, 0, 255)
        return from_rgba_np(arr)
