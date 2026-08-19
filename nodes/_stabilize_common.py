"""Utilidades compartidas entre los algoritmos de estabilización de ODDNodes
(Warp automático y Point Lock). Solo numpy + OpenCV, sin torch."""

import math
import numpy as np

try:
    import cv2
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "ODDNodes necesita opencv-python para estabilizar video. Instalalo con:\n"
        "    pip install opencv-python\n"
        "(o python_embeded\\python.exe -m pip install opencv-python en la build portable)"
    ) from exc


def to_gray_u8(frame_float_rgb):
    """frame HxWx3 float 0..1 RGB  ->  HxW uint8 gris."""
    arr = np.clip(frame_float_rgb * 255.0, 0.0, 255.0).astype(np.uint8)
    if arr.ndim == 2:
        return arr
    if arr.shape[2] == 1:
        return arr[:, :, 0]
    if arr.shape[2] == 4:
        arr = arr[:, :, :3]
    return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)


def _valid_rect_for(matrix, width, height):
    """Rectángulo con datos reales tras aplicar `matrix`, como (l, t, r, b)."""
    corners = np.array(
        [[0, 0, 1], [width, 0, 1], [width, height, 1], [0, height, 1]],
        dtype=np.float32,
    ).T
    dst = matrix @ corners  # 2x4 -> tl, tr, br, bl
    tl, tr, br, bl = dst[:, 0], dst[:, 1], dst[:, 2], dst[:, 3]
    return (
        max(tl[0], bl[0]),   # left
        max(tl[1], tr[1]),   # top
        min(tr[0], br[0]),   # right
        min(bl[1], br[1]),   # bottom
    )


def common_crop(matrices, width, height):
    """Recorte válido para TODOS los frames. Devuelve (x0, y0, x1, y1) enteros."""
    left, top = 0.0, 0.0
    right, bottom = float(width), float(height)
    for m in matrices:
        l, t, r, b = _valid_rect_for(m, width, height)
        left = max(left, l)
        top = max(top, t)
        right = min(right, r)
        bottom = min(bottom, b)

    x0 = int(math.ceil(max(0.0, left)))
    y0 = int(math.ceil(max(0.0, top)))
    x1 = int(math.floor(min(float(width), right)))
    y1 = int(math.floor(min(float(height), bottom)))

    if x1 - x0 < 8 or y1 - y0 < 8:
        return 0, 0, width, height
    return x0, y0, x1, y1


def apply_crop_and_resize(warped, matrices, width, height, auto_crop, resize_to_original):
    """Aplica el recorte común a todos los frames (si `auto_crop`) y opcionalmente
    reescala de vuelta al tamaño original. Devuelve (frames, crop_box)."""
    crop_box = (0, 0, width, height)
    if not auto_crop:
        return warped, crop_box

    x0, y0, x1, y1 = common_crop(matrices, width, height)
    crop_box = (x0, y0, x1, y1)
    if (x1 - x0, y1 - y0) == (width, height):
        return warped, crop_box

    cropped = warped[:, y0:y1, x0:x1, :]
    if not resize_to_original:
        return cropped, crop_box

    n_frames = warped.shape[0]
    resized = np.empty((n_frames, height, width, warped.shape[3]), dtype=np.float32)
    for t in range(n_frames):
        resized[t] = cv2.resize(cropped[t], (width, height), interpolation=cv2.INTER_LANCZOS4)
    return resized, crop_box
