"""The geometry module — what an arrow and a label do once the boxes are placed.

Every Excalidraw-backed application ends up answering the same three
questions once its boxes are on the sheet: where does an arrow between two
boxes go, how does an arrow the user bent survive the boxes moving, and how
does a label stay legible. This module holds the primitives every
application needs to answer them — box arithmetic, which face an arrow
leaves and arrives on, a bent route remembered as a SHAPE rather than a
place, an arrow's kind read out of Excalidraw's two unrelated fields, and
greedy word-wrap to a column budget. The layout ENGINE — where a box goes,
how a route is chosen among several — stays with the application; this
module is what the engine is built out of.

``geometry`` is the lowest module in this package: ``stencils`` and
``scene`` import their box arithmetic from it rather than carrying their own
copy.

Words:
- a BOX is ``{x, y, width, height}``, Excalidraw's own field names, so an
  element structurally IS a box. A function that takes a box accepts either
  a dict with those four keys or a plain ``(x, y, width, height)`` tuple —
  whichever the corpus fixture or the caller happens to have — and every
  function that RETURNS a box returns the tuple form, the one
  ``stencils.py`` already used before this module existed;
- a FACE is ``left | right | top | bottom``, a side of a box;
- an ANCHOR is where an arrow meets a box, as unit fractions ``{u, v}`` of
  its width and height — deliberately unclamped, so a point just outside
  the box says so;
- a BEND is a route's interior point as ``{t, d}``: ``t`` the fraction
  along the chord from anchor to anchor, ``d`` the signed perpendicular
  offset in pixels. A route with no bends is a straight line;
- the KIND of an arrow is ``sharp | curved | elbow``, one word for
  Excalidraw's two fields;
- the CHORD is the segment between an arrow's two anchors.

The skeleton pipeline — ``normalizeBoundArrows`` and
``topAlignCrowdedLabels`` in the TypeScript half — is TypeScript only. It is
the pass a sketch application runs in the browser between a model's reply
and ``convertToExcalidrawElements``; no server has a use for it today, so
there is no Python twin.

Points are ``(x, y)`` tuples on the way out; on the way in, anything
indexable by ``[0]``/``[1]`` (a tuple or a list, the corpus's own JSON
shape) is accepted.

Pure functions, no I/O.
"""

from __future__ import annotations

import math
from typing import Any, Literal

Box = tuple[float, float, float, float]
Point = tuple[float, float]
Side = Literal["left", "right", "top", "bottom"]
ArrowKind = Literal["sharp", "curved", "elbow"]


def _num(v: Any, fallback: float = 0.0) -> float:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else fallback


def _as_box(box: Any) -> Box:
    """A box, read from a dict ``{x, y, width, height}`` or a plain
    ``(x, y, width, height)`` sequence — either is accepted on input."""
    if isinstance(box, dict):
        return (_num(box.get("x")), _num(box.get("y")), _num(box.get("width")), _num(box.get("height")))
    x, y, w, h = box
    return (_num(x), _num(y), _num(w), _num(h))


# --- boxes ---------------------------------------------------------------------

def box_of(element: dict[str, Any]) -> Box:
    """An element's box. A linear element (line, arrow, freedraw) keeps its
    origin at its FIRST point and its points relative to it, so a stroke
    drawn right-to-left has an origin at its right end and points that run
    negative; its box starts at the least point, not at the origin. Reading
    ``x`` as the left edge is how a hand-drawn symbol got a frame a
    stroke's width off."""
    x = _num(element.get("x"))
    y = _num(element.get("y"))
    points = element.get("points")
    if isinstance(points, list) and points:
        xs = [_num(p[0]) for p in points if isinstance(p, (list, tuple)) and len(p) >= 2]
        ys = [_num(p[1]) for p in points if isinstance(p, (list, tuple)) and len(p) >= 2]
        if xs:
            x += min(xs)
        if ys:
            y += min(ys)
    return (x, y, _num(element.get("width")), _num(element.get("height")))


def union(boxes: list[Any]) -> Box | None:
    """The box enclosing every box given, or ``None`` for none. Takes boxes
    rather than elements — ``union([box_of(e) for e in elements])`` is the
    element-list version an application reaches for when it has a mix of
    shapes and text."""
    boxes = [_as_box(b) for b in boxes]
    if not boxes:
        return None
    x1 = min(b[0] for b in boxes)
    y1 = min(b[1] for b in boxes)
    x2 = max(b[0] + b[2] for b in boxes)
    y2 = max(b[1] + b[3] for b in boxes)
    return (x1, y1, x2 - x1, y2 - y1)


def centre(box: Any) -> Point:
    """The centre point of a box."""
    x, y, w, h = _as_box(box)
    return (x + w / 2, y + h / 2)


def contains(box: Any, point: Any) -> bool:
    """Whether a point sits inside a box, edges inclusive — a dropped box
    counts as landing in the zone whose border it is dragged onto."""
    x, y, w, h = _as_box(box)
    return x <= point[0] <= x + w and y <= point[1] <= y + h


def overlap(a: Any, b: Any) -> bool:
    """Whether two boxes share any area. Boxes that only touch — a shared
    edge or a shared corner — do NOT overlap; the strict inequalities are
    what let two arranged rows sit flush against each other without
    tripping a collision."""
    ax, ay, aw, ah = _as_box(a)
    bx, by, bw, bh = _as_box(b)
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def area(box: Any) -> float:
    """A box's area."""
    _, _, w, h = _as_box(box)
    return w * h


# --- faces and anchors -----------------------------------------------------------

def facing_sides(a: Any, b: Any) -> tuple[Side, Side]:
    """Which face of ``a`` and which face of ``b`` an arrow between them
    should leave and arrive on. Whichever axis separates the centres MORE
    decides, so an arrow leaves and arrives where a reader expects rather
    than cutting a corner; a tie (equal separation on both axes) goes to the
    horizontal axis, since ``dx`` is compared with ``>=``."""
    acx, acy = centre(a)
    bcx, bcy = centre(b)
    dx = bcx - acx
    dy = bcy - acy
    if abs(dx) >= abs(dy):
        return ("right", "left") if dx >= 0 else ("left", "right")
    return ("bottom", "top") if dy >= 0 else ("top", "bottom")


def point_on_side(box: Any, side: Side, t: float) -> Point:
    """The point a fraction ``t`` of the way along one face of a box,
    ``t=0`` at the face's first corner in reading order (top: left→right,
    bottom: left→right, left: top→bottom, right: top→bottom)."""
    x, y, w, h = _as_box(box)
    if side == "top":
        return (x + w * t, y)
    if side == "bottom":
        return (x + w * t, y + h)
    if side == "left":
        return (x, y + h * t)
    return (x + w, y + h * t)


def along(other: Any, side: Side) -> float:
    """Where a box sits along the axis a face SPREADS on — the sort key for
    several arrows sharing one face. A ``top``/``bottom`` face spreads
    along x, so the key is the other box's x-centre; a ``left``/``right``
    face spreads along y, so it is the other box's y-centre. Sorting a
    face's arrivals by this is what keeps them from crossing each other in
    the last few pixels before they land."""
    cx, cy = centre(other)
    return cx if side in ("top", "bottom") else cy


def anchor_uv(point: Any, box: Any) -> dict[str, float]:
    """A point as unit fractions of a box's width and height — the endpoint
    half of shape memory (GMF's IdentityAnchor, Excalidraw's own
    ``fixedPoint`` for elbow arrows). Deliberately NOT clamped to the box:
    an arrow's end often sits a hair off the face it meets, and rounding it
    onto the face would move the line the user drew. Reading a point and
    writing it back with :func:`anchor_xy` is then exactly the identity. A
    zero-sized box reads as 1 px wide/tall rather than dividing by zero."""
    x, y, w, h = _as_box(box)
    w = w or 1
    h = h or 1
    return {"u": (point[0] - x) / w, "v": (point[1] - y) / h}


def anchor_xy(uv: dict[str, float], box: Any) -> Point:
    """That fraction back on the box, wherever the box now is."""
    x, y, w, h = _as_box(box)
    return (x + uv["u"] * w, y + uv["v"] * h)


def exit_t(box: Any, dx: float, dy: float) -> float:
    """The fraction along a centre-to-centre segment ``(dx, dy)`` at which
    it exits ``box``'s bounding box, measured from the box's own centre.
    Used to trim a centre-to-centre line back to the box's edge without
    ever computing an intersection: the smaller of how far the segment can
    travel before it clears the box horizontally or vertically."""
    _, _, w, h = _as_box(box)
    tx = math.inf if dx == 0 else (w / 2) / abs(dx)
    ty = math.inf if dy == 0 else (h / 2) / abs(dy)
    return min(tx, ty)


def centre_segment(a: Any, b: Any, gap: float) -> dict[str, float]:
    """The segment between two boxes' centres, trimmed ``gap`` px outside
    each — the shape whose binding focus Excalidraw derives is exactly 0.
    When the boxes overlap or nest, there is no sane trim (the exit points
    cross or the centres coincide): the raw centre-to-centre line is
    returned instead, on the same reasoning as the twins' own phase-3
    fallback — the binding focus is still 0, and Excalidraw re-routes it on
    the next move regardless."""
    ax, ay = centre(a)
    bx, by = centre(b)
    dx = bx - ax
    dy = by - ay
    length = math.hypot(dx, dy)
    if length < 1:
        return {"x1": ax, "y1": ay, "x2": bx, "y2": by}
    t0 = exit_t(a, dx, dy) + gap / length
    t1 = 1 - exit_t(b, dx, dy) - gap / length
    if not (t0 < t1):
        t0 = 0
        t1 = 1
    return {"x1": ax + dx * t0, "y1": ay + dy * t0, "x2": ax + dx * t1, "y2": ay + dy * t1}


# --- shape memory ------------------------------------------------------------
#
# A hand-drawn bend used to be stored as absolute sheet coordinates, which
# made it a statement about the page rather than about the arrow. Move
# either box and those coordinates describe a line that no longer reaches
# its own endpoints. Each interior point is stored instead as ``{t, d}``
# against the segment between the arrow's two ANCHORS: ``t`` the fraction
# along it, ``d`` the signed perpendicular offset in pixels — Eclipse GMF's
# RelativeBendpoints idea, in the simpler of its two forms. The endpoints
# themselves are never stored: they are always the anchors the router just
# computed, refitted between them on every draw.

def relative_bends(points: list[Any]) -> list[dict[str, float]]:
    """A route's interior points, expressed relative to its own chord
    (first point to last). A route with fewer than three points, or whose
    two ends coincide (a zero-length chord — nothing to measure ``t``/``d``
    against), has nothing to remember."""
    if len(points) < 3:
        return []
    ax, ay = points[0]
    bx, by = points[-1]
    vx = bx - ax
    vy = by - ay
    length = math.hypot(vx, vy)
    if length < 1e-6:
        return []
    out: list[dict[str, float]] = []
    for p in points[1:-1]:
        px, py = p
        wx = px - ax
        wy = py - ay
        out.append({
            "t": (wx * vx + wy * vy) / (length * length),
            "d": (vx * wy - vy * wx) / length,
        })
    return out


def absolute_route(bends: list[dict[str, float]], a: Any, b: Any) -> list[Point]:
    """The route those bends describe, refitted between live anchors ``a``
    and ``b``. With no bends this is just the straight segment ``[a, b]``;
    with ``a`` and ``b`` coincident there is no chord to lay the bends
    against, so the route degenerates to the two (equal) endpoints."""
    ax, ay = a
    bx, by = b
    vx = bx - ax
    vy = by - ay
    length = math.hypot(vx, vy)
    if length < 1e-6:
        return [(ax, ay), (bx, by)]
    nx = -vy / length
    ny = vx / length
    points: list[Point] = [(ax, ay)]
    for bend in bends:
        t, d = bend["t"], bend["d"]
        points.append((ax + t * vx + d * nx, ay + t * vy + d * ny))
    points.append((bx, by))
    return points


def arrow_kind(element: dict[str, Any]) -> ArrowKind:
    """Which of the toolbox's three arrow types an element is drawn as.
    Excalidraw splits sharp/curved/elbow across two unrelated fields — an
    elbow arrow is ``elbowed``, a curved one carries a ``roundness`` —
    which is a shape that cannot be stored, compared, or handed to a
    renderer. Read into one word here; ``elbowed`` wins when both are set,
    since an elbow arrow keeps whatever stale ``roundness`` an earlier type
    left behind."""
    if element.get("elbowed"):
        return "elbow"
    return "curved" if element.get("roundness") else "sharp"


def arrow_fields(kind: ArrowKind) -> dict[str, Any]:
    """The two fields Excalidraw wants for a given kind — the write side of
    :func:`arrow_kind`. Sharp is what the app itself draws when nothing was
    chosen, and what an older geometry says by saying nothing; ``elbowed``
    is present (and ``True``) only for an elbow, never ``False`` — the
    renderer spreads this dict in, and a present-but-false key is not the
    same as an absent one to code that checks ``"elbowed" in element``."""
    if kind == "curved":
        return {"roundness": {"type": 2}}
    if kind == "elbow":
        return {"roundness": None, "elbowed": True}
    return {"roundness": None}


def arrow_element(points: list[Any]) -> dict[str, Any]:
    """An arrow element's ``x``, ``y``, ``width``, ``height`` and ``points``
    from its absolute route. Excalidraw wants points relative to the
    element's own origin, and the box is the EXTENT of the point cloud, not
    a box ending at the last point — an elbow that doubles back on itself
    would otherwise be handed a negative width or height and render as a
    straight line through the corner it was meant to turn. The origin is
    always the route's first point, matching :func:`box_of`'s rule for a
    linear element."""
    sx, sy = points[0]
    rel: list[Point] = [(p[0] - sx, p[1] - sy) for p in points]
    xs = [p[0] for p in rel]
    ys = [p[1] for p in rel]
    return {
        "x": sx,
        "y": sy,
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
        "points": rel,
    }


# --- labels ------------------------------------------------------------------

# The sentinel line_count() hands wrap() for an uncapped word-wrap — the
# Python equivalent of the TypeScript side's Number.MAX_SAFE_INTEGER: no
# real label reaches it, so the "capped at maxLines" branch never fires.
_UNCAPPED = math.inf


def ellipsise(line: str, cols: int) -> str:
    """One line cut to ``cols`` characters with a trailing ellipsis. A line
    already at or over the budget loses its last character to make room
    for the mark; a shorter line simply gets it appended."""
    return line[: cols - 1] + "…" if len(line) >= cols else line + "…"


def wrap(text: str, cols: int, max_lines: float) -> list[str]:
    """Greedy word wrap to ``cols`` characters per line, capped at
    ``max_lines`` with an ellipsis on the last line when the text does not
    fit. A word longer than the budget on its own is cut to fit, with its
    own ellipsis, rather than being pushed whole onto an overflowing
    line."""
    words = (text or "").split()
    lines: list[str] = []
    line = ""
    for raw in words:
        word = raw[: cols - 1] + "…" if len(raw) > cols else raw
        nxt = f"{line} {word}" if line else word
        if len(nxt) <= cols:
            line = nxt
            continue
        lines.append(line)
        if len(lines) == max_lines:
            lines[-1] = ellipsise(lines[-1], cols)
            return lines
        line = word
    if line:
        if len(lines) < max_lines:
            lines.append(line)
        else:
            lines[-1] = ellipsise(lines[-1], cols)
    return lines


def terse(text: str, max_words: int) -> str:
    """The first ``max_words`` words of ``text``, with a trailing ellipsis
    appended (as its own word, not fused onto the last one) when there
    were more. The full text is never lost — this is only ever what gets
    DRAWN."""
    words = (text or "").split()
    if not words:
        return ""
    kept = " ".join(words[:max_words])
    return f"{kept}…" if len(words) > max_words else kept


def line_count(text: str, cols: int) -> int:
    """How many lines :func:`wrap` would produce for ``text`` at ``cols``,
    uncapped — what a server needs to size a label's box before the client
    ever draws it. Defined as ``wrap``'s own line count (rather than as an
    independent character-counting loop) so the two can never drift apart
    the way the Bastion's Python ``_text_lines`` and TypeScript
    ``wrapLabel`` did: ``_text_lines`` undercounts an empty string as one
    line where ``wrap`` draws none, and overcounts a single word longer
    than the budget as two lines because it never accounts for that word
    being cut to fit on one."""
    return len(wrap(text, cols, _UNCAPPED))
