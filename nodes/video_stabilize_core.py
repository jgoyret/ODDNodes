"""
Núcleo de estabilización de video estilo Warp Stabilizer (Premiere/DaVinci):
tracking automático de features cuadro a cuadro + suavizado de la trayectoria
de cámara resultante. Solo numpy + OpenCV, sin torch, para poder testearlo
fuera de ComfyUI.

A diferencia de un "point lock" (fijar un punto elegido a mano a su posición
del frame 0), acá no se ancla nada: se estima cuánto se movió la cámara entre
cada par de frames consecutivos usando decenas de features autodetectadas, se
arma con eso la trayectoria acumulada de la cámara, se suaviza esa trayectoria
con una media móvil, y la diferencia entre trayectoria real y suavizada es la
corrección que se le aplica a cada frame. El resultado es temblor removido
pero paneos/dollys intencionales conservados (atenuados, no anulados).
"""

import math
import numpy as np
import cv2

from ._stabilize_common import to_gray_u8, apply_crop_and_resize

FEATURE_PARAMS = dict(maxCorners=250, qualityLevel=0.01, minDistance=24, blockSize=7)
LK_PARAMS = dict(
    winSize=(21, 21),
    maxLevel=3,
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
)
# Por debajo de esto no hay suficiente info para una estimación de transform confiable.
MIN_TRACKED_POINTS = 10


# --------------------------------------------------------------------------
# motion cuadro-a-cuadro
# --------------------------------------------------------------------------

def _detect_and_track(prev_gray, cur_gray):
    """Detecta features en prev_gray y las sigue en cur_gray con Lucas-Kanade.

    Se redetectan features en cada par de frames (en vez de mantener un set
    fijo a lo largo de todo el video) para no depender de que un puñado de
    puntos elegidos al principio sigan visibles 500 frames después.

    Devuelve (prev_pts, cur_pts) filtrados por status, o (None, None) si no
    hay suficientes para una estimación confiable.
    """
    prev_pts = cv2.goodFeaturesToTrack(prev_gray, mask=None, **FEATURE_PARAMS)
    if prev_pts is None or len(prev_pts) < MIN_TRACKED_POINTS:
        return None, None

    cur_pts, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, cur_gray, prev_pts, None, **LK_PARAMS)
    status = status.reshape(-1).astype(bool)
    prev_ok = prev_pts.reshape(-1, 2)[status]
    cur_ok = cur_pts.reshape(-1, 2)[status]
    if len(prev_ok) < MIN_TRACKED_POINTS:
        return None, None
    return prev_ok, cur_ok


def _frame_deltas(gray_frames):
    """(dx, dy, da, d_log_scale) cuadro-a-cuadro vía RANSAC sobre features
    autodetectadas. La escala se guarda en log para que el suavizado (que es
    un promedio) sea simétrico alrededor de "sin cambio" (0 en vez de 1).

    Si un par de frames no da suficientes features/inliers (motion blur
    fuerte, escena sin textura, corte de plano), ese delta queda en (0,0,0,0)
    -- "asumir que la cámara no se movió" es la degradación más segura, en
    vez de arriesgar una estimación con 3 puntos ruidosos.
    """
    n = len(gray_frames)
    deltas = np.zeros((n - 1, 4), dtype=np.float64)
    failures = 0

    for i in range(n - 1):
        prev_pts, cur_pts = _detect_and_track(gray_frames[i], gray_frames[i + 1])
        if prev_pts is None:
            failures += 1
            continue

        m, _inliers = cv2.estimateAffinePartial2D(
            prev_pts, cur_pts, method=cv2.RANSAC, ransacReprojThreshold=3.0, maxIters=2000
        )
        if m is None:
            failures += 1
            continue

        dx, dy = float(m[0, 2]), float(m[1, 2])
        da = math.atan2(float(m[1, 0]), float(m[0, 0]))
        scale = math.hypot(float(m[0, 0]), float(m[1, 0]))
        d_log_scale = math.log(scale) if scale > 1e-6 else 0.0
        deltas[i] = (dx, dy, da, d_log_scale)

    return deltas, failures


# --------------------------------------------------------------------------
# suavizado de trayectoria
# --------------------------------------------------------------------------

def _moving_average(values, radius):
    """Media móvil centrada, con padding por replicación en los bordes (así
    la ventana no se angosta -y el suavizado no se debilita- cerca del
    principio/final del clip)."""
    radius = max(1, int(radius))
    window = 2 * radius + 1
    padded = np.pad(values, (radius, radius), mode="edge")
    kernel = np.ones(window) / window
    return np.convolve(padded, kernel, mode="same")[radius:-radius]


def _smooth_transforms(deltas, radius):
    """Suaviza la trayectoria acumulada de cámara y devuelve los deltas
    cuadro-a-cuadro corregidos (mismo shape que `deltas`)."""
    trajectory = np.cumsum(deltas, axis=0)
    smoothed = np.empty_like(trajectory)
    for c in range(trajectory.shape[1]):
        smoothed[:, c] = _moving_average(trajectory[:, c], radius)
    correction = smoothed - trajectory
    return deltas + correction


def _build_matrix(dx, dy, da, d_log_scale, correct_rotation, correct_scale, max_angle_rad):
    da = float(np.clip(da, -max_angle_rad, max_angle_rad)) if correct_rotation else 0.0
    scale = math.exp(d_log_scale) if correct_scale else 1.0
    cos_a, sin_a = math.cos(da) * scale, math.sin(da) * scale
    return np.array([[cos_a, -sin_a, dx], [sin_a, cos_a, dy]], dtype=np.float32)


# --------------------------------------------------------------------------
# pipeline completo
# --------------------------------------------------------------------------

def stabilize(
    frames,
    smoothing_radius=30,
    correct_rotation=True,
    correct_scale=True,
    max_correction_angle_deg=15.0,
    auto_crop=True,
    resize_to_original=True,
):
    """frames: array (T, H, W, 3) float 0..1.

    Devuelve (frames_estabilizados, informe_dict).
    """
    frames = np.asarray(frames, dtype=np.float32)
    n_frames, height, width = frames.shape[0], frames.shape[1], frames.shape[2]

    if n_frames < 3:
        return frames, {"frames": int(n_frames), "note": "hacen falta al menos 3 frames para estabilizar"}

    gray = [to_gray_u8(frames[i]) for i in range(n_frames)]
    deltas, failures = _frame_deltas(gray)
    transforms_smooth = _smooth_transforms(deltas, smoothing_radius)

    max_angle_rad = math.radians(max_correction_angle_deg)
    matrices = [np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)]
    for dx, dy, da, ds in transforms_smooth:
        matrices.append(_build_matrix(dx, dy, da, ds, correct_rotation, correct_scale, max_angle_rad))

    warped = np.empty_like(frames)
    for t in range(n_frames):
        warped[t] = cv2.warpAffine(
            frames[t],
            matrices[t],
            (width, height),
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_REPLICATE,
        )
    np.clip(warped, 0.0, 1.0, out=warped)

    warped, crop_box = apply_crop_and_resize(warped, matrices, width, height, auto_crop, resize_to_original)

    # Lanczos puede sobrepasar el rango al interpolar: recortamos al final.
    np.clip(warped, 0.0, 1.0, out=warped)

    raw_path = np.cumsum(deltas, axis=0)
    smooth_path = np.cumsum(transforms_smooth, axis=0)
    max_shake_px = (
        float(np.max(np.linalg.norm(raw_path[:, :2] - smooth_path[:, :2], axis=1)))
        if len(raw_path) else 0.0
    )

    report = {
        "frames": int(n_frames),
        "input_size": f"{width}x{height}",
        "output_size": f"{warped.shape[2]}x{warped.shape[1]}",
        "crop_box": crop_box,
        "smoothing_radius": int(smoothing_radius),
        "shake_corregido_max_px": round(max_shake_px, 3),
        "pares_de_frames_sin_features_suficientes": int(failures),
    }
    return warped, report
