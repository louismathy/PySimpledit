from __future__ import annotations
import numpy as np
from PySide6.QtGui import QImage

def qimage_to_numpy(img: QImage) -> np.ndarray:

       
    if img.format() != QImage.Format_ARGB32:
        img = img.convertToFormat(QImage.Format_ARGB32)

    w, h = img.width(), img.height()
    ptr = img.bits()
    ptr.setsize(img.sizeInBytes())                        
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, img.bytesPerLine() // 4, 4))
    arr = arr[:, :w, :]                              
    return arr.copy()                                     


def numpy_to_qimage(arr: np.ndarray) -> QImage:
       
    h, w = arr.shape[:2]

    if arr.shape[2] == 3:
                                 
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[..., :3] = arr
        rgba[..., 3] = 255
        arr = rgba

                                
    bgra = arr[..., [2, 1, 0, 3]].copy()

    qimg = QImage(bgra.data, w, h, bgra.strides[0], QImage.Format_ARGB32)
    return qimg.copy()
