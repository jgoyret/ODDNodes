"""
Núcleo de estabilización por "point lock": ancla uno o dos puntos elegidos a
mano a su posición del frame 0. Sirve para casos donde necesitás que una
región puntual del cuadro quede perfectamente estática pase lo que pase con
el resto de la imagen -- por ejemplo la nariz en un render de cabeza
parlante que se va a retargetear a un modelo 3D: si la cabeza hace un
gesto ("no" con la cabeza, etc.), el punto de la nariz se movería en pantalla
aunque conceptualmente el modelo 3D quiere que ese punto sea el "cero" fijo
del rig. Es un objetivo distinto al de `video_stabilize_core` (que suaviza
temblor de cámara conservando el movimiento real): acá el punto elegido debe
quedar clavado, no simplemente suavizado.

Modo de 1 punto: traslación pura (dx, dy = referencia - tracking). No hay
ratio de distancia entre dos puntos, así que no es sensible al jitter de
tracking sub-píxel -- es el modo recomendado por defecto.

Modo de 2 puntos: el primer punto queda anclado exacto en todos los frames
(igual que el modo de 1 punto); el segundo punto define rotación/escala, pero
esos dos valores se derivan de la distancia entre ambos puntos y SÍ son
sensibles al ruido de tracking frame a frame -- por eso se suavizan con una
media móvil corta (`rotation_scale_smoothing`) antes de aplicarse. La
traslación nunca se suaviza: el punto ancla siempre quede exacto.

Solo numpy + OpenCV, sin torch.
"""

import math
import numpy as np
import cv2

from ._stabilize_common import to_gray_u8, apply_crop_and_resize


# --------------------------------------------------------------------------
# template matching (recupera el punto si el optical flow lo pierde)
# --------------------------------------------------------------------------

def _subpixel_offset(response, loc):
    """Ajuste parabólico de 3 puntos alrededor del máximo, en x e y."""
    x, y = loc
    h, w = response.shape
    dx = dy = 0.0
    if 0 < x < w - 1:
        l, c, r = float(response[y, x - 1]), float(response[y, x]), float(response[y, x + 1])
        den = l - 2.0 * c + r
        if abs(den) > 1e-9:
            dx = 0.5 * (l - r) / den
    if 0 < y < h - 1:
        u, c, d = float(response[y - 1, x]), float(response[y, x]), float(response[y + 1, x])
        den = u - 2.0 * c + d
        if abs(den) > 1e-9:
            dy = 0.5 * (u - d) / den
    # un ajuste subpíxel sano nunca supera medio píxel
    return float(np.clip(dx, -0.5, 0.5)), float(np.clip(dy, -0.5, 0.5))


def _extract_template(gray, point, win):
    """Devuelve (parche, (offset_x, offset_y)) donde el offset es la posición
    del punto pedido dentro del parche."""
    half = max(2, win // 2)
    px, py = int(round(point[0])), int(round(point[1]))
    x0 = max(0, px - half)
    y0 = max(0, py - half)
    x1 = min(gray.shape[1], px + half + 1)
    y1 = min(gray.shape[0], py + half + 1)
    patch = gray[y0:y1, x0:x1].copy()
    return patch, (px - x0, py - y0)


def _match_template(gray, template_pack, around, radius, min_confidence=0.5):
    """Busca el parche del frame 0 cerca de `around`. Devuelve punto o None."""
    tmpl, (off_x, off_y) = template_pack
    th, tw = tmpl.shape[:2]
    if th < 3 or tw < 3:
        return None

    cx, cy = int(round(around[0])), int(round(around[1]))
    x0 = max(0, cx - off_x - radius)
    y0 = max(0, cy - off_y - radius)
    x1 = min(gray.shape[1], cx - off_x + tw + radius)
    y1 = min(gray.shape[0], cy - off_y + th + radius)
    roi = gray[y0:y1, x0:x1]
    if roi.shape[0] < th or roi.shape[1] < tw:
        return None

    response = cv2.matchTemplate(roi, tmpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(response)
    if max_val < min_confidence:
        return None
    dx, dy = _subpixel_offset(response, max_loc)
    return np.array(
        [x0 + max_loc[0] + dx + off_x, y0 + max_loc[1] + dy + off_y],
        dtype=np.float32,
    )


# --------------------------------------------------------------------------
# tracking
# --------------------------------------------------------------------------

def track_points(gray_frames, start_points, win=31, fb_threshold=1.5, search_radius=24, match_confidence=0.5):
    """Sigue N puntos a lo largo de la secuencia.

    Lucas-Kanade piramidal frame a frame, con chequeo forward-backward.
    Si un punto falla el chequeo (o el flujo óptico lo movió más de lo que
    un frame de video puede mover algo de verdad), se recupera por template
    matching contra el parche del frame 0 -- así el error no se acumula
    indefinidamente. `match_confidence` filtra matches dudosos: si ninguna
    zona cercana se parece lo suficiente al parche original, el punto se
    congela en su última posición conocida en vez de saltar a una zona
    parecida pero incorrecta.

    gray_frames  : lista de HxW uint8
    start_points : (N, 2) float32, coordenadas en el frame 0
    return       : (T, N, 2) float32
    """
    win = max(7, int(win) | 1)  # impar y no minúsculo
    lk_params = dict(
        winSize=(win, win),
        maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 40, 0.005),
    )
    # Un punto real no puede saltar más que esto en un solo frame; si el flujo
    # óptico lo mueve más lejos, tratamos ese resultado como no confiable.
    max_jump = max(8.0, float(search_radius) * 1.5)

    n_frames = len(gray_frames)
    points = np.asarray(start_points, dtype=np.float32).reshape(-1, 2)
    n_points = points.shape[0]

    tracks = np.zeros((n_frames, n_points, 2), dtype=np.float32)
    tracks[0] = points
    recovered = 0

    templates = [_extract_template(gray_frames[0], points[i], win) for i in range(n_points)]

    prev_gray = gray_frames[0]
    prev_pts = points.copy().reshape(-1, 1, 2)

    for t in range(1, n_frames):
        cur_gray = gray_frames[t]

        fwd, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, cur_gray, prev_pts, None, **lk_params)
        back, _, _ = cv2.calcOpticalFlowPyrLK(cur_gray, prev_gray, fwd, None, **lk_params)
        fb_error = np.linalg.norm(prev_pts - back, axis=2).reshape(-1)

        result = fwd.reshape(-1, 2).copy()
        for i in range(n_points):
            jump = float(np.linalg.norm(result[i] - tracks[t - 1][i]))
            failed = (
                status.reshape(-1)[i] == 0
                or not np.isfinite(result[i]).all()
                or fb_error[i] > fb_threshold
                or jump > max_jump
            )
            if failed:
                fallback = _match_template(
                    cur_gray, templates[i], tracks[t - 1][i], search_radius,
                    min_confidence=match_confidence,
                )
                result[i] = fallback if fallback is not None else tracks[t - 1][i]
                recovered += 1

        # clamp defensivo dentro del cuadro
        result[:, 0] = np.clip(result[:, 0], 0, cur_gray.shape[1] - 1)
        result[:, 1] = np.clip(result[:, 1], 0, cur_gray.shape[0] - 1)

        tracks[t] = result
        prev_gray = cur_gray
        prev_pts = result.reshape(-1, 1, 2).astype(np.float32)

    return tracks, recovered


# --------------------------------------------------------------------------
# transformaciones
# --------------------------------------------------------------------------

def translation_matrix(now_pt, ref_pt):
    dx = float(ref_pt[0]) - float(now_pt[0])
    dy = float(ref_pt[1]) - float(now_pt[1])
    return np.array([[1.0, 0.0, dx], [0.0, 1.0, dy]], dtype=np.float32)


def _raw_angle_scale(now_pts, ref_pts):
    """Ángulo y escala crudos (ruidosos) que llevarían el segundo punto a su
    posición de referencia, dado que el primero ya está anclado."""
    a_now = complex(float(now_pts[0][0]), float(now_pts[0][1]))
    b_now = complex(float(now_pts[1][0]), float(now_pts[1][1]))
    a_ref = complex(float(ref_pts[0][0]), float(ref_pts[0][1]))
    b_ref = complex(float(ref_pts[1][0]), float(ref_pts[1][1]))

    v_now = b_now - a_now
    v_ref = b_ref - a_ref
    if abs(v_now) < 1e-6 or abs(v_ref) < 1e-6:
        return 0.0, 1.0
    ratio = v_ref / v_now
    return math.atan2(ratio.imag, ratio.real), abs(ratio)


def _moving_average(values, radius):
    """Media móvil centrada, con padding por replicación en los bordes."""
    radius = max(1, int(radius))
    window = 2 * radius + 1
    padded = np.pad(values, (radius, radius), mode="edge")
    kernel = np.ones(window) / window
    return np.convolve(padded, kernel, mode="same")[radius:-radius]


def _similarity_matrix_anchored(a_now, a_ref, angle, scale):
    """Matriz que ancla `a_now` exacto en `a_ref`, y rota/escala alrededor de eso."""
    a = scale * complex(math.cos(angle), math.sin(angle))
    b = complex(float(a_ref[0]), float(a_ref[1])) - a * complex(float(a_now[0]), float(a_now[1]))
    return np.array(
        [[a.real, -a.imag, b.real],
         [a.imag,  a.real, b.imag]],
        dtype=np.float32,
    )


def draw_markers(frame, points, size=14, thickness=2):
    """Dibuja cruces numeradas sobre una copia del frame (float 0..1)."""
    canvas = np.clip(frame * 255.0, 0, 255).astype(np.uint8).copy()
    palette = [(255, 60, 60), (60, 200, 255), (120, 255, 120), (255, 220, 60)]
    for idx, (px, py) in enumerate(np.asarray(points, dtype=np.float32).reshape(-1, 2)):
        x, y = int(round(px)), int(round(py))
        color = palette[idx % len(palette)]
        cv2.line(canvas, (x - size, y), (x + size, y), color, thickness, cv2.LINE_AA)
        cv2.line(canvas, (x, y - size), (x, y + size), color, thickness, cv2.LINE_AA)
        cv2.circle(canvas, (x, y), size, color, thickness, cv2.LINE_AA)
        cv2.putText(
            canvas, str(idx + 1), (x + size + 4, y - size - 4),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, thickness, cv2.LINE_AA,
        )
    return canvas.astype(np.float32) / 255.0


# --------------------------------------------------------------------------
# pipeline completo
# --------------------------------------------------------------------------

def stabilize(
    frames,
    points,
    mode="one_point",
    track_window=31,
    search_radius=24,
    match_confidence=0.5,
    correct_rotation=True,
    correct_scale=True,
    rotation_scale_smoothing=5,
    auto_crop=True,
    resize_to_original=True,
):
    """frames: array (T, H, W, 3) float 0..1.  points: lista de (x, y) del frame 0.

    Devuelve (frames_estabilizados, informe_dict).
    """
    frames = np.asarray(frames, dtype=np.float32)
    n_frames, height, width = frames.shape[0], frames.shape[1], frames.shape[2]

    points = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    if mode == "one_point":
        points = points[:1]
    elif points.shape[0] < 2:
        raise ValueError("El modo de dos puntos necesita dos puntos.")

    if n_frames < 2:
        return frames, {"frames": int(n_frames), "note": "un solo frame, nada que estabilizar"}

    gray = [to_gray_u8(frames[i]) for i in range(n_frames)]
    tracks, recovered = track_points(
        gray, points, win=track_window, search_radius=search_radius,
        match_confidence=match_confidence,
    )
    reference = tracks[0]

    if mode == "one_point":
        matrices = [translation_matrix(tracks[t][0], reference[0]) for t in range(n_frames)]
    else:
        raw_angle = np.zeros(n_frames, dtype=np.float64)
        raw_scale = np.ones(n_frames, dtype=np.float64)
        for t in range(n_frames):
            raw_angle[t], raw_scale[t] = _raw_angle_scale(tracks[t], reference)

        angle = _moving_average(raw_angle, rotation_scale_smoothing) if correct_rotation else np.zeros(n_frames)
        if correct_scale:
            log_scale = _moving_average(np.log(np.clip(raw_scale, 1e-6, None)), rotation_scale_smoothing)
            scale = np.exp(log_scale)
        else:
            scale = np.ones(n_frames)

        matrices = [
            _similarity_matrix_anchored(tracks[t][0], reference[0], angle[t], scale[t])
            for t in range(n_frames)
        ]

    warped = np.empty_like(frames)
    for t in range(n_frames):
        warped[t] = cv2.warpAffine(
            frames[t], matrices[t], (width, height),
            flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE,
        )
    np.clip(warped, 0.0, 1.0, out=warped)

    warped, crop_box = apply_crop_and_resize(warped, matrices, width, height, auto_crop, resize_to_original)
    np.clip(warped, 0.0, 1.0, out=warped)

    # métricas antes / después
    raw_motion = tracks - reference[None, :, :]
    raw_max = float(np.max(np.linalg.norm(raw_motion, axis=2)))

    residual = []
    for t in range(n_frames):
        m = matrices[t]
        pts = np.hstack([tracks[t], np.ones((tracks[t].shape[0], 1), np.float32)])
        moved = (m @ pts.T).T
        residual.append(np.linalg.norm(moved - reference, axis=1))
    residual_max = float(np.max(residual))

    report = {
        "frames": int(n_frames),
        "mode": mode,
        "input_size": f"{width}x{height}",
        "output_size": f"{warped.shape[2]}x{warped.shape[1]}",
        "crop_box": crop_box,
        "movimiento_antes_px": round(raw_max, 3),
        "movimiento_despues_px": round(residual_max, 3),
        "puntos_recuperados_por_template": int(recovered),
    }
    return warped, report
