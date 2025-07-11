import os
from PIL import Image
import numpy as np
import torch

class SequentialImageLoader:
    CATEGORY = "Picta/IO"
    RETURN_TYPES = ("IMAGE", "STRING",)
    RETURN_NAMES = ("Image", "Path")
    FUNCTION = "load_next"
    OUTPUT_IS_LIST = (False, False)

    def __init__(self):
        self.image_paths = []
        self.index = 0
        self.last_folder = ""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "folder_path": ("STRING", {"default": "./input_folder"})
            }
        }

    def load_next(self, folder_path):
        if self.last_folder != folder_path:
            self.last_folder = folder_path
            self.index = 0
            self.image_paths = self._gather_image_paths(folder_path)

        if self.index >= len(self.image_paths):
            print("✅ Todas las imágenes fueron procesadas.")
            return (torch.zeros(1, 512, 512, 3), "")

        path = self.image_paths[self.index]
        self.index += 1

        img = Image.open(path).convert("RGB")
        img_np = np.array(img).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).unsqueeze(0)

        return (img_tensor, path)

    def _gather_image_paths(self, folder_path):
        supported_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        paths = []
        for root, _, files in os.walk(folder_path):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in supported_exts:
                    paths.append(os.path.join(root, f))
        paths.sort()
        return paths

NODE_CLASS_MAPPINGS = {
    "Picta_SequentialImageLoader": SequentialImageLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Picta_SequentialImageLoader": "Sequential Image Loader",
}
