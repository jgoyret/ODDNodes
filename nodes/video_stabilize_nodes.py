"""Nodo de ComfyUI para estabilización de video.

Un solo nodo, dos métodos:
- Warp automático: suaviza el temblor de cámara (tracking de features en toda
  la imagen + suavizado de la trayectoria), conservando paneos/dollys reales.
- Point Lock: ancla un punto elegido a mano (click sobre el preview del
  nodo) a su posición del frame 0. Para cuando necesitás que una región
  puntual del cuadro quede perfectamente estática -- ej. la nariz en un
  render de cabeza parlante que se va a retargetear a un modelo 3D.
"""

import json
import os

import numpy as np
import torch
from PIL import Image

import folder_paths

from .video_stabilize_core import stabilize as stabilize_warp
from .point_lock_core import stabilize as stabilize_point_lock, draw_markers

METHOD_WARP = "Warp automático (shake de cámara)"
METHOD_ONE_POINT = "Point Lock — 1 punto (traslación)"
METHOD_TWO_POINTS = "Point Lock — 2 puntos (traslación + rotación/escala)"
METHODS = [METHOD_WARP, METHOD_ONE_POINT, METHOD_TWO_POINTS]


def _to_numpy(images):
    """IMAGE de ComfyUI (B,H,W,C torch float 0..1) -> numpy float32."""
    return images.detach().cpu().numpy().astype(np.float32)


def _to_torch(array, like):
    return torch.from_numpy(np.ascontiguousarray(array)).to(like.device, dtype=like.dtype)


def _parse_points(raw):
    """JSON tipo "[[x1,y1],[x2,y2]]" (lo escribe el canvas del nodo) -> lista de tuplas."""
    try:
        parsed = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        return []
    points = []
    for p in parsed:
        if isinstance(p, (list, tuple)) and len(p) == 2:
            try:
                points.append((float(p[0]), float(p[1])))
            except (TypeError, ValueError):
                continue
    return points


def _save_preview(frame_float_rgb, points):
    """Guarda el frame 0 (con los puntos marcados) como PNG temporal y devuelve
    el dict que ComfyUI espera en el `ui.images` de la respuesta de un nodo,
    para que el widget de canvas del front-end lo pueda cargar."""
    marked = draw_markers(frame_float_rgb, points) if points else frame_float_rgb
    arr8 = np.clip(marked * 255.0, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr8)

    out_dir = folder_paths.get_temp_directory()
    os.makedirs(out_dir, exist_ok=True)
    full_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
        "video_stabilize_preview", out_dir, arr8.shape[1], arr8.shape[0]
    )
    file = f"{filename}_{counter:05}_.png"
    img.save(os.path.join(full_folder, file), compress_level=1)
    return [{"filename": file, "subfolder": subfolder, "type": "temp"}]


class VideoStabilize:
    """Estabiliza un video. 'Warp automático' suaviza el temblor de cámara
    conservando el movimiento real (paneos/dollys atenuados, no anulados).
    'Point Lock' ancla un punto elegido a mano a su posición del frame 0,
    para cuando una región puntual del cuadro necesita quedar perfectamente
    estática pase lo que pase con el resto de la imagen."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "method": (METHODS, {"default": METHODS[0]}),
                # -- Warp automático --
                "smoothness": ("INT", {
                    "default": 30, "min": 1, "max": 200,
                    "tooltip": "Solo Warp automático. Radio en frames de la ventana de suavizado "
                               "(equivalente al 'Smoothness %' de Premiere).",
                }),
                "max_rotation_correction_deg": ("FLOAT", {
                    "default": 15.0, "min": 0.5, "max": 45.0, "step": 0.5,
                    "tooltip": "Solo Warp automático. Límite de seguridad de rotación corregida por frame.",
                }),
                # -- Point Lock --
                "points": ("STRING", {"default": "[]", "multiline": False}),
                "track_window": ("INT", {
                    "default": 31, "min": 7, "max": 201, "step": 2,
                    "tooltip": "Solo Point Lock. Tamaño de la ventana de tracking alrededor de cada punto.",
                }),
                "search_radius": ("INT", {
                    "default": 24, "min": 4, "max": 200, "step": 1,
                    "tooltip": "Solo Point Lock. Radio de búsqueda para recuperar un punto si el tracking lo pierde.",
                }),
                "match_confidence": ("FLOAT", {
                    "default": 0.5, "min": 0.05, "max": 0.95, "step": 0.05,
                    "tooltip": "Solo Point Lock. Confianza mínima del template matching de recuperación.",
                }),
                "point_lock_smoothing": ("INT", {
                    "default": 5, "min": 1, "max": 60,
                    "tooltip": "Solo Point Lock de 2 puntos. Suaviza la rotación/escala derivada del segundo "
                               "punto (la traslación del primer punto siempre queda exacta).",
                }),
                # -- comunes a Warp y Point Lock de 2 puntos --
                "correct_rotation": ("BOOLEAN", {"default": True}),
                "correct_scale": ("BOOLEAN", {"default": True}),
                "auto_crop": ("BOOLEAN", {"default": True}),
                "resize_to_original": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("images", "report")
    FUNCTION = "run"
    CATEGORY = "ODDNodes/Video"
    OUTPUT_NODE = True

    def run(
        self, images, method, smoothness, max_rotation_correction_deg,
        points, track_window, search_radius, match_confidence, point_lock_smoothing,
        correct_rotation, correct_scale, auto_crop, resize_to_original,
    ):
        frames = _to_numpy(images)

        if method == METHOD_WARP:
            preview_ui = []
            result, report = stabilize_warp(
                frames,
                smoothing_radius=int(smoothness),
                correct_rotation=bool(correct_rotation),
                correct_scale=bool(correct_scale),
                max_correction_angle_deg=float(max_rotation_correction_deg),
                auto_crop=bool(auto_crop),
                resize_to_original=bool(resize_to_original),
            )
        else:
            needed = 1 if method == METHOD_ONE_POINT else 2
            pts = _parse_points(points)[:needed]
            preview_ui = _save_preview(frames[0], pts)

            if len(pts) < needed:
                text = (
                    f"[Point Lock] Faltan puntos: marcá {needed} en el preview del nodo "
                    f"(tenés {len(pts)}) y volvé a encolar."
                )
                return {"ui": {"images": preview_ui}, "result": (images, text)}

            result, report = stabilize_point_lock(
                frames,
                pts,
                mode="one_point" if needed == 1 else "two_points",
                track_window=int(track_window),
                search_radius=int(search_radius),
                match_confidence=float(match_confidence),
                correct_rotation=bool(correct_rotation),
                correct_scale=bool(correct_scale),
                rotation_scale_smoothing=int(point_lock_smoothing),
                auto_crop=bool(auto_crop),
                resize_to_original=bool(resize_to_original),
            )

        lines = [f"[{method}]"]
        for key, value in report.items():
            lines.append(f"  {key}: {value}")
        text = "\n".join(lines)
        print(text)
        return {"ui": {"images": preview_ui}, "result": (_to_torch(result, images), text)}


NODE_CLASS_MAPPINGS = {
    "ODD_VideoStabilize": VideoStabilize,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ODD_VideoStabilize": "Estabilizador de Video",
}
