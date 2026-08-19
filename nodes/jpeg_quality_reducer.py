import io
from PIL import Image
import torch
import numpy as np

class JPEGQualityReducer:
    CATEGORY = "ODDNodes/Image"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("Compressed Image",)
    FUNCTION = "compress_image"
    OUTPUT_IS_LIST = (False,)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "quality": ("INT", {
                    "default": 75,
                    "min": 1,
                    "max": 100
                }),
            }
        }

    def compress_image(self, image, quality):
        # Convert torch tensor to numpy
        image_np = image[0].numpy()
        image_np = (image_np * 255).astype(np.uint8)

        # Convert to PIL Image
        pil_image = Image.fromarray(image_np)

        # Save to buffer as JPEG with specified quality
        buffer = io.BytesIO()
        pil_image.save(buffer, format="JPEG", quality=quality, optimize=True)
        buffer.seek(0)

        # Reload image from buffer
        compressed_image = Image.open(buffer).convert("RGB")
        img_np = np.array(compressed_image).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).unsqueeze(0)

        return (img_tensor,)

NODE_CLASS_MAPPINGS = {
    "ODD_JPEGQualityReducer": JPEGQualityReducer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ODD_JPEGQualityReducer": "JPEG Quality Reducer",
}
