import os
from PIL import Image
import numpy as np

class SaveImageWithStructure:
    CATEGORY = "Picta/IO"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "save_images"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "original_path": ("STRING",),
                "output_base_folder": ("STRING", {"default": "./output_folder"}),
                "input_base_folder": ("STRING", {"default": "./input_folder"}),
            }
        }

    OUTPUT_IS_LIST = (False, False, False, False)

    def save_images(self, image, original_path, output_base_folder, input_base_folder):
        if not isinstance(image, list):
            image = [image]
        if not isinstance(original_path, list):
            original_path = [original_path]

        if len(image) != len(original_path):
            raise ValueError("Image list and path list must have the same length.")

        count = 0
        for img_tensor, path in zip(image, original_path):
            try:
                img_np = (img_tensor[0].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
                img = Image.fromarray(img_np)

                rel_path = os.path.relpath(path, input_base_folder)
                output_path = os.path.join(output_base_folder, rel_path)
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                img.save(output_path)
                count += 1
            except Exception as e:
                print(f"❌ Error al guardar {path}: {e}")

        return (f"Guardadas {count} imágenes.",)

NODE_CLASS_MAPPINGS = {
    "Picta_SaveImageWithStructure": SaveImageWithStructure,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Picta_SaveImageWithStructure": "Save Image With Structure",
}