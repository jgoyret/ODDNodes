# ODDNodes

A grab-bag of custom nodes for ComfyUI. No grand plan or curation — these are
nodes I write as I hit specific needs while using ComfyUI myself. Quality and
scope vary from node to node.

All nodes are prefixed with `ODD_`, so search for `ODD_` in the ComfyUI node
picker to find them all.

## Nodes

| Node | Description |
| --- | --- |
| **Video Stabilize** | Stabilizes a video clip. Two methods: automatic warp (smooths camera shake while keeping real pans/dollies) or Point Lock (pins a hand-picked point to its frame-0 position). |
| **Dataset Folder Browser** | Steps through a folder of image + sibling JSON pairs, one at a time, for dataset review/cleanup. Built mainly for Ideogram 4 caption datasets. |
| **Save Ideogram 4 JSON** | Writes an edited JSON string back to its source file, with a one-time backup of the original. |
| **Tinted Image By Hex Color** | Blends an image with a solid hex color at a given intensity. |
| **Save Image With Structure** | Saves images to an output folder, mirroring the relative path of their original input files. |
| **Recursive Image Loader** | Loads all images under a folder (recursively) as a batch, along with their file paths. |
| **JPEG Quality Reducer** | Re-encodes an image through JPEG at a given quality to simulate compression artifacts. |
