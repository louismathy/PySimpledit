from __future__ import annotations
import numpy as np
from PySide6.QtGui import QImage

def to_rgba_np(img: QImage) -> tuple[np.ndarray, QImage]:
    """Convert QImage → contiguous RGBA NumPy array + converted QImage."""
    if img.format() != QImage.Format_ARGB32:
        img = img.convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()

    ptr = img.bits()
    arr = np.frombuffer(ptr, np.uint8).reshape((h, img.bytesPerLine() // 4, 4))
    # Sicherstellen, dass Array contiguous ist
    arr = arr[:, :w, :].copy()  
    return arr, img

def from_rgba_np(rgba: np.ndarray) -> QImage:
    """Convert contiguous RGBA NumPy array → QImage (ARGB32)."""
    h, w, ch = rgba.shape
    assert ch == 4
    arr = np.ascontiguousarray(rgba, dtype=np.uint8)
    qimg = QImage(arr.data, w, h, w * 4, QImage.Format_ARGB32)
    # Wichtig: Copy erzwingen, sonst verweist QImage nur auf NumPy-Buffer
    return qimg.copy()
