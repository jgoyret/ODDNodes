"""Dataset QC tools — browse a folder of image+JSON pairs one at a time, and
save corrections back to disk. Built to pair with KJNodes' Ideogram 4 Prompt
Builder (visual bbox editor) for reviewing/fixing Ideogram 4 caption datasets.
"""

import json
import os
import random
import re
import shutil

import numpy as np
import torch
from PIL import Image

import folder_paths

_IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")
_TEMP_PREFIX = "_odd_dataset_qc_" + "".join(random.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(5))


def _save_temp_preview(pil):
    # Same convention core PreviewImage uses (temp dir, type "temp") so other
    # nodes' "on any node's execution, images -> use as reference" listeners
    # (e.g. KJNodes' Ideogram 4 Prompt Builder "Grab BG") pick it up too.
    output_dir = folder_paths.get_temp_directory()
    full_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
        _TEMP_PREFIX, output_dir, pil.width, pil.height
    )
    file = f"{filename}_{counter:05}_.png"
    pil.save(os.path.join(full_folder, file), compress_level=1)
    return [{"filename": file, "subfolder": subfolder, "type": "temp"}]


def _natural_key(s):
    # "Max_2.png" < "Max_9.png" < "Max_10.png" (not lexicographic).
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _clean_path(p):
    return (p or "").strip().strip('"').strip("'")


def _list_images(folder_path):
    return sorted(
        [f for f in os.listdir(folder_path) if f.lower().endswith(_IMG_EXTS)],
        key=_natural_key,
    )


def _blank_image():
    return torch.zeros((1, 64, 64, 3), dtype=torch.float32)


class ODD_DatasetFolderBrowser:
    """Loads image[index] + its sibling .json from a folder, with natural
    filename sort. Pair the 'Prev'/'Next' buttons (added client-side) with
    Queue Prompt to step through a dataset one file at a time."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "folder_path": ("STRING", {"default": "", "multiline": False}),
                "index": ("INT", {"default": 0, "min": 0, "max": 999999, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING", "INT", "INT", "INT", "STRING")
    RETURN_NAMES = ("image", "json_string", "filename", "folder_path", "width", "height", "total_count", "status")
    FUNCTION = "load"
    CATEGORY = "ODDNodes/Dataset QC"

    def load(self, folder_path, index):
        folder_path = _clean_path(folder_path)

        if not os.path.isdir(folder_path):
            status = f"ERROR: folder not found: {folder_path}"
            result = (_blank_image(), "", "", folder_path, 0, 0, 0, status)
            return {"ui": {"text": [status], "width": [0], "height": [0]}, "result": result}

        files = _list_images(folder_path)
        total = len(files)
        if total == 0:
            status = f"ERROR: no images (.png/.jpg/.jpeg/.webp) found in {folder_path}"
            result = (_blank_image(), "", "", folder_path, 0, 0, 0, status)
            return {"ui": {"text": [status], "width": [0], "height": [0]}, "result": result}

        idx = max(0, min(index, total - 1))
        fname = files[idx]
        base = os.path.splitext(fname)[0]
        img_path = os.path.join(folder_path, fname)
        json_path = os.path.join(folder_path, base + ".json")

        pil = Image.open(img_path).convert("RGB")
        width, height = pil.width, pil.height
        arr = np.asarray(pil, dtype=np.float32) / 255.0
        tensor = torch.from_numpy(arr).unsqueeze(0)

        json_string = ""
        status = f"{idx + 1}/{total}  —  {fname}  ({width}x{height})"
        if os.path.isfile(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                json_string = f.read()
        else:
            status += "   [NO JSON YET]"

        try:
            preview_images = _save_temp_preview(pil)
        except Exception:
            preview_images = []

        result = (tensor, json_string, fname, folder_path, width, height, total, status)
        return {
            "ui": {"text": [status], "width": [width], "height": [height], "images": preview_images},
            "result": result,
        }

    @classmethod
    def IS_CHANGED(cls, folder_path, index):
        # Widget values alone would make ComfyUI cache stale output if a file on
        # disk changed (e.g. after Save) while index/folder stayed the same —
        # fold in mtimes so revisiting an index always reflects current disk state.
        folder_path = _clean_path(folder_path)
        try:
            files = _list_images(folder_path)
            if not files:
                return "empty"
            idx = max(0, min(index, len(files) - 1))
            fname = files[idx]
            base = os.path.splitext(fname)[0]
            img_path = os.path.join(folder_path, fname)
            json_path = os.path.join(folder_path, base + ".json")
            mtimes = [
                os.path.getmtime(p) if os.path.isfile(p) else 0
                for p in (img_path, json_path)
            ]
            return f"{fname}:{mtimes}"
        except Exception as e:
            return f"error:{e}"


def _write_json_string(folder_path, filename, json_string):
    """Validates and writes json_string to <folder_path>/<filename base>.json,
    overwriting the original. Keeps a one-time .bak of the original content the
    first time a given file is touched. Returns (status, error) — error is None
    on success, and status is None on failure."""
    folder_path = _clean_path(folder_path)

    if not folder_path or not os.path.isdir(folder_path):
        return None, f"folder not found: {folder_path}"
    if not filename:
        return None, "no filename given"
    if not json_string or not json_string.strip():
        return None, "json_string is empty — refusing to overwrite the file"

    try:
        parsed = json.loads(json_string)
    except json.JSONDecodeError as e:
        return None, f"invalid JSON, NOT saved: {e}"

    base = os.path.splitext(filename)[0]
    json_path = os.path.join(folder_path, base + ".json")

    # One-time backup of whatever was on disk before the first save this session.
    if os.path.isfile(json_path):
        bak_path = json_path + ".bak"
        if not os.path.isfile(bak_path):
            try:
                shutil.copyfile(json_path, bak_path)
            except Exception:
                pass

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)
        f.write("\n")

    return f"Saved: {json_path}", None


class ODD_SaveIdeogram4Json:
    """Writes json_string back to <folder_path>/<filename base>.json, overwriting
    the original. Refuses to save empty or invalid JSON. Keeps a one-time .bak
    of the original content the first time a given file is touched."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "folder_path": ("STRING", {"default": "", "multiline": False}),
                "filename": ("STRING", {"default": "", "multiline": False}),
                "json_string": ("STRING", {"default": "", "multiline": True, "forceInput": True}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "save"
    CATEGORY = "ODDNodes/Dataset QC"
    OUTPUT_NODE = True

    def save(self, folder_path, filename, json_string):
        status, error = _write_json_string(folder_path, filename, json_string)
        if error:
            status = f"ERROR: {error}"
        return {"ui": {"text": [status]}, "result": (status,)}
