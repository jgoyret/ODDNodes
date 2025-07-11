from PIL import Image
import numpy as np
import torch

class TintedImageByHexColor:
    CATEGORY = "Picta/Color"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("Tinted Image",)
    FUNCTION = "apply_tint"
    OUTPUT_IS_LIST = (False,)
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "hex_color": ("STRING", {
                    "default": "#FF0000",
                }),
                "intensity": ("FLOAT", {
                    "default": 0.5,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.01,
                }),
            }
        }

    def apply_tint(self, image, hex_color, intensity):
        # Convert tensor to PIL
        img = Image.fromarray((image[0].cpu().numpy() * 255).astype(np.uint8))

        # Parse hex color
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

        # Create a tint image
        tint = Image.new("RGB", img.size, (r, g, b))
        blended = Image.blend(img.convert("RGB"), tint, intensity)

        # Convert back to tensor
        img_np = np.array(blended).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).unsqueeze(0)

        return (img_tensor,)

# Registrar el nodo
NODE_CLASS_MAPPINGS = {
    "Picta_TintedImageByHexColor": TintedImageByHexColor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Picta_TintedImageByHexColor": "Tinted Image By Hex Color",
}
