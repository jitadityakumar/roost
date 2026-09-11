import { useCallback, useEffect, useRef, useState } from "react";
import {
  COLOR_PALETTE,
  ROOM_TYPES,
  centroid,
  dist,
  parseLength,
  pointInPoly,
  polyArea,
  rectToPoints,
  shadeColor,
  sqftOf,
} from "./floorplanGeometry.js";

// React/canvas port of ~/claude/local-apps/house-tracker/floorplan-tool's
// index.html -- same mechanics (state.rooms/shapes/activeScale, canvas draw
// loop, calibration, rect/polygon drawing) reimplemented with React state +
// a canvas ref rather than global state + direct DOM manipulation.
//
// High-frequency interaction state (pan/zoom view transform, in-progress
// draw/poly/calibration points) lives in refs, not React state -- redrawn
// imperatively via draw() -- so a mousemove during panning/drawing doesn't
// trigger a React re-render per pixel. Room/shape data lives in React state
// since the sidebar needs to reactively reflect it.
//
// Props:
//   imageSrc: string -- <img> src (data: URI or a URL), fixed for the
//     lifetime of this mount (changing it is the parent's job, e.g. Admin's
//     "change baseline image" flow, which should remount this component).
//   initialRooms/initialShapes/initialScale: seed state.
//   onSave(payload): called with { rooms, shapes, activeScale, imageW, imageH }.
//   saving: disables the Save button while a save is in flight.
export default function FloorplanTracer({ imageSrc, initialRooms, initialShapes, initialScale, onSave, saving }) {
  const canvasRef = useRef(null);
  const wrapRef = useRef(null);
  const imgRef = useRef(null);
  const viewRef = useRef({ scale: 1, ox: 0, oy: 0, fitScale: 1 });
  const transientRef = useRef({
    drawStart: null, drawPreview: null,
    polyPoints: null, polyPreview: null,
    calPoints: null,
    panning: false, panStart: null, spaceDown: false,
  });

  const [imgLoaded, setImgLoaded] = useState(false);
  const [imgDims, setImgDims] = useState({ w: 0, h: 0 });
  const [rooms, setRooms] = useState(initialRooms || []);
  const [shapes, setShapes] = useState(initialShapes || []);
  const [activeScale, setActiveScale] = useState(initialScale ?? null);
  const [activeRoomId, setActiveRoomId] = useState((initialRooms && initialRooms[0]?.id) || null);
  const [tool, setToolState] = useState("select");
  const [selectedShapeId, setSelectedShapeId] = useState(null);
  const [zoomPct, setZoomPct] = useState(100);
  const [toast, setToastMsg] = useState(null);
  const [calModalOpen, setCalModalOpen] = useState(false);
  const [calInput, setCalInput] = useState("");
  const [colorPopoverRoomId, setColorPopoverRoomId] = useState(null);
  const [colorPopoverPos, setColorPopoverPos] = useState({ top: 0, left: 0 });

  // Always-fresh mirror of the state the imperative draw()/mouse handlers
  // need, so listeners attached once (empty-deps effects) never read stale
  // closures.
  const stateRef = useRef(null);
  stateRef.current = { rooms, shapes, activeScale, activeRoomId, tool, selectedShapeId };

  const toastTimersRef = useRef(new Set());
  const toast_ = useCallback((msg) => {
    setToastMsg(msg);
    const id = setTimeout(() => {
      toastTimersRef.current.delete(id);
      setToastMsg((cur) => (cur === msg ? null : cur));
    }, 2200);
    toastTimersRef.current.add(id);
  }, []);

  useEffect(() => {
    const timers = toastTimersRef.current;
    return () => {
      timers.forEach(clearTimeout);
      timers.clear();
    };
  }, []);

  // ---------- view transform ----------
  const toImage = useCallback((sx, sy) => {
    const cv = canvasRef.current;
    const rect = cv.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const px = (sx - rect.left) * dpr, py = (sy - rect.top) * dpr;
    const v = viewRef.current;
    return { x: (px - v.ox) / v.scale, y: (py - v.oy) / v.scale };
  }, []);

  const toScreen = useCallback((ix, iy) => {
    const v = viewRef.current;
    return { x: ix * v.scale + v.ox, y: iy * v.scale + v.oy };
  }, []);

  const fitToContainer = useCallback(() => {
    const cv = canvasRef.current, wrap = wrapRef.current;
    if (!cv || !wrap) return;
    const r = wrap.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    cv.width = r.width * dpr; cv.height = r.height * dpr;
    cv.style.width = r.width + "px"; cv.style.height = r.height + "px";
    if (!imgDims.w) return;
    const fit = Math.min((r.width * dpr) / imgDims.w, (r.height * dpr) / imgDims.h) * 0.94;
    viewRef.current.fitScale = fit;
    viewRef.current.scale = fit;
    viewRef.current.ox = (r.width * dpr - imgDims.w * fit) / 2;
    viewRef.current.oy = (r.height * dpr - imgDims.h * fit) / 2;
    setZoomPct(100);
  }, [imgDims]);

  // ---------- drawing ----------
  const roundRect = (ctx, x, y, w, h, r) => {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  };

  const drawShapePath = (ctx, pts, color, selected, previewOnly) => {
    const v = viewRef.current;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
    ctx.closePath();
    ctx.fillStyle = color + (previewOnly ? "33" : "2b");
    ctx.fill();
    ctx.lineWidth = (selected ? 3.5 : 2) / v.scale;
    ctx.strokeStyle = selected ? "#1d2725" : color;
    ctx.setLineDash(previewOnly ? [6 / v.scale, 4 / v.scale] : []);
    ctx.stroke();
    ctx.setLineDash([]);
  };

  const drawLabel = (ctx, x, y, text, color, selected) => {
    ctx.font = "600 11px -apple-system, sans-serif";
    const padX = 6, padY = 4;
    const w = ctx.measureText(text).width + padX * 2;
    ctx.fillStyle = "#fff";
    ctx.strokeStyle = color;
    ctx.lineWidth = selected ? 2 : 1;
    roundRect(ctx, x - w / 2, y - 9, w, 18, 5);
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = "#1d2725";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(text, x, y + 1);
    void padY;
  };

  const roomColorOrDefault = () => {
    const s = stateRef.current;
    const r = s.rooms.find((x) => x.id === s.activeRoomId);
    return r ? r.color : "#2e7d6b";
  };

  const draw = useCallback(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    // jsdom (unit tests) has no real canvas backend and returns null here --
    // a real browser always gives a context, so this is a test-env guard,
    // not something that should ever trip in production.
    if (!ctx) return;
    const v = viewRef.current;
    const s = stateRef.current;
    const t = transientRef.current;

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, cv.width, cv.height);
    if (!imgRef.current) return;

    ctx.setTransform(v.scale, 0, 0, v.scale, v.ox, v.oy);
    // Rightmove floorplan PNGs have a transparent background -- an
    // explicit white fill avoids black-on-black in dark mode (same fix as
    // PR #77's CSS background on <img> paths, reproduced here for canvas).
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, imgDims.w, imgDims.h);
    ctx.drawImage(imgRef.current, 0, 0);

    for (const shape of s.shapes) {
      const room = s.rooms.find((r) => r.id === shape.roomId);
      const color = room ? room.color : "#888";
      drawShapePath(ctx, shape.points, color, shape.id === s.selectedShapeId, false);
    }

    if (s.tool === "rect" && t.drawPreview) {
      drawShapePath(ctx, rectToPoints(t.drawPreview), roomColorOrDefault(), false, true);
    }
    if (s.tool === "poly" && t.polyPoints && t.polyPoints.length) {
      const pts = t.polyPreview ? t.polyPoints.concat([t.polyPreview]) : t.polyPoints;
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
      ctx.strokeStyle = roomColorOrDefault();
      ctx.lineWidth = 2 / v.scale;
      ctx.setLineDash([6 / v.scale, 4 / v.scale]);
      ctx.stroke();
      ctx.setLineDash([]);
      for (const p of t.polyPoints) {
        ctx.beginPath(); ctx.arc(p.x, p.y, 4 / v.scale, 0, 7);
        ctx.fillStyle = "#fff"; ctx.fill(); ctx.lineWidth = 1.5 / v.scale;
        ctx.strokeStyle = roomColorOrDefault(); ctx.stroke();
      }
    }
    if (s.tool === "calibrate" && t.calPoints && t.calPoints.length) {
      const pts = t.calPoints;
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      const end = pts[1] || t.polyPreview;
      if (end) ctx.lineTo(end.x, end.y);
      ctx.strokeStyle = "#a8631c";
      ctx.lineWidth = 2.5 / v.scale;
      ctx.stroke();
    }

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    for (const shape of s.shapes) {
      const room = s.rooms.find((r) => r.id === shape.roomId);
      const c = centroid(shape.points);
      const scr = toScreen(c.x, c.y);
      const sqft = sqftOf(shape);
      const label = (room ? room.name : "?") + (sqft != null ? "  " + sqft.toFixed(1) + " sf" : "  (no scale)");
      drawLabel(ctx, scr.x, scr.y, label, room ? room.color : "#888", shape.id === s.selectedShapeId);
    }
  }, [imgDims, toScreen]);

  // ---------- image load ----------
  useEffect(() => {
    if (!imageSrc) return;
    setImgLoaded(false);
    const im = new Image();
    im.onload = () => {
      imgRef.current = im;
      setImgDims({ w: im.naturalWidth, h: im.naturalHeight });
      setImgLoaded(true);
    };
    im.onerror = () => toast_("Could not load the floor plan image");
    im.src = imageSrc;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imageSrc]);

  useEffect(() => {
    if (!imgLoaded) return;
    fitToContainer();
    draw();
  }, [imgLoaded, fitToContainer, draw]);

  useEffect(() => {
    draw();
  }, [rooms, shapes, activeScale, selectedShapeId, tool, draw]);

  // fitToContainer/draw are recreated (useCallback deps change) once imgDims
  // is known -- keep a ref to the latest versions so this mount-once
  // listener never calls a stale pre-image-load closure (which would bail
  // out on imgDims.w === 0 and leave the view transform stuck uninitialized
  // after a resize).
  const resizeHandlersRef = useRef({ fitToContainer, draw });
  resizeHandlersRef.current = { fitToContainer, draw };

  useEffect(() => {
    function onResize() {
      resizeHandlersRef.current.fitToContainer();
      resizeHandlersRef.current.draw();
    }
    window.addEventListener("resize", onResize);
    const wrap = wrapRef.current;
    let ro;
    if (wrap && "ResizeObserver" in window) {
      ro = new ResizeObserver(onResize);
      ro.observe(wrap);
    }
    return () => {
      window.removeEventListener("resize", onResize);
      if (ro) ro.disconnect();
    };
  }, []);

  // ---------- rooms ----------
  function addRoomOfType(type) {
    const def = ROOM_TYPES[type];
    if (!def) return;
    // Computed from the outer `rooms` (not inside the setRooms updater,
    // which React/StrictMode may invoke more than once) so the new room's
    // id/name/color are generated exactly once per click.
    const existingOfType = rooms.filter((r) => r.type === type).length;
    const name = `${def.label} ${existingOfType + 1}`;
    const color = shadeColor(def.color, existingOfType);
    const id = "r" + Date.now() + Math.floor(Math.random() * 999);
    const room = { id, name, color, type };
    setRooms((prev) => [...prev, room]);
    setActiveRoomId(room.id);
  }

  function deleteRoom(id) {
    const room = rooms.find((r) => r.id === id);
    if (!room) return;
    const shapeCount = shapes.filter((s) => s.roomId === id).length;
    if (!confirm(`Delete room "${room.name}" and its ${shapeCount} shape(s)?`)) return;
    setShapes((prev) => prev.filter((s) => s.roomId !== id));
    const next = rooms.filter((r) => r.id !== id);
    setRooms(next);
    if (activeRoomId === id) setActiveRoomId(next[0]?.id || null);
  }

  function deleteShape(id) {
    setShapes((prev) => prev.filter((s) => s.id !== id));
    setSelectedShapeId((cur) => (cur === id ? null : cur));
  }

  function renameRoom(id, name) {
    setRooms((prev) => prev.map((r) => (r.id === id ? { ...r, name: name.trim() || r.name } : r)));
  }

  function reassignShape(shapeId, roomId) {
    setShapes((prev) => prev.map((s) => (s.id === shapeId ? { ...s, roomId } : s)));
  }

  function setRoomColor(roomId, color) {
    setRooms((prev) => prev.map((r) => (r.id === roomId ? { ...r, color } : r)));
  }

  function openColorPopover(e, roomId) {
    const rect = e.currentTarget.getBoundingClientRect();
    setColorPopoverPos({ top: rect.bottom + 6, left: rect.left });
    setColorPopoverRoomId(roomId);
  }

  function clearAllShapes() {
    if (!shapes.length && !rooms.length) return;
    if (!confirm("Delete all shapes and rooms? Scale stays.")) return;
    setShapes([]);
    setRooms([]);
    setActiveRoomId(null);
    setSelectedShapeId(null);
  }

  // ---------- tools ----------
  function setTool(t) {
    setToolState(t);
    transientRef.current.polyPoints = null; transientRef.current.polyPreview = null;
    transientRef.current.drawStart = null; transientRef.current.drawPreview = null;
    transientRef.current.calPoints = null;
  }

  const HINTS = {
    select: "Click a shape to select it. Delete/Backspace removes the selected shape.",
    rect: "Drag to draw a rectangle for the current room.",
    poly: "Click to add points. Double-click, click the first point, or press Enter to close. Backspace undoes the last point, Esc cancels.",
    calibrate: "Click two points along a known length (e.g. a wall with a printed dimension), then type its real length.",
  };

  function requireRoomAndScale() {
    if (!stateRef.current.activeRoomId) { toast_("Add a room first (toolbar buttons)"); return false; }
    if (!stateRef.current.activeScale) { toast_("Set the scale first (Calibrate tool)"); return false; }
    return true;
  }

  function hitTestShape(p) {
    const s = stateRef.current;
    for (let i = s.shapes.length - 1; i >= 0; i--) {
      if (pointInPoly(p, s.shapes[i].points)) return s.shapes[i];
    }
    return null;
  }

  function addShape(pts, kind, area) {
    const s = stateRef.current;
    setShapes((prev) => [
      ...prev,
      { id: "s" + Date.now() + Math.floor(Math.random() * 999), roomId: s.activeRoomId, points: pts, pxArea: area, scalePxPerFt: s.activeScale, kind },
    ]);
  }

  function finishPolygon() {
    const t = transientRef.current;
    const pts = t.polyPoints;
    if (pts) {
      const area = polyArea(pts);
      if (area > 4) addShape(pts, "poly", area);
    }
    t.polyPoints = null; t.polyPreview = null;
    draw();
  }

  // ---------- mouse interaction ----------
  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const dpr = () => window.devicePixelRatio || 1;

    function screenDistToImagePoint(e, ipt) {
      const scr = toScreen(ipt.x, ipt.y);
      const rect = cv.getBoundingClientRect();
      const sx = scr.x / dpr() + rect.left, sy = scr.y / dpr() + rect.top;
      return Math.hypot(e.clientX - sx, e.clientY - sy);
    }

    function onMouseDown(e) {
      const t = transientRef.current;
      if (e.button === 1 || t.spaceDown) {
        t.panning = true;
        t.panStart = { x: e.clientX, y: e.clientY, ox: viewRef.current.ox, oy: viewRef.current.oy };
        return;
      }
      if (!imgRef.current) return;
      const p = toImage(e.clientX, e.clientY);
      const s = stateRef.current;

      if (s.tool === "rect") {
        if (!requireRoomAndScale()) return;
        t.drawStart = p; t.drawPreview = { x0: p.x, y0: p.y, x1: p.x, y1: p.y };
      } else if (s.tool === "poly") {
        if (!requireRoomAndScale()) return;
        if (!t.polyPoints) t.polyPoints = [];
        if (t.polyPoints.length >= 3 && screenDistToImagePoint(e, t.polyPoints[0]) < 10) {
          finishPolygon(); return;
        }
        t.polyPoints.push(p);
        draw();
      } else if (s.tool === "calibrate") {
        if (!t.calPoints) t.calPoints = [];
        t.calPoints.push(p);
        if (t.calPoints.length === 2) { setCalInput(""); setCalModalOpen(true); }
        draw();
      } else if (s.tool === "select") {
        const hit = hitTestShape(p);
        setSelectedShapeId(hit ? hit.id : null);
      }
    }

    function onMouseMove(e) {
      const t = transientRef.current;
      if (t.panning) {
        viewRef.current.ox = t.panStart.ox + (e.clientX - t.panStart.x) * dpr();
        viewRef.current.oy = t.panStart.oy + (e.clientY - t.panStart.y) * dpr();
        draw(); return;
      }
      if (!imgRef.current) return;
      const p = toImage(e.clientX, e.clientY);
      const s = stateRef.current;
      if (s.tool === "rect" && t.drawStart) {
        t.drawPreview = { x0: t.drawStart.x, y0: t.drawStart.y, x1: p.x, y1: p.y };
        draw();
      } else if (s.tool === "poly" && t.polyPoints) {
        t.polyPreview = p; draw();
      } else if (s.tool === "calibrate" && t.calPoints && t.calPoints.length === 1) {
        t.polyPreview = p; draw();
      }
    }

    function onMouseUp() {
      const t = transientRef.current;
      if (t.panning) { t.panning = false; return; }
      if (stateRef.current.tool === "rect" && t.drawStart) {
        const r = t.drawPreview;
        const pts = rectToPoints(r);
        const area = polyArea(pts);
        if (area > 4) addShape(pts, "rect", area);
        t.drawStart = null; t.drawPreview = null; draw();
      }
    }

    function onDblClick() {
      const t = transientRef.current;
      if (stateRef.current.tool === "poly" && t.polyPoints && t.polyPoints.length >= 3) finishPolygon();
    }

    function onWheel(e) {
      if (!imgRef.current) return;
      e.preventDefault();
      const before = toImage(e.clientX, e.clientY);
      const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      const v = viewRef.current;
      const newScale = Math.min(Math.max(v.scale * factor, v.fitScale * 0.15), v.fitScale * 14);
      v.scale = newScale;
      const rect = cv.getBoundingClientRect();
      const px = (e.clientX - rect.left) * dpr(), py = (e.clientY - rect.top) * dpr();
      v.ox = px - before.x * v.scale;
      v.oy = py - before.y * v.scale;
      setZoomPct(Math.round((100 * v.scale) / v.fitScale));
      draw();
    }

    cv.addEventListener("mousedown", onMouseDown);
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    cv.addEventListener("dblclick", onDblClick);
    cv.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      cv.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      cv.removeEventListener("dblclick", onDblClick);
      cv.removeEventListener("wheel", onWheel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toImage, toScreen, draw]);

  // ---------- keyboard ----------
  useEffect(() => {
    function onKeyDown(e) {
      const tag = document.activeElement?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") {
        if (e.key === "Escape") document.activeElement.blur();
        return;
      }
      const t = transientRef.current;
      if (e.code === "Space") {
        t.spaceDown = true;
        if (canvasRef.current) canvasRef.current.style.cursor = "grab";
        e.preventDefault();
        return;
      }
      if (e.key === "r" || e.key === "R") setTool("rect");
      if (e.key === "p" || e.key === "P") setTool("poly");
      if (e.key === "c" || e.key === "C") setTool("calibrate");
      if (e.key === "s" || e.key === "S") setTool("select");
      if (e.key === "Escape") {
        t.polyPoints = null; t.polyPreview = null; t.drawStart = null; t.drawPreview = null; t.calPoints = null;
        draw();
      }
      if (e.key === "Backspace" || e.key === "Delete") {
        if (stateRef.current.tool === "poly" && t.polyPoints && t.polyPoints.length) {
          t.polyPoints.pop(); draw(); e.preventDefault();
        } else if (stateRef.current.selectedShapeId) {
          deleteShape(stateRef.current.selectedShapeId); e.preventDefault();
        }
      }
      if (e.key === "Enter" && stateRef.current.tool === "poly" && t.polyPoints && t.polyPoints.length >= 3) {
        finishPolygon();
      }
    }
    function onKeyUp(e) {
      if (e.code === "Space") {
        transientRef.current.spaceDown = false;
        if (canvasRef.current) canvasRef.current.style.cursor = "crosshair";
      }
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draw]);

  // ---------- calibration modal ----------
  function applyCalibration() {
    const feet = parseLength(calInput);
    if (!feet || feet <= 0) { toast_('Could not read that length — try 15\'3", 15.25, or 4.3m'); return; }
    const t = transientRef.current;
    const pxLen = dist(t.calPoints[0], t.calPoints[1]);
    const scale = pxLen / feet;
    setActiveScale(scale);
    setCalModalOpen(false);
    t.calPoints = null;
    toast_("Scale set: " + scale.toFixed(2) + " px/ft — new shapes will use it");
  }
  function cancelCalibration() {
    setCalModalOpen(false);
    transientRef.current.calPoints = null;
    draw();
  }

  // ---------- totals ----------
  const outdoorRoomIds = new Set(rooms.filter((r) => r.type === "outdoor").map((r) => r.id));
  const outdoorTotal = shapes.filter((s) => outdoorRoomIds.has(s.roomId)).reduce((a, s) => a + (sqftOf(s) || 0), 0);
  const indoorTotal = shapes.filter((s) => !outdoorRoomIds.has(s.roomId)).reduce((a, s) => a + (sqftOf(s) || 0), 0);

  function handleSave() {
    onSave({ rooms, shapes, activeScale, imageW: imgDims.w, imageH: imgDims.h });
  }

  return (
    <div className="tracer">
      <div className="tracer-toolbar">
        <div className="tracer-group">
          <button className={tool === "select" ? "active" : ""} onClick={() => setTool("select")} title="Select / delete shapes (S)">Select</button>
          <button className={tool === "rect" ? "active" : ""} onClick={() => setTool("rect")} title="Rectangle (R)">Rect</button>
          <button className={tool === "poly" ? "active" : ""} onClick={() => setTool("poly")} title="Polygon — click points, double-click to close (P)">Polygon</button>
          <button className={tool === "calibrate" ? "active" : ""} onClick={() => setTool("calibrate")} title="Calibrate scale (C)">Calibrate</button>
        </div>
        <div className="tracer-group">
          {Object.entries(ROOM_TYPES).map(([key, def]) => (
            <button key={key} className="ghost" onClick={() => addRoomOfType(key)}>+ {def.label}</button>
          ))}
        </div>
        <span className={`tracer-scale-readout mono ${activeScale ? "" : "unset"}`}>
          {activeScale ? `scale: ${activeScale.toFixed(2)} px/ft` : "scale not set"}
        </span>
        <div className="tracer-spacer" />
        <button className="tracer-save-btn" onClick={handleSave} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
      </div>

      <div className="tracer-main">
        <div className="tracer-canvas-wrap" ref={wrapRef}>
          <canvas ref={canvasRef} className="tracer-canvas" />
          {!imgLoaded && <div className="tracer-empty-state">Loading floor plan…</div>}
          <div className="tracer-hint">{HINTS[tool]} &nbsp;·&nbsp; scroll to zoom, space+drag to pan</div>
          <div className="tracer-zoom-readout mono">{zoomPct}%</div>
        </div>

        <div className="tracer-sidebar">
          <div className="tracer-rooms-list">
            {rooms.length === 0 ? (
              <div className="tracer-room-empty" style={{ padding: "20px 6px" }}>
                No rooms yet — use the toolbar buttons above to add one, then draw shapes onto it.
              </div>
            ) : (
              rooms.map((room) => {
                const roomShapes = shapes.filter((sh) => sh.roomId === room.id);
                const total = roomShapes.reduce((a, sh) => a + (sqftOf(sh) || 0), 0);
                return (
                  <div className="tracer-room" key={room.id}>
                    <div className="tracer-room-head">
                      <span className="tracer-dot tracer-recolor-btn" style={{ background: room.color }} title="Change color" onClick={(e) => openColorPopover(e, room.id)} />
                      <input type="text" defaultValue={room.name} onBlur={(e) => renameRoom(room.id, e.target.value)} />
                      <span className="tracer-room-sub mono">{total.toFixed(1)} sf</span>
                      <span className="tracer-room-del" title="Delete room and its shapes" onClick={() => deleteRoom(room.id)}>×</span>
                    </div>
                    {roomShapes.length ? (
                      roomShapes.map((sh, i) => (
                        <div className={`tracer-shape-row ${sh.id === selectedShapeId ? "selected" : ""}`} key={sh.id} onClick={() => setSelectedShapeId(sh.id)}>
                          <span>{sh.kind === "rect" ? "▭" : "⬠"} {i + 1}</span>
                          <span className="tracer-sqft mono">{(sqftOf(sh) ?? 0).toFixed(1)} sf</span>
                          <select value={sh.roomId} onChange={(e) => reassignShape(sh.id, e.target.value)} onClick={(e) => e.stopPropagation()}>
                            {rooms.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                          </select>
                          <span className="tracer-x" onClick={(e) => { e.stopPropagation(); deleteShape(sh.id); }}>×</span>
                        </div>
                      ))
                    ) : (
                      <div className="tracer-room-empty">No shapes yet</div>
                    )}
                  </div>
                );
              })
            )}
          </div>
          <div className="tracer-totals">
            <div className="tracer-totals-line"><span>Rooms</span><span className="mono">{rooms.length}</span></div>
            <div className="tracer-totals-line"><span>Shapes</span><span className="mono">{shapes.length}</span></div>
            <div className="tracer-totals-line"><span>Indoor total</span><span className="mono">{indoorTotal.toFixed(1)} sq ft</span></div>
            <div className="tracer-totals-line"><span>Outdoor total</span><span className="mono">{outdoorTotal.toFixed(1)} sq ft</span></div>
            <div className="tracer-totals-grand"><span>Total</span><span className="mono">{(indoorTotal + outdoorTotal).toFixed(1)} sq ft</span></div>
            <div className="tracer-totals-actions">
              <button className="ghost" onClick={clearAllShapes}>Clear all shapes &amp; rooms</button>
            </div>
          </div>
        </div>
      </div>

      {toast && <div className="tracer-toast show">{toast}</div>}

      {colorPopoverRoomId && (
        <>
          <div className="tracer-popover-backdrop" onClick={() => setColorPopoverRoomId(null)} />
          <div className="tracer-color-popover show" style={{ top: colorPopoverPos.top, left: colorPopoverPos.left }}>
            <div className="tracer-swatches">
              {COLOR_PALETTE.map((c) => (
                <span key={c} className="tracer-swatch" style={{ background: c }} title={c}
                  onClick={() => { setRoomColor(colorPopoverRoomId, c); setColorPopoverRoomId(null); }} />
              ))}
            </div>
            <label className="tracer-custom-swatch">
              <input type="color" onChange={(e) => setRoomColor(colorPopoverRoomId, e.target.value)} onBlur={() => setColorPopoverRoomId(null)} />
              Custom…
            </label>
          </div>
        </>
      )}

      {calModalOpen && (
        <div className="tracer-cal-modal show">
          <div className="tracer-cal-box">
            <h2>Set real-world length</h2>
            <p>You drew a reference line. Enter what it measures in real life — <span className="mono">15&apos;3&quot;</span>, <span className="mono">15.25</span> (feet), or <span className="mono">4.3m</span> all work.</p>
            <input
              type="text" autoFocus value={calInput}
              onChange={(e) => setCalInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") applyCalibration(); if (e.key === "Escape") cancelCalibration(); }}
              placeholder='e.g. 15&apos;3&quot;'
            />
            <div className="tracer-cal-row">
              <button className="ghost" onClick={cancelCalibration}>Cancel</button>
              <button className="tracer-cal-primary" onClick={applyCalibration}>Set scale</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
