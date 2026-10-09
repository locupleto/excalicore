"""The elements module — complete Excalidraw elements, built without a canvas.

Excalidraw makes an element complete when the user draws it: an id, a seed
for the rough renderer, version counters, the style fields, and — for the
shapes that hold text or take an arrow — the two-way references that keep a
label in its box and an arrow on its shape. A server that draws for a person
(an agent adding a box, a script sketching a flow) has no canvas to do that,
and an element missing any of it fails quietly: a field Excalidraw expects as
``null`` arrives as ``undefined``, a label detaches, an arrow floats free of
the box it was bound to.

This module builds elements that are complete in that sense and keeps the
references consistent when they change:

- **base fields** (:func:`base_element`) and the four builders on top of it:
  :func:`text_element`, :func:`shape_element` (rectangle, ellipse, diamond),
  :func:`frame_element` and :func:`linear_element` (arrow, line);
- **text**: :func:`measure_text` and :func:`wrap_text` estimate what the
  canvas will measure exactly once the text is edited (a server has no font
  metrics), and a text can be centred and wrapped inside a container;
- **labels**: :func:`add_label` binds a text into a box BOTH ways
  (``containerId`` on the text, a ``text`` entry in the box's
  ``boundElements``) and grows the box to hold it; :func:`fit_label` keeps it
  centred after the box moves;
- **arrows**: :func:`route_between` finds an arrow's route from the boxes at its
  ends, :func:`bind_end` binds an end to a shape both ways,
  :func:`refit_arrow` puts bound ends back on their shapes' edges after a
  shape moved, and :func:`detach` removes an element without leaving a
  dangling reference.

Built on :mod:`excalicore.geometry` — the box arithmetic, the word wrap, the
route-to-element conversion and the exit point of a ray from a box. The
mutating functions change the dicts they are given and RETURN the other
elements they changed, so the caller can store exactly those; they do not
bump ``version``, because only the caller knows whether an element already
exists on a canvas (use :func:`touch`).

The module has no opinion about what the elements mean, which colours or
fonts to use, or how roughness is chosen: those are parameters. Pure
functions over dicts — no I/O, no database, no canvas.
"""

from __future__ import annotations

import math
import random
import string
import time
import unicodedata
from collections.abc import Mapping
from typing import Any

from .fontmetrics import ADVANCE, METRICS
from .fontmetrics import ADVANCE, METRICS
from .geometry import arrow_element, box_of, centre, exit_t, wrap

# --- Excalidraw's vocabulary ---------------------------------------------------------

SHAPES = ("rectangle", "ellipse", "diamond")
LINEAR = ("arrow", "line")
#: What an arrow may bind to.
BINDABLE = ("rectangle", "ellipse", "diamond", "text", "frame")
#: Every kind this module builds.
KINDS = ("text", *SHAPES, *LINEAR, "frame")
ARROWHEADS = (
    "arrow", "bar", "dot", "circle", "circle_outline", "triangle",
    "triangle_outline", "diamond", "diamond_outline", "crowfoot_one",
    "crowfoot_many", "crowfoot_one_or_many",
)
STROKE_STYLES = ("solid", "dashed", "dotted")

#: Excalidraw's font family ids (``constants.FONT_FAMILY``).
FONT_VIRGIL, FONT_HELVETICA, FONT_CASCADIA, FONT_EXCALIFONT, FONT_NUNITO = 1, 2, 3, 5, 6
#: Unitless line height by font family, as Excalidraw's font metadata has it.
LINE_HEIGHT = {
    FONT_VIRGIL: 1.25, FONT_HELVETICA: 1.15, FONT_CASCADIA: 1.2,
    FONT_EXCALIFONT: 1.25, FONT_NUNITO: 1.35,
}
DEFAULT_LINE_HEIGHT = 1.25

#: Excalidraw's own default stroke colour.
INK = "#1e1e1e"
#: Excalidraw's frame outline (``FRAME_STYLE.strokeColor``).
FRAME_INK = "#bbb"
FONT_SIZE = 20                  # Excalidraw's DEFAULT_FONT_SIZE
PADDING = 5                     # Excalidraw's BOUND_TEXT_PADDING
BIND_GAP = 4.0                  # an arrow's end stands this far off its shape
#: The flat glyph width (a fraction of the font size) the estimate used before
#: per-glyph widths: kept as the floor of an empty text and an opt-in ``char_em``.
CHAR_EM = 0.55

_ALPHABET = string.ascii_letters + string.digits + "_-"

Box = tuple[float, float, float, float]
Point = tuple[float, float]


# --- small things ---------------------------------------------------------------------


def new_id() -> str:
    """An id the way Excalidraw makes them: 21 characters of nanoid's alphabet."""
    return "".join(random.choices(_ALPHABET, k=21))


def nonce() -> int:
    """A ``seed`` or ``versionNonce``: a random positive 31-bit integer."""
    return random.randint(1, 2**31 - 1)


def now_ms() -> int:
    """Epoch milliseconds, as an element's ``updated``."""
    return int(time.time() * 1000)


def touch(element: dict) -> dict:
    """Record that an existing element changed: ``version`` up by one, a fresh
    ``versionNonce``, a new ``updated``. Excalidraw reconciles by these, so an
    edit made without them can be discarded as stale. Returns the element."""
    element["version"] = int(element.get("version") or 0) + 1
    element["versionNonce"] = nonce()
    element["updated"] = now_ms()
    return element


# --- text -----------------------------------------------------------------------------


def line_height(font: int) -> float:
    """The unitless line height of a font family."""
    return LINE_HEIGHT.get(font, DEFAULT_LINE_HEIGHT)


def _advance(ch: str, size: float, font: int) -> float:
    """One glyph's advance at ``size``: the font's own width, else (a glyph the
    tables lack) the font's average, or a full em for wide East-Asian forms."""
    table = ADVANCE.get(font) or ADVANCE[FONT_EXCALIFONT]
    w = table.get(ch)
    if w is not None:
        return w * size / 1000
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return size
    return (METRICS.get(font) or METRICS[FONT_EXCALIFONT])[0] * size / 1000


def text_width(line: str, size: float, font: int, *, char_em: float | None = None) -> float:
    """The width of one line. With ``char_em`` every glyph is that many ems
    wide (the old flat estimate); without, each glyph has the width of the
    font family, so ``WIDE CAPS`` are not measured like ``narrow lowercase``."""
    if char_em is not None:
        return len(line) * size * char_em
    return sum(_advance(ch, size, font) for ch in line)


def measure_text(text: str, size: float, font: int, *, char_em: float | None = None) -> tuple[float, float]:
    """The box a text takes, estimated: widest line (summed glyph advances of
    the font family) by lines times the line height. The canvas measures
    exactly the moment the text is edited, and the Observatory frontend
    re-measures on load, so this only has to be close, and never short."""
    lines = text.split("\n") or [""]
    width = max(text_width(line, size, font, char_em=char_em) for line in lines)
    floor = size * (char_em if char_em is not None else CHAR_EM)
    return (round(max(width, floor), 2), round(len(lines) * size * line_height(font), 2))


def wrap_text(text: str, width: float, size: float, font: int = FONT_EXCALIFONT, *,
              char_em: float | None = None) -> str:
    """Wrap ``text`` to ``width`` pixels the way the canvas wraps text bound to
    a box: line breaks kept, words kept whole while they fit, a word wider
    than the box broken across lines. Widths are the font's own."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            cand = f"{line} {word}" if line else word
            if text_width(cand, size, font, char_em=char_em) <= width:
                line = cand
                continue
            if line:
                lines.append(line)
                line = ""
            while text_width(word, size, font, char_em=char_em) > width and len(word) > 1:
                n = 1
                while n < len(word) - 1 and text_width(word[: n + 1], size, font, char_em=char_em) <= width:
                    n += 1
                lines.append(word[:n])
                word = word[n:]
            line = word
        lines.append(line)
    return "\n".join(lines)


def _in_container(container: Mapping[str, Any], text: str, size: float, font: int,
                  padding: float) -> tuple[str, float, float, float, float]:
    """``text`` wrapped to a container's width and centred in it: the wrapped
    text, its width and height, and its top-left corner."""
    wrapped = wrap_text(text, container["width"] - 2 * padding, size, font)
    w, h = measure_text(wrapped, size, font)
    return (wrapped, w, h,
            container["x"] + (container["width"] - w) / 2,
            container["y"] + (container["height"] - h) / 2)


# --- the builders ---------------------------------------------------------------------


def base_element(kind: str, x: float, y: float, w: float, h: float, *, roughness: int,
                 **over: Any) -> dict:
    """The fields every Excalidraw element carries, with Excalidraw's defaults.
    ``index`` is ``None``, which Excalidraw defines as "not yet assigned to a
    scene": it assigns the fractional index when the elements are loaded, and
    inventing one here would collide with the elements already there. Anything
    in ``over`` replaces a default."""
    el = {
        "id": new_id(),
        "type": kind,
        "x": x, "y": y, "width": w, "height": h,
        "angle": 0,
        "strokeColor": INK,
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": roughness,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "index": None,
        "roundness": None,
        "seed": nonce(),
        "version": 1,
        "versionNonce": nonce(),
        "isDeleted": False,
        "boundElements": None,
        "updated": now_ms(),
        "link": None,
        "locked": False,
    }
    el.update(over)
    return el


def text_element(
    text: str, x: float, y: float, *, size: float = FONT_SIZE, font: int, roughness: int,
    container: Mapping[str, Any] | None = None, padding: float = PADDING, **over: Any,
) -> dict:
    """A text element: free-standing at ``(x, y)``, or, given ``container``,
    wrapped to the container's width and centred in it (``containerId`` set).
    This builds the text only; :func:`add_label` also binds it into the box."""
    original = text
    if container is not None:
        text, w, h, x, y = _in_container(container, text, size, font, padding)
    else:
        w, h = measure_text(text, size, font)
    return base_element(
        "text", x, y, w, h, roughness=roughness,
        text=text, originalText=original, fontSize=size, fontFamily=font,
        textAlign="center" if container is not None else "left",
        verticalAlign="middle" if container is not None else "top",
        containerId=container["id"] if container is not None else None,
        autoResize=True, lineHeight=line_height(font),
        **over,
    )


def shape_element(kind: str, x: float, y: float, w: float, h: float, *, roughness: int,
                  **over: Any) -> dict:
    """A rectangle, ellipse or diamond. A rectangle and a diamond carry the
    rounded-corner ``roundness`` Excalidraw gives them by default."""
    if kind not in SHAPES:
        raise ValueError(f"a shape is one of {', '.join(SHAPES)}, not {kind!r}")
    roundness = {"rectangle": {"type": 3}, "diamond": {"type": 2}}.get(kind)
    return base_element(kind, x, y, w, h, roughness=roughness, roundness=roundness, **over)


def frame_element(x: float, y: float, w: float, h: float, name: str | None = None, *,
                  roughness: int = 0, **over: Any) -> dict:
    """A frame, named ``name`` (``None`` for no name), in Excalidraw's frame outline."""
    over.setdefault("strokeColor", FRAME_INK)
    return base_element("frame", x, y, w, h, roughness=roughness, name=name or None, **over)


def linear_element(
    kind: str, route: list[Any], *, roughness: int, start_head: str | None = None,
    end_head: str | None = None, **over: Any,
) -> dict:
    """An arrow or a line along an absolute ``route`` — its origin at the first
    point, its points relative to that, as Excalidraw wants
    (:func:`excalicore.geometry.arrow_element`). Unbound at both ends; see
    :func:`bind_end`."""
    if kind not in LINEAR:
        raise ValueError(f"a linear element is one of {', '.join(LINEAR)}, not {kind!r}")
    geo = arrow_element(route)
    el = base_element(
        kind, geo["x"], geo["y"], geo["width"], geo["height"], roughness=roughness,
        points=[[p[0], p[1]] for p in geo["points"]], lastCommittedPoint=None,
        startBinding=None, endBinding=None,
        startArrowhead=start_head, endArrowhead=end_head, **over,
    )
    if kind == "arrow":
        el["elbowed"] = False
    return el


# --- where an arrow ends --------------------------------------------------------------


def boundary_point(shape: str, box: Any, aim: Any, gap: float = BIND_GAP) -> Point:
    """Where a ray from the centre of ``box`` toward ``aim`` leaves the SHAPE
    drawn in it — an ellipse and a diamond are inside their bounding box —
    plus ``gap``. If ``aim`` is inside the shape the ray stops at ``aim``."""
    cx, cy = centre(box)
    dx, dy = aim[0] - cx, aim[1] - cy
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return (cx, cy)
    t = min(exit_t(box, dx, dy, shape), 1.0)
    reach = length * t + gap
    return (cx + dx / length * reach, cy + dy / length * reach)


def route_between(
    points: list[Any] | None, start: tuple[str, Any] | None = None,
    end: tuple[str, Any] | None = None, *, gap: float = BIND_GAP,
) -> list[Point]:
    """The absolute route of an arrow whose ends stand on shapes.

    ``points`` is the route as far as the caller knows it (two or more points)
    or ``None``; ``start`` and ``end`` are ``(shape, box)`` for an end that
    stands on a shape, ``None`` for a free end. A shape end is moved onto the
    shape's edge, aimed at the next point. With no ``points`` both ends must be
    shapes and the route is the line between their centres, trimmed to their
    edges. Raises ``ValueError`` when there is nothing to draw."""
    if points is None:
        if start is None or end is None:
            raise ValueError("a route needs points, or a shape at both ends")
        route: list[Point] = [centre(start[1]), centre(end[1])]
    else:
        route = [(p[0], p[1]) for p in points]
    if start is not None:
        route[0] = boundary_point(start[0], start[1], route[1] if len(route) > 1 else centre(start[1]), gap)
    if end is not None:
        route[-1] = boundary_point(end[0], end[1], route[-2], gap)
    if start is not None and end is not None and len(route) == 2:
        route = [
            boundary_point(start[0], start[1], centre(end[1]), gap),
            boundary_point(end[0], end[1], centre(start[1]), gap),
        ]
    return route


def route_of(linear: Mapping[str, Any]) -> list[Point]:
    """A linear element's route in absolute coordinates."""
    return [(linear["x"] + p[0], linear["y"] + p[1]) for p in linear["points"]]


def set_route(linear: dict, route: list[Any]) -> None:
    """Give a linear element a new absolute route: its origin, size and
    relative points together."""
    geo = arrow_element(route)
    linear.update(
        x=geo["x"], y=geo["y"], width=geo["width"], height=geo["height"],
        points=[[p[0], p[1]] for p in geo["points"]],
    )


# --- references that stay consistent ---------------------------------------------------


def unlist_bound(host: dict, member_id: str) -> bool:
    """Take ``member_id`` out of ``host``'s ``boundElements``. True if it was there."""
    listed = host.get("boundElements") or []
    kept = [b for b in listed if b.get("id") != member_id]
    if len(kept) == len(listed):
        return False
    host["boundElements"] = kept or None
    return True


def label_of(container: Mapping[str, Any], by_id: Mapping[str, dict]) -> dict | None:
    """The text bound into ``container``, if any (looked up in ``by_id``)."""
    for b in container.get("boundElements") or []:
        if b.get("type") == "text":
            found = by_id.get(b.get("id"))
            if found is not None:
                return found
    return None


def add_label(container: dict, text: str, *, size: float = FONT_SIZE, font: int, roughness: int,
              padding: float = PADDING, **over: Any) -> dict:
    """Bind ``text`` into ``container`` as its label and return the new text.

    The text is wrapped to the box and centred in it; if it needs more height
    than the box has, the box grows (its width never does). The binding is made
    both ways. The container's stroke colour is the text's unless ``over``
    says otherwise (a transparent stroke falls back to :data:`INK`). The caller
    stores the label after its box, so it paints on top, and ``touch``es the
    container if it already existed."""
    stroke = container.get("strokeColor") or INK
    over.setdefault("strokeColor", INK if stroke == "transparent" else stroke)
    label = text_element(text, container["x"], container["y"], size=size, font=font,
                         roughness=roughness, container=container, padding=padding, **over)
    need = label["height"] + 2 * padding
    if need > container["height"]:
        container["height"] = need
        label = text_element(text, container["x"], container["y"], size=size, font=font,
                             roughness=roughness, container=container, padding=padding, **over)
    container["boundElements"] = [*(container.get("boundElements") or []),
                                  {"id": label["id"], "type": "text"}]
    return label


def fit_label(container: dict, label: dict, *, text: str | None = None, size: float | None = None,
              padding: float = PADDING) -> list[dict]:
    """Lay ``label`` out again inside ``container`` — after the box moved or was
    resized, or with new ``text`` or ``size`` — wrapped, centred, and growing the
    box if it needs more height. Returns the elements changed (the label, and
    the container if it grew)."""
    if text is not None:
        label["originalText"] = text
    if size is not None:
        label["fontSize"] = size
    changed = [label]
    wrapped, w, h, x, y = _in_container(
        container, label["originalText"], label["fontSize"], label["fontFamily"], padding)
    need = h + 2 * padding
    if need > container["height"]:
        container["height"] = need
        changed.append(container)
        wrapped, w, h, x, y = _in_container(
            container, label["originalText"], label["fontSize"], label["fontFamily"], padding)
    label.update(x=x, y=y, width=w, height=h, text=wrapped)
    return changed


def bind_end(arrow: dict, which: str, host: dict | None, *, by_id: Mapping[str, dict] | None = None,
             gap: float = BIND_GAP) -> list[dict]:
    """Bind one end (``"start"`` or ``"end"``) of ``arrow`` to ``host``, or free
    it with ``host=None``, keeping both directions in step: the arrow's binding
    names the host and the host's ``boundElements`` names the arrow. An end that
    was bound to something else is removed from that element's list (found in
    ``by_id``). Only the binding changes; call :func:`refit_arrow` to move the
    end onto the host. Returns the other elements changed."""
    if which not in ("start", "end"):
        raise ValueError('which is "start" or "end"')
    field = "startBinding" if which == "start" else "endBinding"
    changed: list[dict] = []
    old = arrow.get(field)
    if old and by_id is not None and old.get("elementId") in by_id:
        previous = by_id[old["elementId"]]
        if previous is not host and unlist_bound(previous, arrow["id"]):
            changed.append(previous)
    arrow[field] = None
    if host is not None:
        arrow[field] = {"elementId": host["id"], "focus": 0, "gap": gap}
        listed = host.get("boundElements") or []
        if not any(b.get("id") == arrow["id"] for b in listed):
            host["boundElements"] = [*listed, {"id": arrow["id"], "type": "arrow"}]
            changed.append(host)
    return changed


def refit_arrow(arrow: dict, by_id: Mapping[str, dict], *, gap: float = BIND_GAP) -> bool:
    """Put a bound arrow's ends back on the edges of the shapes they are bound
    to (found in ``by_id``) — after a shape moved or changed size. An arrow
    bound at neither end is left alone. True if the arrow was changed."""
    route = route_of(arrow)
    sb, eb = arrow.get("startBinding"), arrow.get("endBinding")
    s = by_id.get(sb["elementId"]) if sb else None
    e = by_id.get(eb["elementId"]) if eb else None
    if s is None and e is None:
        return False
    if s is not None and e is not None and len(route) == 2:
        route = route_between(
            None, (s["type"], box_of(s)), (e["type"], box_of(e)), gap=gap)
    else:
        if s is not None:
            route[0] = boundary_point(s["type"], box_of(s), route[1], gap)
        if e is not None:
            route[-1] = boundary_point(e["type"], box_of(e), route[-2], gap)
    set_route(arrow, route)
    return True


def detach(element: dict, by_id: Mapping[str, dict]) -> tuple[list[str], list[dict]]:
    """Take ``element`` out of the references around it, ready to be removed.

    Its labels go with it; an arrow bound to it stays, let go at that end; a
    label leaves its box's list; an arrow leaves the lists of the shapes it was
    bound to. Returns ``(ids to remove, other elements changed)``: the ids are
    the element and its labels, and nothing here removes them from ``by_id``."""
    gone = [element["id"]]
    changed: list[dict] = []

    def note(el: dict) -> None:
        if not any(c is el for c in changed):
            changed.append(el)

    if element.get("containerId"):
        box = by_id.get(element["containerId"])
        if box is not None and unlist_bound(box, element["id"]):
            note(box)
    for b in element.get("boundElements") or []:
        member = by_id.get(b.get("id"))
        if member is None:
            continue
        if b.get("type") == "text":
            gone.append(member["id"])
        elif b.get("type") == "arrow":
            for field in ("startBinding", "endBinding"):
                bound = member.get(field)
                if bound and bound.get("elementId") == element["id"]:
                    member[field] = None
            note(member)
    if element.get("type") in LINEAR:
        for field in ("startBinding", "endBinding"):
            bound = element.get(field)
            if bound and bound.get("elementId") in by_id:
                host = by_id[bound["elementId"]]
                if unlist_bound(host, element["id"]):
                    note(host)
    return gone, changed
