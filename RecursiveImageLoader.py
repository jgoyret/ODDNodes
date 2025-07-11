import os
from PIL import Image
import numpy as np
import torch

class RecursiveImageLoader:
    CATEGORY = "Picta/IO"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("Image", "Path")
    FUNCTION = "load_images"
    OUTPUT_IS_LIST = (False, False)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "folder_path": ("STRING", {"default": "./input_folder"}),
                "mode": (["single", "batch"],),
            }
        }

    def __init__(self):
        self._image_list = []
        self._path_list = []
        self._index = 0
        self._last_folder = None

    def load_images(self, folder_path, mode):
        supported_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

        # Solo recarga si el folder cambió o no hay imágenes cargadas
        if not self._image_list or self._last_folder != folder_path:
            self._image_list = []
            self._path_list = []
            self._index = 0
            self._last_folder = folder_path

            for root, _, files in os.walk(folder_path):
                for f in sorted(files):
                    ext = os.path.splitext(f)[1].lower()
                    if ext in supported_exts:
                        full_path = os.path.join(root, f)
                        img = Image.open(full_path).convert("RGB")
                        img_np = np.array(img).astype(np.float32) / 255.0
                        img_tensor = torch.from_numpy(img_np).unsqueeze(0)
                        self._image_list.append(img_tensor)
                        self._path_list.append(full_path)

        if mode == "batch":
            return (self._image_list, self._path_list)

        # modo single (una imagen por ejecución)
        if self._index >= len(self._image_list):
            return (None, None)

        img = self._image_list[self._index]
        path = self._path_list[self._index]
        self._index += 1
        return (img, path)


NODE_CLASS_MAPPINGS = {
    "Picta_RecursiveImageLoader": RecursiveImageLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Picta_RecursiveImageLoader": "Recursive Image Loader",
}