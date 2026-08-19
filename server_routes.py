"""ODDNodes server-side routes.

- /odd_nodes/list_dir  — folder listing for the in-app folder browser modal.
- /odd_nodes/preview   — filename/json/dims for image[index] in a folder, so
  the Dataset Folder Browser node can show a live preview on Prev/Next without
  a graph execution.
- /odd_nodes/image     — streams the raw image bytes for the same lookup.
- /odd_nodes/save_json — writes an edited json_string back to image[index]'s
  sibling .json, from the live preview's Edit/Save controls (no graph
  execution needed).

/odd_nodes/preview reads the sibling .json's content; /odd_nodes/image streams
raw image bytes. All of these only ever operate on the folder_path/index the
client asks for — same trust boundary as every other local-disk ComfyUI node.
"""

import logging
import os
import re
import string

_IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def _natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _clean_path(p):
    return (p or "").strip().strip('"').strip("'")


def _list_drives():
    try:
        return list(os.listdrives())  # Python 3.12+
    except AttributeError:
        drives = []
        for letter in string.ascii_uppercase:
            d = f"{letter}:\\"
            if os.path.exists(d):
                drives.append(d)
        return drives


def _resolve_image(folder_path, index):
    """-> (folder_path, filename, total_count, error)."""
    folder_path = _clean_path(folder_path)
    if not os.path.isdir(folder_path):
        return None, None, 0, f"Folder not found: {folder_path}"
    files = sorted(
        [f for f in os.listdir(folder_path) if f.lower().endswith(_IMG_EXTS)],
        key=_natural_key,
    )
    total = len(files)
    if total == 0:
        return None, None, 0, f"No images found in {folder_path}"
    idx = max(0, min(index, total - 1))
    return folder_path, files[idx], total, None


def register_routes():
    try:
        from server import PromptServer
    except Exception:
        logging.exception("ODDNodes: could not import PromptServer, folder browser route disabled")
        return

    if not hasattr(PromptServer, "instance") or PromptServer.instance is None:
        return
    try:
        if PromptServer.instance.app.router.frozen:
            logging.warning("ODDNodes: router already frozen, skipping route registration")
            return
    except Exception:
        pass

    from aiohttp import web
    from PIL import Image

    from .nodes.dataset_qc import _write_json_string

    routes = PromptServer.instance.routes

    def _get_index(request):
        try:
            return int(request.rel_url.query.get("index", "0"))
        except ValueError:
            return 0

    @routes.get("/odd_nodes/preview")
    async def odd_preview(request):
        folder_path = request.rel_url.query.get("folder_path", "")
        index = _get_index(request)
        folder, fname, total, err = _resolve_image(folder_path, index)
        if err:
            return web.json_response({"error": err}, status=400)

        idx = max(0, min(index, total - 1))
        base = os.path.splitext(fname)[0]
        img_path = os.path.join(folder, fname)
        json_path = os.path.join(folder, base + ".json")

        try:
            with Image.open(img_path) as im:
                width, height = im.size
        except Exception as e:
            return web.json_response({"error": f"Could not read image: {e}"}, status=400)

        has_json = os.path.isfile(json_path)
        json_string = ""
        if has_json:
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    json_string = f.read()
            except Exception as e:
                json_string = f"[ERROR reading JSON: {e}]"

        status = f"{idx + 1}/{total}  —  {fname}  ({width}x{height})"
        if not has_json:
            status += "   [NO JSON YET]"

        return web.json_response({
            "filename": fname,
            "total_count": total,
            "width": width,
            "height": height,
            "json_string": json_string,
            "has_json": has_json,
            "status": status,
        })

    @routes.get("/odd_nodes/image")
    async def odd_image(request):
        folder_path = request.rel_url.query.get("folder_path", "")
        index = _get_index(request)
        folder, fname, total, err = _resolve_image(folder_path, index)
        if err:
            return web.Response(status=404, text=err)
        return web.FileResponse(os.path.join(folder, fname))

    @routes.post("/odd_nodes/save_json")
    async def odd_save_json(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid request body"}, status=400)

        folder_path = body.get("folder_path", "")
        json_string = body.get("json_string", "")
        try:
            index = int(body.get("index", 0))
        except (TypeError, ValueError):
            index = 0

        folder, fname, total, err = _resolve_image(folder_path, index)
        if err:
            return web.json_response({"error": err}, status=400)

        status, error = _write_json_string(folder, fname, json_string)
        if error:
            return web.json_response({"error": error}, status=400)

        return web.json_response({"status": status, "filename": fname})

    @routes.get("/odd_nodes/list_dir")
    async def odd_list_dir(request):
        raw_path = request.rel_url.query.get("path", "").strip()

        if not raw_path:
            return web.json_response({
                "path": "",
                "parent": None,
                "dirs": _list_drives(),
                "root_list": True,
            })

        path = raw_path
        if not os.path.isdir(path):
            return web.json_response({"error": f"Not a directory: {path}"}, status=400)

        try:
            names = []
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            names.append(entry.name)
                    except OSError:
                        continue
            names.sort(key=_natural_key)
        except PermissionError:
            return web.json_response({"error": f"Permission denied: {path}"}, status=403)
        except OSError as e:
            return web.json_response({"error": str(e)}, status=400)

        stripped = path.rstrip("\\/")
        parent = os.path.dirname(stripped)
        if not parent or os.path.normpath(parent) == os.path.normpath(path):
            parent = ""  # drive root's parent -> back to the drive list

        return web.json_response({
            "path": path,
            "parent": parent,
            "dirs": names,
            "root_list": False,
        })

    logging.info(
        "ODDNodes: registered /odd_nodes/list_dir, /odd_nodes/preview, "
        "/odd_nodes/image, /odd_nodes/save_json"
    )
