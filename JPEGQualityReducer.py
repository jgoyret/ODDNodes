from PIL import Image
import io
from comfy.nodes.base import ComfyNode

class JPEGQualityReducer(ComfyNode):
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"image": ("IMAGE",), "quality": ("INT",)}}

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "reduce_quality"
    CATEGORY = "Image Processing"

    def reduce_quality(self, image, quality):
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=quality, optimize=True)
        buf.seek(0)
        return (Image.open(buf),)
    
NODE_CLASS_MAPPINGS = {
    "Picta_JPEGQualityReducer": JPEGQualityReducer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Picta_JPEGQualityReducer": "JPEG Quality Reducer",
}