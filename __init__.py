# PictaNodes __init__.py
# Puedes dejarlo vacío si no necesitas lógica al importar
from .tint_nodes import TintedImageByHexColor
from .SaveImageWithStructure import SaveImageWithStructure
from .RecursiveImageLoader import RecursiveImageLoader

NODE_CLASS_MAPPINGS = {
    "Picta_TintedImageByHexColor": TintedImageByHexColor,
    "Picta_SaveImageWithStructure": SaveImageWithStructure,
    "Picta_RecursiveImageLoader": RecursiveImageLoader,

}
