"""The bridge between an Excalidraw canvas and a language model.

Two directions, both lossy on purpose:

**Canvas → model** (:func:`compact`). The raw scene is far too wide to put in a
prompt, and most of its width is bookkeeping a model must never invent. So the
canvas is projected onto a *skeleton dialect*: a handful of meaningful fields
per element, the binding graph folded into skeleton form, and the element types
a model cannot faithfully re-emit reduced to read-only geometry.

**Model → canvas** (:func:`extract_patch`). A reply is prose that may end in one
JSON object. That object is a MERGE PATCH — added or changed elements plus a
list of ids to delete — never a whole board. The inversion matters: a lazy
partial reply is then correct behaviour, and destruction requires explicit
intent. Validation is strict all-or-nothing, so a half-garbled reply can never
half-apply.

Everything here is pure: no I/O, no database, no framework. The constants are
keyword defaults rather than hard-coded, so an application tunes the dialect
instead of forking the module.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

# Fields worth showing a model — enough to reason about the board and to
# preserve ids, without the versionNonce/seed/roundness noise that only burns
# tokens and invites the model to echo values it should never author.
KEEP: tuple[str, ...] = (
    "id", "type", "x", "y", "width", "height", "text", "label",
    "strokeColor", "backgroundColor", "fontSize", "points", "start", "end",
    "angle", "arrowhead",
)

# Read-only to the model: hand strokes, images, and placed stencils. It cannot
# re-draw a stroke (raw payloads are huge point clouds), an echoed image would
# lose its fileId and break skeleton conversion, and a stencil instance is a
# group of primitives it should address as one symbol. Patch elements of these
# types are dropped and the client preserves the real ones. The model still
# SEES them: compact() emits each as id + bbox (+ a simplified polyline for
# strokes), which is enough to align new shapes to the ink and to delete by id.
OPAQUE_TYPES: frozenset[str] = frozenset({"freedraw", "image", "stencil"})

# The customData key a stencil instance is recognised by.
_STENCIL_KEYS: frozenset[str] = frozenset({"stencil"})

MAX_STROKE_POINTS = 32     # polyline budget per stroke; tolerance coarsens to fit
MAX_COORD = 1_000_000      # beyond this it is a hallucination, not a layout

_LABEL_TAIL = re.compile(r"\s*`{0,3}\s*(?:excalidraw|json)\s*`{0,3}\s*$", re.IGNORECASE)
_FENCE_HEAD = re.compile(r"^\s*`{3}[ \t]*\r?\n?")
_decoder = json.JSONDecoder()


def rdp(points: list[list[float]], eps: float) -> list[list[float]]:
    """Ramer-Douglas-Peucker polyline simplification (iterative)."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        worst, worst_d = -1, eps
        for i in range(a + 1, b):
            px, py = points[i]
            if norm:
                d = abs(dx * (ay - py) - dy * (ax - px)) / norm
            else:
                d = math.hypot(px - ax, py - ay)
            if d > worst_d:
                worst, worst_d = i, d
        if worst != -1:
            keep[worst] = True
            stack.append((a, worst))
            stack.append((worst, b))
    return [p for p, k in zip(points, keep) if k]


def stroke_summary(element: dict[str, Any], *,
                   max_points: int = MAX_STROKE_POINTS) -> dict[str, Any]:
    """A freedraw stroke as read-only geometry a model can align to and delete.

    Returns id + bbox + a simplified polyline in absolute integer board
    coordinates, plus a ``closed`` hint when the ends nearly meet (a hand-drawn
    circle). The RDP tolerance coarsens until the polyline fits ``max_points``,
    so a 900-point scribble costs the same as a 40-point one.
    """
    x0 = element.get("x") or 0
    y0 = element.get("y") or 0
    slim: dict[str, Any] = {
        "id": element.get("id"), "type": "freedraw",
        "x": round(x0), "y": round(y0),
        "width": round(element.get("width") or 0),
        "height": round(element.get("height") or 0),
    }
    if element.get("strokeColor"):
        slim["strokeColor"] = element["strokeColor"]
    pts = [
        [float(p[0]), float(p[1])]
        for p in (element.get("points") or [])
        if isinstance(p, (list, tuple)) and len(p) >= 2
        and all(isinstance(c, (int, float)) and not isinstance(c, bool)
                and math.isfinite(c) for c in p[:2])
    ]
    if len(pts) >= 2:
        diag = math.hypot(slim["width"], slim["height"]) or 1.0
        eps = diag * 0.02
        simple = rdp(pts, eps)
        while len(simple) > max_points:
            eps *= 2
            simple = rdp(pts, eps)
        slim["points"] = [[round(x0 + px), round(y0 + py)] for px, py in simple]
        if math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]) < diag * 0.12:
            slim["closed"] = True
    return slim


def instance_of(element: dict[str, Any]) -> str | None:
    """The stencil instance an element belongs to, or None.

    ``customData.stencil.instance`` is where excalicore writes it.
    """
    cd = element.get("customData")
    if not isinstance(cd, dict):
        return None
    tag = cd.get("stencil")
    if isinstance(tag, dict) and tag.get("instance"):
        return str(tag["instance"])
    return None


def stencil_summary(instance: str, members: list[dict[str, Any]]) -> dict[str, Any]:
    """One placed stencil as the read-only entry the model sees.

    ``{"id", "type": "stencil", "name", "x", "y", "width", "height"}`` plus a
    ``label`` when a part carries one (the part with role ``label``, else the
    first text in the group) and a ``subject`` when the application tagged the
    parts with namespaces of its own beside ``stencil`` — those are passed
    through untouched, so a prompt can say what the symbol stands for without
    the application re-deriving it from a rectangle and two lines.
    """
    def _tag(m: dict[str, Any]) -> dict[str, Any]:
        cd = m.get("customData")
        tag = cd.get("stencil") if isinstance(cd, dict) else None
        return tag if isinstance(tag, dict) else {}

    cd0 = members[0].get("customData") or {}
    tag0 = _tag(members[0])
    entry: dict[str, Any] = {
        "id": instance, "type": "stencil",
        "name": tag0.get("name"),
    }
    # The box the model sees is the SUBJECT's — read off the body and its
    # frame, the only way back — so a stick figure is reported as the box it
    # stands for, not as the union of its limbs and a centred caption with no
    # width. Only an instance without a frame falls back to the footprint of
    # its parts.
    body = next((m for m in members if _tag(m).get("role") == "body"), None)
    frame = _tag(body).get("frame") if body is not None else None
    box: tuple[float, float, float, float] | None = None
    if isinstance(frame, dict):
        try:
            box = (
                float(body.get("x") or 0) + float(frame["dx"]),
                float(body.get("y") or 0) + float(frame["dy"]),
                float(body.get("width") or 0) * float(frame["sw"]),
                float(body.get("height") or 0) * float(frame["sh"]),
            )
        except (KeyError, TypeError, ValueError):
            box = None
    if box is None:
        xs = [m.get("x") or 0 for m in members]
        ys = [m.get("y") or 0 for m in members]
        x2 = [(m.get("x") or 0) + (m.get("width") or 0) for m in members]
        y2 = [(m.get("y") or 0) + (m.get("height") or 0) for m in members]
        box = (min(xs), min(ys), max(x2) - min(xs), max(y2) - min(ys))
    entry.update({"x": round(box[0]), "y": round(box[1]),
                  "width": round(box[2]), "height": round(box[3])})
    label = None
    for m in members:
        if _tag(m).get("role") == "label":
            label = m
            break
        if m.get("type") == "text" and label is None:
            label = m
    text = (label.get("originalText") or label.get("text")) if label is not None else None
    if not text and body is not None and isinstance(body.get("label"), dict):
        text = body["label"].get("text")  # a label carried as a property on the body
    if text:
        entry["label"] = text
    subject = {k: v for k, v in cd0.items() if k not in _STENCIL_KEYS}
    if subject:
        entry["subject"] = subject
    return entry


def bbox(elements: list[Any]) -> tuple[float, float]:
    """(width, height) of a group of elements — an instance's natural footprint."""
    xs: list[float] = []
    ys: list[float] = []
    for e in elements or []:
        if not isinstance(e, dict):
            continue
        x, y = e.get("x"), e.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue
        # A linear element's origin is its first point; drawn right-to-left
        # its points run negative and its box starts before the origin.
        pts = [p for p in (e.get("points") or []) if isinstance(p, (list, tuple)) and len(p) >= 2
               and all(isinstance(c, (int, float)) for c in p[:2])]
        if pts:
            x += min(p[0] for p in pts)
            y += min(p[1] for p in pts)
        xs += [x, x + (e.get("width") or 0)]
        ys += [y, y + (e.get("height") or 0)]
    if not xs:
        return (0.0, 0.0)
    return (max(xs) - min(xs), max(ys) - min(ys))


def compact(elements: list[Any] | None, *,
            keep: tuple[str, ...] = KEEP,
            opaque: frozenset[str] = OPAQUE_TYPES,
            max_points: int = MAX_STROKE_POINTS) -> list[dict[str, Any]]:
    """Project the raw canvas onto the skeleton dialect the model speaks.

    Beyond field-stripping, this translates Excalidraw's binding graph into
    skeleton forms so a hand-drawn board survives the echo round-trip:

    - text bound to a container (``containerId``) folds into the container's
      ``label:{text}`` and drops as a standalone element — otherwise an echoed
      label detaches from its shape, or worse, duplicates;
    - arrow ``startBinding``/``endBinding`` become skeleton ``start``/``end``
      id refs, and raw ``points`` are dropped there, because conversion
      re-routes bound arrows anyway;
    - elements placed from a stencil carry ``customData.stencil {name,
      instance, role, ...}``; each instance folds into ONE read-only
      ``{"type": "stencil"}`` entry — its id the instance id, its ``label``
      the label part's text, its ``subject``
      whatever other namespaces the application tagged the parts with — so the
      model sees a symbol rather than the dozen primitives it is made of, and
      can bind an arrow to it by that one id (the client resolves the id to
      the stencil's body);
    - the remaining opaque types appear as read-only geometry.
    """
    els = [e for e in elements or [] if isinstance(e, dict) and not e.get("isDeleted")]
    by_id = {e["id"]: e for e in els if e.get("id")}
    bound_text = {
        e["containerId"]: e
        for e in els
        if e.get("type") == "text" and e.get("containerId") in by_id
    }
    instances: dict[str, list[dict[str, Any]]] = {}
    for e in els:
        gid = instance_of(e)
        if gid:
            instances.setdefault(gid, []).append(e)
    placed_ids = {e.get("id") for g in instances.values() for e in g}

    out: list[dict[str, Any]] = []
    for gid, members in instances.items():
        out.append(stencil_summary(gid, members))
    for el in els:
        if el.get("id") in placed_ids:
            continue  # summarized as its instance's stencil entry above
        kind = el.get("type")
        if kind == "freedraw":
            out.append(stroke_summary(el, max_points=max_points))
            continue
        if kind in opaque:
            out.append({
                "id": el.get("id"), "type": kind,
                "x": round(el.get("x") or 0), "y": round(el.get("y") or 0),
                "width": round(el.get("width") or 0),
                "height": round(el.get("height") or 0),
            })
            continue
        if kind == "text" and el.get("containerId") in by_id:
            continue  # folded into its container's label below
        slim = {k: el[k] for k in keep if k in el}
        lbl = bound_text.get(el.get("id"))
        lbl_text = (lbl or {}).get("originalText") or (lbl or {}).get("text")
        if lbl_text and "label" not in slim:
            slim["label"] = (
                {"text": lbl_text, "fontSize": lbl["fontSize"]}
                if lbl.get("fontSize") else {"text": lbl_text}
            )
        for bind_key, ref_key in (("startBinding", "start"), ("endBinding", "end")):
            bind = el.get(bind_key)
            if isinstance(bind, dict) and bind.get("elementId") in by_id:
                slim[ref_key] = {"id": bind["elementId"]}
                slim.pop("points", None)
        out.append(slim)
    return out


def sane_geometry(element: dict[str, Any], *, max_coord: float = MAX_COORD) -> bool:
    """True when every present coordinate is a finite number within bounds."""
    for key in ("x", "y", "width", "height"):
        v = element.get(key)
        if v is None:
            continue
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return False
        if not math.isfinite(v) or abs(v) > max_coord:
            return False
    return True


def valid_patch(obj: Any, *,
                opaque: frozenset[str] = OPAQUE_TYPES,
                max_coord: float = MAX_COORD) -> dict[str, Any] | None:
    """Validate a parsed block as a merge patch, or return None.

    A patch is ``{elements: [{type, ...}, ...]}`` and/or ``{delete: [id, ...]}``.
    An element may instead be a stencil placement, ``{"stencil": name, x, y}``.
    Strict all-or-nothing: one malformed element, or one insane coordinate,
    rejects the WHOLE patch, so a half-garbled reply can never half-apply.

    Opaque-typed elements are then dropped silently — an echoed stroke would
    replace real ink with its own simplified caricature — while the rest of the
    patch stands. A patch that says nothing after that is not a patch.
    """
    if not isinstance(obj, dict):
        return None
    els = obj.get("elements")
    els = els if isinstance(els, list) else []
    delete = obj.get("delete")
    delete = [d for d in delete if isinstance(d, str)] if isinstance(delete, list) else []

    def _num(v: Any) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    def _ok(e: Any) -> bool:
        if not (isinstance(e, dict) and sane_geometry(e, max_coord=max_coord)):
            return False
        name = e.get("stencil")
        if isinstance(name, str) and name.strip():
            # A placement: {"stencil": name, "x", "y"[, "label"][, "subject"]}.
            # It carries no "type" — the client supplies the real elements
            # from its shelf, so the position is the whole payload. Which
            # stencils exist is the application's business, not this module's.
            return _num(e.get("x")) and _num(e.get("y"))
        return bool(e.get("type"))

    if not all(_ok(e) for e in els):
        return None
    els = [e for e in els if e.get("type") not in opaque]
    if not els and not delete:
        return None
    return {"elements": els, "delete": delete}


def extract_patch(message: str, **kwargs: Any) -> tuple[str, dict[str, Any] | None]:
    """Split a model reply into ``(prose, patch)``.

    The patch is the LAST balanced JSON object in the message that validates;
    it and any surrounding ``excalidraw`` label or code fence are stripped from
    the prose. If nothing parses, the whole message is prose and the patch is
    None — invalid drawing is dropped, never forced onto the canvas.

    Keyword arguments are passed through to :func:`valid_patch`.
    """
    best: tuple[int, int, dict[str, Any]] | None = None
    i, n = 0, len(message)
    while i < n:
        if message[i] == "{":
            try:
                obj, end = _decoder.raw_decode(message, i)
            except json.JSONDecodeError:
                i += 1
                continue
            got = valid_patch(obj, **kwargs)
            if got is not None:
                best = (i, end, got)  # keep the last valid patch
            i = end
        else:
            i += 1
    if best is None:
        return message.strip(), None
    start, end, patch = best
    head = _LABEL_TAIL.sub("", message[:start])
    tail = _FENCE_HEAD.sub("", message[end:])
    prose = f"{head.rstrip()}\n{tail.lstrip()}".strip()
    return prose, patch
