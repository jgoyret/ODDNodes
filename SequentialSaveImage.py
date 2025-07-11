import os
from PIL import Image
import numpy as np

class SequentialSaveImage:
    CATEGORY = "Picta/IO"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "save_image"
    OUTPUT_IS_LIST = (False,)

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

    def save_image(self, image, original_path, output_base_folder, input_base_folder):
        try:
            img_np = (image[0].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
            img = Image.fromarray(img_np)

            rel_path = os.path.relpath(original_path, input_base_folder)
            output_path = os.path.join(output_base_folder, rel_path)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            img.save(output_path)
            return (f"✅ Guardada: {output_path}",)
        except Exception as e:
            return (f"❌ Error: {str(e)}",)

NODE_CLASS_MAPPINGS = {
    "Picta_SequentialSaveImage": SequentialSaveImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Picta_SequentialSaveImage": "Sequential Save Image",
}
