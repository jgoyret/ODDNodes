import os
from PIL import Image
import numpy as np
import torch

class RecursiveImageLoader:
    CATEGORY = "ODDNodes/IO"
    RETURN_TYPES = ("IMAGE", "STRING",)
    RETURN_NAMES = ("Image List", "Path List")
    FUNCTION = "load_images"
    OUTPUT_IS_LIST = (True, True)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "folder_path": ("STRING", {
                    "default": "./input_folder"
                }),
            }
        }

    def load_images(self, folder_path):
        supported_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        image_list = []
        path_list = []

        for root, _, files in os.walk(folder_path):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in supported_exts:
                    full_path = os.path.join(root, f)
                    img = Image.open(full_path).convert("RGB")
                    img_np = np.array(img).astype(np.float32) / 255.0
                    img_tensor = torch.from_numpy(img_np).unsqueeze(0)
                    image_list.append(img_tensor)
                    path_list.append(full_path)

        return (image_list, path_list)

NODE_CLASS_MAPPINGS = {
    "ODD_RecursiveImageLoader": RecursiveImageLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ODD_RecursiveImageLoader": "Recursive Image Loader",
}