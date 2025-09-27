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
class BWEffect(BaseEffect):
    key = "bw"

    def apply_moviepy(self, clip: "VideoClip") -> "VideoClip":
        import numpy as np

        def _bw(img):
            arr = img.astype(np.float32, copy=True)
            r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
            gray = (0.299 * r + 0.587 * g + 0.114 * b)
            out_rgb = np.stack([gray, gray, gray], axis=-1)
            out = out_rgb.astype(np.uint8)
            if arr.shape[-1] == 4:
                out = np.concatenate([out, arr[..., 3:4].astype(np.uint8)], axis=-1)
            return out

        return clip.image_transform(_bw)

    def apply_qimage(self, img: "QImage") -> "QImage":
        arr, _ = to_rgba_np(img)  # BGRA
        # Grau aus BGR (achte: arr[...,2] = R)
        r = arr[..., 2].astype(np.float32)
        g = arr[..., 1].astype(np.float32)
        b = arr[..., 0].astype(np.float32)
        gray = np.clip(0.299 * r + 0.587 * g + 0.114 * b, 0, 255).astype(np.uint8)
        arr[..., 0] = gray  # B
        arr[..., 1] = gray  # G
        arr[..., 2] = gray  # R
        return from_rgba_np(arr)
