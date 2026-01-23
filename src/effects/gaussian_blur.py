from __future__ import annotations
from typing import TYPE_CHECKING
import numpy as np
from .base import BaseEffect
from .registry import register_effect
from ._qimage_numpy import to_rgba_np, from_rgba_np

if TYPE_CHECKING:
    from moviepy.video.VideoClip import VideoClip
    from PySide6.QtGui import QImage


def _gaussian_kernel1d(sigma: float) -> np.ndarray:
    if sigma <= 0:
        return np.array([1.0], dtype=np.float32)
    radius = int(max(1, round(3.0 * sigma)))
    x = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-(x * x) / (2.0 * sigma * sigma))
    kernel /= float(kernel.sum())
    return kernel.astype(np.float32)


def _convolve1d(arr: np.ndarray, kernel: np.ndarray, axis: int) -> np.ndarray:
    pad = kernel.size // 2
    if pad == 0:
        return arr
    pad_spec = [(0, 0)] * arr.ndim
    pad_spec[axis] = (pad, pad)
    padded = np.pad(arr, pad_spec, mode="reflect")
    convolved = np.apply_along_axis(lambda m: np.convolve(m, kernel, mode="valid"), axis, padded)
    return convolved.astype(np.float32, copy=False)


def _gaussian_blur_rgb(arr: np.ndarray, sigma: float) -> np.ndarray:
    kernel = _gaussian_kernel1d(sigma)
    if kernel.size == 1:
        return arr
    out = _convolve1d(arr, kernel, axis=1)
    out = _convolve1d(out, kernel, axis=0)
    return out


@register_effect
class GaussianBlurEffect(BaseEffect):
    key = "gaussian_blur"

    def apply_moviepy(self, clip: "VideoClip") -> "VideoClip":
        sigma = float(self.params.get("sigma", 2.0))

        def _blur(img):
            arr = img.astype(np.float32, copy=True)
            arr[..., :3] = _gaussian_blur_rgb(arr[..., :3], sigma)
            return np.clip(arr, 0, 255).astype(np.uint8)

        return clip.image_transform(_blur)

    def apply_qimage(self, img: "QImage") -> "QImage":
        sigma = float(self.params.get("sigma", 2.0))
        arr, _ = to_rgba_np(img)
        rgb = arr[..., 0:3].astype(np.float32)
        rgb = _gaussian_blur_rgb(rgb, sigma)
        arr[..., 0:3] = np.clip(rgb, 0, 255).astype(np.uint8)
        return from_rgba_np(arr)
