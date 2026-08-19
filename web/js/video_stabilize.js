// ODDNodes / Video Stabilize — método "Warp automático" no necesita nada
// especial. Método "Point Lock" deja click/arrastrar el/los punto(s) ancla
// sobre el preview del propio nodo. Flujo: encolá una vez para que el nodo
// renderice el frame 0 como preview, después clickeá para ubicar P1 (y P2 en
// modo de 2 puntos) y arrastrá para ajustar. Las coordenadas se escriben en
// el widget STRING oculto "points", que es lo que viaja a Python.
const { app } = window.comfyAPI.app;

const METHOD_WARP = "Warp automático (shake de cámara)";
const METHOD_ONE_POINT = "Point Lock — 1 punto (traslación)";

const WARP_ONLY_WIDGETS = ["smoothness", "max_rotation_correction_deg"];
const POINT_LOCK_WIDGETS = ["track_window", "search_radius", "match_confidence", "point_lock_smoothing"];

// Standard trick to hide a widget while keeping it live/serialized: give it
// zero layout height instead of removing it from node.widgets.
function hideWidget(node, name, hidden) {
  const w = node.widgets?.find((x) => x.name === name);
  if (!w) return;
  if (w.__oddOrigComputeSize === undefined) w.__oddOrigComputeSize = w.computeSize;
  w.computeSize = hidden ? () => [0, -4] : w.__oddOrigComputeSize;
}

function currentMethod(node) {
  return node.widgets?.find((w) => w.name === "method")?.value;
}

function pointsNeeded(node) {
  return currentMethod(node) === METHOD_ONE_POINT ? 1 : 2;
}

function applyVisibility(node) {
  const method = currentMethod(node);
  const isPointLock = method !== METHOD_WARP;

  WARP_ONLY_WIDGETS.forEach((name) => hideWidget(node, name, isPointLock));
  POINT_LOCK_WIDGETS.forEach((name) => hideWidget(node, name, !isPointLock));
  hideWidget(node, "points", true); // siempre oculto: lo escribe el picker, no se tipea a mano

  // correct_rotation / correct_scale no aplican al modo de 1 punto (solo traslación).
  const rotScaleRelevant = method !== METHOD_ONE_POINT;
  hideWidget(node, "correct_rotation", !rotScaleRelevant);
  hideWidget(node, "correct_scale", !rotScaleRelevant);

  node._videoStabilizePicker?.setVisible(isPointLock);
  node.setSize?.(node.computeSize());
  node.graph?.setDirtyCanvas?.(true, true);
}

function buildPointPicker(node) {
  const wrap = document.createElement("div");
  wrap.style.cssText = "display:flex;flex-direction:column;gap:4px;width:100%;";

  const hint = document.createElement("div");
  hint.style.cssText = "font-size:10px;opacity:0.7;";
  hint.textContent = "Encolá una vez para cargar el preview, después clickeá/arrastrá los puntos acá.";

  const canvasWrap = document.createElement("div");
  canvasWrap.style.cssText =
    "position:relative;width:100%;background:#111;border-radius:4px;overflow:hidden;";

  const canvas = document.createElement("canvas");
  canvas.style.cssText = "width:100%;height:auto;display:none;cursor:crosshair;";

  const emptyMsg = document.createElement("div");
  emptyMsg.textContent = "(sin preview todavía — encolá el nodo una vez)";
  emptyMsg.style.cssText = "padding:24px 8px;text-align:center;opacity:0.5;font-size:11px;";

  canvasWrap.appendChild(canvas);
  canvasWrap.appendChild(emptyMsg);

  const btnRow = document.createElement("div");
  btnRow.style.cssText = "display:flex;gap:6px;justify-content:flex-end;";
  const clearBtn = document.createElement("button");
  clearBtn.textContent = "Borrar puntos";
  clearBtn.style.cssText =
    "padding:4px 10px;cursor:pointer;font-size:11px;border-radius:4px;" +
    "border:1px solid #444;background:#2a2a2a;color:#ddd;";
  btnRow.appendChild(clearBtn);

  wrap.appendChild(hint);
  wrap.appendChild(canvasWrap);
  wrap.appendChild(btnRow);

  node.addDOMWidget("pointlock_picker", "div", wrap, { serialize: false });

  const state = {
    img: null,
    naturalW: 0,
    naturalH: 0,
    pts: [], // {x,y} en espacio de píxeles de la imagen original
    dragIdx: -1,
  };
  const palette = ["#ff3c3c", "#3cc8ff"];

  function pointsWidget() {
    return node.widgets?.find((w) => w.name === "points");
  }

  function commitPoints() {
    const w = pointsWidget();
    if (w) {
      w.value = JSON.stringify(state.pts.map((p) => [Math.round(p.x), Math.round(p.y)]));
    }
    node.graph?.setDirtyCanvas?.(true, true);
  }

  function loadFromWidget() {
    const w = pointsWidget();
    if (!w?.value) {
      state.pts = [];
      return;
    }
    try {
      const parsed = JSON.parse(w.value);
      state.pts = Array.isArray(parsed)
        ? parsed
            .filter((p) => Array.isArray(p) && p.length === 2)
            .map((p) => ({ x: Number(p[0]), y: Number(p[1]) }))
        : [];
    } catch (e) {
      state.pts = [];
    }
  }

  function redraw() {
    if (!state.img) return;
    const ctx = canvas.getContext("2d");
    canvas.width = state.naturalW;
    canvas.height = state.naturalH;
    ctx.drawImage(state.img, 0, 0);

    const needed = pointsNeeded(node);
    const size = Math.max(8, state.naturalW * 0.012);
    state.pts.slice(0, needed).forEach((p, idx) => {
      const color = palette[idx % palette.length];
      ctx.strokeStyle = color;
      ctx.lineWidth = Math.max(2, state.naturalW * 0.002);
      ctx.beginPath();
      ctx.moveTo(p.x - size, p.y);
      ctx.lineTo(p.x + size, p.y);
      ctx.moveTo(p.x, p.y - size);
      ctx.lineTo(p.x, p.y + size);
      ctx.arc(p.x, p.y, size, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = color;
      ctx.font = `${Math.max(12, state.naturalW * 0.018)}px sans-serif`;
      ctx.fillText(String(idx + 1), p.x + size + 3, p.y - size - 3);
    });
  }

  function canvasToImage(evt) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((evt.clientX - rect.left) * state.naturalW) / rect.width,
      y: ((evt.clientY - rect.top) * state.naturalH) / rect.height,
    };
  }

  function nearestPointIdx(p, maxDist) {
    let best = -1;
    let bestDist = maxDist;
    state.pts.forEach((q, idx) => {
      const d = Math.hypot(p.x - q.x, p.y - q.y);
      if (d < bestDist) {
        bestDist = d;
        best = idx;
      }
    });
    return best;
  }

  canvas.addEventListener("mousedown", (evt) => {
    if (!state.img) return;
    const p = canvasToImage(evt);
    const needed = pointsNeeded(node);
    const hit = nearestPointIdx(p, state.naturalW * 0.03);
    if (hit >= 0) {
      state.dragIdx = hit;
    } else if (state.pts.length < needed) {
      state.pts.push(p);
      state.dragIdx = state.pts.length - 1;
    } else {
      // ya están los puntos que hacen falta: reubica el más cercano
      state.dragIdx = nearestPointIdx(p, Infinity);
      if (state.dragIdx >= 0) state.pts[state.dragIdx] = p;
    }
    redraw();
    evt.preventDefault();
  });

  canvas.addEventListener("mousemove", (evt) => {
    if (state.dragIdx < 0) return;
    state.pts[state.dragIdx] = canvasToImage(evt);
    redraw();
  });

  const endDrag = () => {
    if (state.dragIdx < 0) return;
    state.dragIdx = -1;
    commitPoints();
  };
  canvas.addEventListener("mouseup", endDrag);
  canvas.addEventListener("mouseleave", endDrag);

  clearBtn.onclick = () => {
    state.pts = [];
    redraw();
    commitPoints();
  };

  function setImage(src, w, h) {
    const img = new Image();
    img.onload = () => {
      state.img = img;
      state.naturalW = w || img.naturalWidth;
      state.naturalH = h || img.naturalHeight;
      canvas.style.display = "block";
      emptyMsg.style.display = "none";
      loadFromWidget(); // vuelve a leer el widget: fuente de verdad única
      redraw();
    };
    img.src = src;
  }

  function setVisible(visible) {
    wrap.style.display = visible ? "flex" : "none";
  }

  return { setImage, redraw, setVisible };
}

app.registerExtension({
  name: "ODDNodes.VideoStabilize",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "ODD_VideoStabilize") return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);
      const node = this;

      const picker = buildPointPicker(node);
      node._videoStabilizePicker = picker;

      const methodW = node.widgets?.find((w) => w.name === "method");
      if (methodW) {
        const orig = methodW.callback;
        methodW.callback = function (...args) {
          orig?.apply(this, args);
          applyVisibility(node);
          picker.redraw();
        };
      }

      applyVisibility(node);
    };

    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      onExecuted?.apply(this, arguments);
      const img = message?.images?.[0];
      if (!img) return;
      const url =
        "/view?filename=" + encodeURIComponent(img.filename) +
        "&subfolder=" + encodeURIComponent(img.subfolder || "") +
        "&type=" + encodeURIComponent(img.type || "temp") +
        "&_t=" + Date.now();
      this._videoStabilizePicker?.setImage(url);
    };
  },
});
