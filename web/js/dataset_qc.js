// ODDNodes / Dataset QC — adds Prev/Next buttons + a folder-browser modal to
// the Dataset Folder Browser node (all client-side, no auto-queue), and a
// live status readout on both the Browser and Saver nodes after execution.
const { app } = window.comfyAPI.app;

function addStatusReadout(nodeType) {
  const onExecuted = nodeType.prototype.onExecuted;
  nodeType.prototype.onExecuted = function (message) {
    onExecuted?.apply(this, arguments);
    const text = message?.text?.[0];
    if (text == null) return;
    if (!this._qcStatusWidget) {
      this._qcStatusWidget = this.addWidget("text", "status", "", () => {});
      this._qcStatusWidget.disabled = true;
    }
    this._qcStatusWidget.value = text;
    this.graph?.setDirtyCanvas(true, true);
  };
}

// Find Ideogram4PromptBuilderKJ nodes wired to any of this node's outputs
// named in `outNames` (e.g. ["width","height"] or ["image"]).
function findConnectedPromptBuilders(node, outNames) {
  const graph = node.graph;
  if (!graph) return [];
  const outs = (node.outputs || []).filter((o) => outNames.includes(o.name));
  const targetIds = new Set();
  for (const out of outs) {
    for (const linkId of out.links || []) {
      const link = graph.links?.[linkId];
      if (link) targetIds.add(link.target_id);
    }
  }
  const targets = [];
  for (const id of targetIds) {
    const t = graph.getNodeById ? graph.getNodeById(id) : null;
    if (t && t.type === "Ideogram4PromptBuilderKJ") targets.push(t);
  }
  return targets;
}

// Workaround for a comfyui-kjnodes quirk: Ideogram4PromptBuilderKJ's width/height
// are plain (non force_input) widgets, so wiring a link into them updates what's
// actually used internally, but NOT the widget's own displayed number. Force it
// here so the on-screen value always matches the connected image.
function syncDownstreamDims(node, width, height) {
  if (width == null || height == null || !width || !height) return;
  try {
    for (const t of findConnectedPromptBuilders(node, ["width", "height"])) {
      const wW = t.widgets?.find((w) => w.name === "width");
      const hW = t.widgets?.find((w) => w.name === "height");
      if (wW && wW.value !== width) {
        wW.value = width;
        wW.callback?.(width);
      }
      if (hW && hW.value !== height) {
        hW.value = height;
        hW.callback?.(height);
      }
    }
    node.graph?.setDirtyCanvas?.(true, true);
  } catch (e) {
    console.warn("ODDNodes: syncDownstreamDims failed", e);
  }
}

// Workaround for another comfyui-kjnodes quirk: the editor's background-image
// auto-refresh (watchImageInputs) only reacts when the upstream node has a
// widget literally named "image" (like stock LoadImage's dropdown) — our
// Browser has no such widget, so it's never detected. Trigger the node's own
// "Grab BG" hook directly instead. It reads the shared `lastResultImage`,
// which kjnodes' own code sets from the "executed" websocket event — give
// that a moment to land first (kjnodes uses the same 100ms grace period
// internally for its own reactive updates).
function refreshDownstreamBackground(node) {
  setTimeout(() => {
    for (const t of findConnectedPromptBuilders(node, ["image"])) {
      try {
        t._grabResultBg?.();
      } catch (e) {
        console.warn("ODDNodes: _grabResultBg failed", e);
      }
    }
  }, 120);
}

function mkEditBtn(label) {
  const b = document.createElement("button");
  b.textContent = label;
  b.style.cssText =
    "padding:4px 12px;cursor:pointer;font-size:11px;border-radius:4px;" +
    "border:1px solid #444;background:#2a2a2a;color:#ddd;";
  return b;
}

// Builds the on-node live preview (image + editable JSON textarea with
// Edit/Save/Cancel controls), and returns a refresh(folderPath, index) that
// fetches /odd_nodes/preview + /odd_nodes/image and updates them — pure
// client-side, no graph execution (Save posts to /odd_nodes/save_json).
function buildLivePreview(node) {
  const wrap = document.createElement("div");
  wrap.style.cssText = "display:flex;flex-direction:column;gap:4px;width:100%;";

  const img = document.createElement("img");
  img.style.cssText =
    "width:100%;max-height:260px;object-fit:contain;background:#111;border-radius:4px;display:none;";

  const errBox = document.createElement("div");
  errBox.style.cssText = "color:#f77;font-size:11px;padding:4px;display:none;";

  const textarea = document.createElement("textarea");
  textarea.readOnly = true;
  textarea.spellcheck = false;
  textarea.placeholder = "(no JSON yet for this image)";
  textarea.style.cssText =
    "width:100%;height:160px;resize:vertical;font-family:monospace;font-size:10px;" +
    "background:#161616;color:#ccc;border:1px solid #333;border-radius:4px;padding:6px;box-sizing:border-box;";

  const editRow = document.createElement("div");
  editRow.style.cssText = "display:flex;gap:6px;justify-content:flex-end;";
  const editBtn = mkEditBtn("Edit");
  const cancelBtn = mkEditBtn("Cancel");
  const saveBtn = mkEditBtn("Save");
  cancelBtn.style.display = "none";
  saveBtn.style.display = "none";
  editRow.appendChild(editBtn);
  editRow.appendChild(cancelBtn);
  editRow.appendChild(saveBtn);

  wrap.appendChild(img);
  wrap.appendChild(errBox);
  wrap.appendChild(textarea);
  wrap.appendChild(editRow);
  node.addDOMWidget("qc_live_preview", "div", wrap, { serialize: false });

  // Nav widgets get locked while editing so Prev/Next/Browse can't blow away
  // an in-progress, unsaved edit.
  const navWidgetNames = ["📁 Browse…", "◀ Prev", "▶ Next", "folder_path", "index"];
  function setNavLocked(locked) {
    for (const name of navWidgetNames) {
      const w = node.widgets?.find((x) => x.name === name);
      if (w) w.disabled = locked;
    }
  }

  let originalText = "";
  let editing = false;

  function setEditing(isEditing) {
    editing = isEditing;
    textarea.readOnly = !isEditing;
    textarea.style.background = isEditing ? "#1c1c1c" : "#161616";
    textarea.style.borderColor = isEditing ? "#6a6" : "#333";
    editBtn.style.display = isEditing ? "none" : "inline-block";
    cancelBtn.style.display = isEditing ? "inline-block" : "none";
    saveBtn.style.display = isEditing ? "inline-block" : "none";
    setNavLocked(isEditing);
    node.graph?.setDirtyCanvas?.(true, true);
  }

  editBtn.onclick = () => {
    originalText = textarea.value;
    setEditing(true);
    textarea.focus();
  };

  cancelBtn.onclick = () => {
    textarea.value = originalText;
    errBox.style.display = "none";
    setEditing(false);
  };

  saveBtn.onclick = async () => {
    saveBtn.disabled = true;
    cancelBtn.disabled = true;
    const folderW = node.widgets?.find((w) => w.name === "folder_path");
    const indexW = node.widgets?.find((w) => w.name === "index");
    try {
      const res = await fetch("/odd_nodes/save_json", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          folder_path: folderW?.value || "",
          index: indexW?.value ?? 0,
          json_string: textarea.value,
        }),
      });
      const data = await res.json();
      if (!res.ok || data.error) {
        errBox.textContent = data.error || "Save failed";
        errBox.style.display = "block";
        return; // stay in edit mode so the user can fix and retry
      }
      errBox.style.display = "none";
      setEditing(false);
      await refresh(folderW?.value || "", indexW?.value ?? 0); // reload normalized JSON from disk
    } catch (e) {
      errBox.textContent = "Save failed: " + e;
      errBox.style.display = "block";
    } finally {
      saveBtn.disabled = false;
      cancelBtn.disabled = false;
    }
  };

  let seq = 0; // discard stale responses if Prev/Next is spammed
  async function refresh(folderPath, index) {
    const mySeq = ++seq;
    errBox.style.display = "none";
    if (editing) setEditing(false); // navigating away discards any unsaved edit
    let data;
    try {
      const url =
        "/odd_nodes/preview?folder_path=" + encodeURIComponent(folderPath || "") +
        "&index=" + encodeURIComponent(index ?? 0) + "&_t=" + Date.now();
      const res = await fetch(url);
      data = await res.json();
    } catch (e) {
      if (mySeq !== seq) return;
      img.style.display = "none";
      errBox.textContent = "Preview fetch failed: " + e;
      errBox.style.display = "block";
      return;
    }
    if (mySeq !== seq) return; // a newer request already landed

    if (data.error) {
      img.style.display = "none";
      textarea.value = "";
      errBox.textContent = data.error;
      errBox.style.display = "block";
      updateStatus(node, data.error);
      return;
    }

    img.src =
      "/odd_nodes/image?folder_path=" + encodeURIComponent(folderPath || "") +
      "&index=" + encodeURIComponent(index ?? 0) + "&_t=" + Date.now();
    img.style.display = "block";
    textarea.value = data.json_string || "";
    updateStatus(node, data.status);
    node.graph?.setDirtyCanvas?.(true, true);
  }

  return refresh;
}

function updateStatus(node, text) {
  if (text == null) return;
  if (!node._qcStatusWidget) {
    node._qcStatusWidget = node.addWidget("text", "status", "", () => {});
    node._qcStatusWidget.disabled = true;
  }
  node._qcStatusWidget.value = text;
}

async function listDir(path) {
  const res = await fetch("/odd_nodes/list_dir?path=" + encodeURIComponent(path || ""));
  return res.json();
}

function joinPath(base, name) {
  const b = (base || "").replace(/[\\/]+$/, "");
  return b ? b + "\\" + name : name;
}

// Simple modal folder browser (double-click to enter a folder, Up to go back,
// Select to accept). Not a native OS dialog — see chat for why.
function openFolderBrowser(startPath, onSelect) {
  const overlay = document.createElement("div");
  overlay.style.cssText =
    "position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:10000;" +
    "display:flex;align-items:center;justify-content:center;";

  const panel = document.createElement("div");
  panel.style.cssText =
    "background:#202020;color:#ddd;border-radius:8px;padding:16px;width:560px;" +
    "max-height:72vh;display:flex;flex-direction:column;" +
    "font-family:sans-serif;font-size:13px;box-shadow:0 8px 30px rgba(0,0,0,0.6);";

  const title = document.createElement("div");
  title.textContent = "Choose a folder";
  title.style.cssText = "font-weight:600;margin-bottom:8px;";

  const pathLabel = document.createElement("div");
  pathLabel.style.cssText =
    "margin-bottom:8px;word-break:break-all;opacity:0.85;background:#161616;" +
    "padding:6px 8px;border-radius:4px;min-height:1.4em;";

  const list = document.createElement("div");
  list.style.cssText =
    "flex:1;overflow-y:auto;border:1px solid #444;border-radius:4px;margin-bottom:10px;min-height:200px;";

  const btnRow = document.createElement("div");
  btnRow.style.cssText = "display:flex;gap:8px;justify-content:flex-end;";

  const mkBtn = (label) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.style.cssText = "padding:6px 12px;cursor:pointer;";
    return b;
  };
  const upBtn = mkBtn("⬆ Up");
  const selectBtn = mkBtn("Select this folder");
  const cancelBtn = mkBtn("Cancel");

  const state = { path: "", parent: null };

  async function refresh(path) {
    list.innerHTML = '<div style="padding:8px;opacity:0.6;">Loading…</div>';
    let data;
    try {
      data = await listDir(path);
    } catch (e) {
      list.innerHTML = `<div style="padding:8px;color:#f77;">${e}</div>`;
      return;
    }
    if (data.error) {
      list.innerHTML = `<div style="padding:8px;color:#f77;">${data.error}</div>`;
      pathLabel.textContent = path || "";
      return;
    }
    state.path = data.path;
    state.parent = data.parent;
    pathLabel.textContent = data.root_list ? "This PC" : data.path;
    upBtn.disabled = data.root_list;
    selectBtn.disabled = data.root_list;
    list.innerHTML = "";
    if (!data.dirs.length) {
      list.innerHTML = '<div style="padding:8px;opacity:0.6;">(no subfolders)</div>';
    }
    for (const name of data.dirs) {
      const row = document.createElement("div");
      row.textContent = "📁 " + name;
      row.style.cssText = "padding:6px 10px;cursor:pointer;";
      row.onmouseenter = () => (row.style.background = "#333");
      row.onmouseleave = () => (row.style.background = "");
      row.ondblclick = () => {
        const next = data.root_list ? name : joinPath(data.path, name);
        refresh(next);
      };
      list.appendChild(row);
    }
  }

  upBtn.onclick = () => refresh(state.parent ?? "");
  cancelBtn.onclick = () => overlay.remove();
  selectBtn.onclick = () => {
    onSelect(state.path);
    overlay.remove();
  };
  overlay.onclick = (e) => {
    if (e.target === overlay) overlay.remove();
  };
  document.addEventListener("keydown", function esc(e) {
    if (e.key === "Escape") {
      overlay.remove();
      document.removeEventListener("keydown", esc);
    }
  });

  panel.appendChild(title);
  panel.appendChild(pathLabel);
  panel.appendChild(list);
  btnRow.appendChild(upBtn);
  btnRow.appendChild(cancelBtn);
  btnRow.appendChild(selectBtn);
  panel.appendChild(btnRow);
  overlay.appendChild(panel);
  document.body.appendChild(overlay);

  refresh(startPath || "");
}

app.registerExtension({
  name: "ODDNodes.DatasetQC",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name === "ODD_SaveIdeogram4Json") {
      addStatusReadout(nodeType);
      return;
    }
    if (nodeData.name !== "ODD_DatasetFolderBrowser") return;

    addStatusReadout(nodeType);

    const onExecutedDims = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      onExecutedDims?.apply(this, arguments);
      const w = message?.width?.[0];
      const h = message?.height?.[0];
      syncDownstreamDims(this, w, h);
      refreshDownstreamBackground(this);
    };

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const node = this;

      let refreshLive = null;
      const doRefresh = () => {
        if (!refreshLive) return;
        const folderW = node.widgets?.find((w) => w.name === "folder_path");
        const indexW = node.widgets?.find((w) => w.name === "index");
        refreshLive(folderW?.value || "", indexW?.value ?? 0);
      };

      const step = (delta) => {
        const w = node.widgets?.find((x) => x.name === "index");
        if (!w) return;
        const min = w.options?.min ?? 0;
        const max = w.options?.max ?? 999999;
        const v = Math.max(min, Math.min(max, (w.value ?? 0) + delta));
        w.value = v;
        w.callback?.(v);
        node.graph?.setDirtyCanvas(true, true);
        doRefresh();
      };

      node.addWidget("button", "📁 Browse…", null, () => {
        const folderWidget = node.widgets?.find((w) => w.name === "folder_path");
        openFolderBrowser(folderWidget?.value || "", (chosen) => {
          if (!folderWidget) return;
          folderWidget.value = chosen;
          folderWidget.callback?.(chosen);
          node.graph?.setDirtyCanvas(true, true);
          doRefresh();
        });
      });
      node.addWidget("button", "◀ Prev", null, () => step(-1));
      node.addWidget("button", "▶ Next", null, () => step(1));

      refreshLive = buildLivePreview(node); // added after the buttons so it renders below them

      // Also refresh on a direct edit of folder_path / index (typing, or the
      // widget's own +/- arrows), not just the custom Prev/Next buttons.
      for (const name of ["folder_path", "index"]) {
        const w = node.widgets?.find((x) => x.name === name);
        if (!w) continue;
        const orig = w.callback;
        w.callback = function (...args) {
          orig?.apply(this, args);
          doRefresh();
        };
      }

      // Initial preview if the node already has a folder_path (e.g. loading a
      // saved workflow) — skip on a freshly-added blank node.
      setTimeout(() => {
        const folderW = node.widgets?.find((w) => w.name === "folder_path");
        if (folderW?.value) doRefresh();
      }, 0);
    };
  },
});
