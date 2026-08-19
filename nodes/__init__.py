"""ODDNodes node registry.

Each tool group lives in its own file here (e.g. dataset_qc.py). To add a new
tool group: create a new file with your node class(es), then import it below
and merge its mappings into NODE_CLASS_MAPPINGS / NODE_DISPLAY_NAME_MAPPINGS.
"""

from .dataset_qc import ODD_DatasetFolderBrowser, ODD_SaveIdeogram4Json
from .video_stabilize_nodes import (
    NODE_CLASS_MAPPINGS as _VIDEO_STABILIZE_CLASSES,
    NODE_DISPLAY_NAME_MAPPINGS as _VIDEO_STABILIZE_NAMES,
)
from .tint_nodes import (
    NODE_CLASS_MAPPINGS as _TINT_CLASSES,
    NODE_DISPLAY_NAME_MAPPINGS as _TINT_NAMES,
)
from .save_image_with_structure import (
    NODE_CLASS_MAPPINGS as _SAVE_STRUCTURE_CLASSES,
    NODE_DISPLAY_NAME_MAPPINGS as _SAVE_STRUCTURE_NAMES,
)
from .recursive_image_loader import (
    NODE_CLASS_MAPPINGS as _RECURSIVE_LOADER_CLASSES,
    NODE_DISPLAY_NAME_MAPPINGS as _RECURSIVE_LOADER_NAMES,
)
from .jpeg_quality_reducer import (
    NODE_CLASS_MAPPINGS as _JPEG_REDUCER_CLASSES,
    NODE_DISPLAY_NAME_MAPPINGS as _JPEG_REDUCER_NAMES,
)

NODE_CLASS_MAPPINGS = {
    "ODD_DatasetFolderBrowser": ODD_DatasetFolderBrowser,
    "ODD_SaveIdeogram4Json": ODD_SaveIdeogram4Json,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ODD_DatasetFolderBrowser": "Dataset Folder Browser",
    "ODD_SaveIdeogram4Json": "Save Ideogram 4 JSON",
}

NODE_CLASS_MAPPINGS.update(_VIDEO_STABILIZE_CLASSES)
NODE_DISPLAY_NAME_MAPPINGS.update(_VIDEO_STABILIZE_NAMES)

NODE_CLASS_MAPPINGS.update(_TINT_CLASSES)
NODE_DISPLAY_NAME_MAPPINGS.update(_TINT_NAMES)

NODE_CLASS_MAPPINGS.update(_SAVE_STRUCTURE_CLASSES)
NODE_DISPLAY_NAME_MAPPINGS.update(_SAVE_STRUCTURE_NAMES)

NODE_CLASS_MAPPINGS.update(_RECURSIVE_LOADER_CLASSES)
NODE_DISPLAY_NAME_MAPPINGS.update(_RECURSIVE_LOADER_NAMES)

NODE_CLASS_MAPPINGS.update(_JPEG_REDUCER_CLASSES)
NODE_DISPLAY_NAME_MAPPINGS.update(_JPEG_REDUCER_NAMES)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
