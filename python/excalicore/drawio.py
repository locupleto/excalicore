"""A diagram as a draw.io file: the ``.drawio`` an editor imports, and the
editable ``.drawio.svg`` that is a picture everywhere else.

An Excalidraw-backed application usually knows more about its board than the
scene says: which box a region contains, which two boxes an arrow joins. A
converter working from the scene would have to guess that back from pixels.
So this module does not read a scene. It is a small builder the application
drives from its own model: containers, boxes and arrows at absolute
coordinates, each with a draw.io style. The builder does the parts that are
the same for every application and easy to get subtly wrong:

- **Containment.** A cell inside a container is stored relative to it, and a
  container must be written before anything placed in it, because draw.io
  resolves a parent by id as it reads. Coordinates go in absolute; the builder
  makes them relative and orders the cells.
- **Attachment.** An edge names its source and target, so it stays attached
  when a box is dragged in the editor. Its two end points are pinned to where
  they meet the boxes (``exitX``/``entryX``, perimeter off), and every point
  between them becomes a waypoint, so a bent route survives as drawn.
- **Two files.** ``to_drawio()`` writes an uncompressed ``mxfile``.
  ``to_svg()`` writes an SVG drawn here, by hand, to the same styles, with
  the ``mxfile`` carried in the root's ``content`` attribute. That is
  draw.io's convention for an editable SVG. An editor opens it as the diagram;
  anything else (a wiki without the draw.io app, a browser) shows the picture.

What the builder does not do is decide anything: no palette, no mapping from
the application's kinds to shapes, no label wording. Styles are draw.io style
properties, passed through. The builder adds only the structural ones a cell
of its type needs, and a caller's value always wins.

Pure: no I/O, no framework.
"""

from __future__ import annotations

import html
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Iterable, Literal, Sequence

from . import geometry

DRAWIO_MEDIA_TYPE = "application/vnd.jgraph.mxfile"
SVG_MEDIA_TYPE = "image/svg+xml"

Shape = Literal["rect", "cylinder", "actor"]
Box = tuple[float, float, float, float]
Point = Sequence[float]

# The structural properties each kind of cell needs. The caller's style is
# laid over these, so any of them can be overridden deliberately.
_CONTAINER = {
    "whiteSpace": "wrap", "html": "1", "container": "1", "collapsible": "0",
    "recursiveResize": "0", "verticalAlign": "top", "align": "left",
    "spacingLeft": "14", "spacingTop": "4",
}
_VERTEX = {"whiteSpace": "wrap", "html": "1"}
_SHAPES: dict[str, tuple[str, dict[str, str]]] = {
    "rect": ("", {}),
    "cylinder": (
        "shape=cylinder3",
        {"boundedLbl": "1", "backgroundOutline": "1", "size": "10"},
    ),
    "actor": (
        "shape=umlActor",
        {"verticalLabelPosition": "bottom", "verticalAlign": "top", "outlineConnect": "0"},
    ),
}
_EDGE = {
    "edgeStyle": "none", "html": "1", "endArrow": "classic", "endFill": "1",
    "exitPerimeter": "0", "entryPerimeter": "0",
}

# Height of a cylinder's end ellipse in the SVG picture: draw.io's `size`.
_CYLINDER_RY = 10.0


@dataclass
class _Cell:
    id: str
    kind: Literal["container", "vertex", "edge"]
    lines: list[str]
    style: dict[str, str]
    parent: str | None = None
    box: Box = (0.0, 0.0, 0.0, 0.0)
    shape: Shape = "rect"
    source: str = ""
    target: str = ""
    points: list[tuple[float, float]] = field(default_factory=list)
    label_at: tuple[float, float] | None = None


class Diagram:
    """One draw.io page, built cell by cell at absolute coordinates."""

    def __init__(self, name: str, *, font_family: str = "Helvetica") -> None:
        self.name = name
        self.font_family = font_family
        self._cells: dict[str, _Cell] = {}

    # --- building -------------------------------------------------------------

    def container(
        self, id: str, label: str, box: Box, *,
        parent: str | None = None, style: dict[str, str] | None = None,
    ) -> None:
        """A region other cells can sit inside. ``label`` is drawn inside the
        top-left corner."""
        self._add(_Cell(id, "container", [label] if label else [],
                        {**_CONTAINER, **(style or {})}, parent, _box(box)))

    def vertex(
        self, id: str, lines: Iterable[str], box: Box, *,
        shape: Shape = "rect", parent: str | None = None,
        style: dict[str, str] | None = None,
    ) -> None:
        """A box. ``lines`` are its label, one entry per line."""
        if shape not in _SHAPES:
            raise ValueError(f"unknown shape {shape!r}: one of {sorted(_SHAPES)}")
        extra = _SHAPES[shape][1]
        self._add(_Cell(id, "vertex", list(lines),
                        {**_VERTEX, **extra, **(style or {})}, parent,
                        _box(box), shape))

    def edge(
        self, id: str, source: str, target: str, points: Sequence[Point],
        lines: Iterable[str] = (), *,
        label_at: Point | None = None, style: dict[str, str] | None = None,
    ) -> None:
        """An arrow from ``source`` to ``target`` along ``points`` (absolute,
        first and last on the two boxes). ``label_at`` places the label in the
        SVG picture; draw.io places its own on the path."""
        pts = [(float(p[0]), float(p[1])) for p in points]
        if len(pts) < 2:
            raise ValueError(f"edge {id!r}: a route needs at least two points")
        self._add(_Cell(
            id, "edge", list(lines), {**_EDGE, **(style or {})},
            source=source, target=target, points=pts,
            label_at=(float(label_at[0]), float(label_at[1])) if label_at else None,
        ))

    def _add(self, cell: _Cell) -> None:
        if cell.id in self._cells or cell.id in ("0", "1"):
            raise ValueError(f"duplicate cell id {cell.id!r}")
        self._cells[cell.id] = cell

    # --- checking ---------------------------------------------------------------

    def _ordered(self) -> list[_Cell]:
        """Every cell, parents before children, edges last. Raises on a parent
        that is not a container, a containment cycle, or an edge whose end is
        not a box."""
        cells = self._cells
        for cell in cells.values():
            if cell.parent is not None:
                up = cells.get(cell.parent)
                if up is None or up.kind != "container":
                    raise ValueError(f"{cell.id!r}: parent {cell.parent!r} is not a container")
            if cell.kind == "edge":
                for end in (cell.source, cell.target):
                    if end not in cells or cells[end].kind == "edge":
                        raise ValueError(f"edge {cell.id!r}: {end!r} is not a box")

        def depth(cell: _Cell) -> int:
            seen: set[str] = set()
            d = 0
            while cell.parent is not None:
                if cell.id in seen:
                    raise ValueError(f"containment cycle at {cell.id!r}")
                seen.add(cell.id)
                cell = cells[cell.parent]
                d += 1
            return d

        rank = {"container": 0, "vertex": 1, "edge": 2}
        # Stable: within a rank and a depth, insertion order stands.
        return sorted(cells.values(), key=lambda c: (rank[c.kind], depth(c)))

    def _style(self, cell: _Cell) -> dict[str, str]:
        return {"fontFamily": self.font_family, **cell.style}

    # --- the .drawio file -------------------------------------------------------

    def to_mxfile(self) -> ET.Element:
        mxfile = ET.Element("mxfile", host="excalicore", type="device")
        diagram = ET.SubElement(mxfile, "diagram", id="page-1", name=self.name[:80])
        graph = ET.SubElement(
            diagram, "mxGraphModel",
            grid="1", gridSize="10", guides="1", tooltips="1", connect="1",
            arrows="1", fold="1", page="0", pageScale="1", math="0", shadow="0",
        )
        root = ET.SubElement(graph, "root")
        ET.SubElement(root, "mxCell", id="0")
        ET.SubElement(root, "mxCell", id="1", parent="0")

        for cell in self._ordered():
            style = self._style(cell)
            if cell.kind == "edge":
                self._write_edge(root, cell, style)
                continue
            lead = _SHAPES[cell.shape][0] if cell.kind == "vertex" else ""
            el = ET.SubElement(
                root, "mxCell", id=cell.id, value=_html(cell.lines),
                style=_style_string(style, lead),
                parent=cell.parent or "1", vertex="1",
            )
            x, y, w, h = cell.box
            if cell.parent is not None:
                px, py, _, _ = self._cells[cell.parent].box
                x, y = x - px, y - py
            ET.SubElement(
                el, "mxGeometry", x=_num(x), y=_num(y), width=_num(w), height=_num(h),
                **{"as": "geometry"},
            )
        return mxfile

    def _write_edge(self, root: ET.Element, cell: _Cell, style: dict[str, str]) -> None:
        src, dst = self._cells[cell.source].box, self._cells[cell.target].box
        (sx, sy), (ex, ey) = cell.points[0], cell.points[-1]
        style = {
            **style,
            "exitX": str(_fraction(sx, src[0], src[2])),
            "exitY": str(_fraction(sy, src[1], src[3])),
            "entryX": str(_fraction(ex, dst[0], dst[2])),
            "entryY": str(_fraction(ey, dst[1], dst[3])),
        }
        # An edge sits on the root layer, so its points are absolute: a cell
        # inside a container would move with the container, and an arrow
        # between two containers belongs to neither.
        el = ET.SubElement(
            root, "mxCell", id=cell.id, value=_html(cell.lines),
            style=_style_string(style), parent="1", edge="1",
            source=cell.source, target=cell.target,
        )
        g = ET.SubElement(el, "mxGeometry", relative="1", **{"as": "geometry"})
        ET.SubElement(g, "mxPoint", x=_num(sx), y=_num(sy), **{"as": "sourcePoint"})
        ET.SubElement(g, "mxPoint", x=_num(ex), y=_num(ey), **{"as": "targetPoint"})
        if len(cell.points) > 2:
            arr = ET.SubElement(g, "Array", **{"as": "points"})
            for px, py in cell.points[1:-1]:
                ET.SubElement(arr, "mxPoint", x=_num(px), y=_num(py))

    def to_drawio(self) -> bytes:
        tree = self.to_mxfile()
        ET.indent(tree)
        return ET.tostring(tree, encoding="utf-8", xml_declaration=False)

    # --- the .drawio.svg file ---------------------------------------------------

    def bounds(self) -> Box:
        boxes: list[Box] = [c.box for c in self._cells.values() if c.kind != "edge"]
        boxes += [(x, y, 0.0, 0.0) for c in self._cells.values() for x, y in c.points]
        return geometry.union(boxes) or (0.0, 0.0, 0.0, 0.0)

    def to_svg(self, *, margin: float = 20.0, background: str = "#ffffff") -> bytes:
        """The diagram drawn as SVG, with the ``mxfile`` in ``content``.

        draw.io discards this picture when it opens the file and rebuilds one
        from ``content``; everywhere else, this picture is what is seen. It
        follows the same styles: fill, stroke, dash, rounding, font colour and
        size. SVG text never wraps itself, so a box's lines are wrapped here
        to its width, as draw.io would.
        """
        bx, by, bw, bh = self.bounds()
        # Room below for an actor's caption, which hangs under its box.
        x0, y0 = bx - margin, by - margin
        w, h = bw + 2 * margin, bh + 2 * margin + 30

        svg = ET.Element(
            "svg", xmlns="http://www.w3.org/2000/svg", version="1.1",
            width=_num(w), height=_num(h),
            viewBox=f"{_num(x0)} {_num(y0)} {_num(w)} {_num(h)}",
            content=ET.tostring(self.to_mxfile(), encoding="unicode"),
            style=f"background-color:{background}",
        )
        defs = ET.SubElement(svg, "defs")
        ET.SubElement(svg, "rect", x=_num(x0), y=_num(y0), width=_num(w),
                      height=_num(h), fill=background)

        markers: dict[str, str] = {}

        def marker(colour: str) -> str:
            if colour not in markers:
                mid = f"arrow-{len(markers)}"
                m = ET.SubElement(
                    defs, "marker", id=mid, viewBox="0 0 10 10", refX="9", refY="5",
                    markerWidth="6", markerHeight="6", orient="auto-start-reverse",
                )
                ET.SubElement(m, "path", d="M0,0 L10,5 L0,10 z", fill=colour)
                markers[colour] = mid
            return markers[colour]

        ordered = self._ordered()
        for cell in ordered:
            if cell.kind == "container":
                self._svg_container(svg, cell)
        for cell in ordered:
            if cell.kind == "vertex":
                self._svg_vertex(svg, cell)
        # Arrows after every box, labels after every arrow: a label must never
        # be crossed by a line drawn after it.
        labels: list[tuple[_Cell, dict[str, str]]] = []
        for cell in ordered:
            if cell.kind != "edge":
                continue
            s = self._style(cell)
            stroke = s.get("strokeColor", "#000000")
            ET.SubElement(
                svg, "polyline",
                points=" ".join(f"{_num(x)},{_num(y)}" for x, y in cell.points),
                fill="none", stroke=stroke,
                **{"stroke-width": s.get("strokeWidth", "1"),
                   "marker-end": f"url(#{marker(stroke)})"},
                **_dash(s), **_opacity(s),
            )
            if cell.lines:
                labels.append((cell, s))
        for cell, s in labels:
            self._svg_edge_label(svg, cell, s)

        return (
            b'<?xml version="1.0" encoding="UTF-8"?>\n'
            + ET.tostring(svg, encoding="utf-8", xml_declaration=False)
        )

    def _svg_container(self, svg: ET.Element, cell: _Cell) -> None:
        s = self._style(cell)
        x, y, w, h = cell.box
        r = _radius(s)
        ET.SubElement(
            svg, "rect", x=_num(x), y=_num(y), width=_num(w), height=_num(h),
            rx=r, ry=r, fill=s.get("fillColor", "none"),
            stroke=s.get("strokeColor", "#000000"),
            **{"stroke-width": s.get("strokeWidth", "1")}, **_dash(s), **_opacity(s),
        )
        size = float(s.get("fontSize", "12"))
        _text(svg, cell.lines, x + float(s.get("spacingLeft", "0")), y + size + 8,
              size=size, colour=_font_colour(s), family=self.font_family, anchor="start")

    def _svg_vertex(self, svg: ET.Element, cell: _Cell) -> None:
        s = self._style(cell)
        x, y, w, h = cell.box
        size = float(s.get("fontSize", "12"))
        stroke = {
            "stroke": s.get("strokeColor", "#000000"),
            "stroke-width": s.get("strokeWidth", "1.5"),
            **_dash(s), **_opacity(s),
        }
        fill = s.get("fillColor", "#ffffff")
        cols = max(8, int((w - 12) / (size * 0.55)))
        lines = [part for line in cell.lines for part in geometry.wrap(line, cols, 4)]
        middle = y + h / 2 + size * 0.35 - (len(lines) - 1) * size * 0.6

        if cell.shape == "cylinder":
            ry = _CYLINDER_RY
            ET.SubElement(
                svg, "path",
                d=(f"M{_num(x)},{_num(y + ry)} A{_num(w / 2)},{_num(ry)} 0 0 1 "
                   f"{_num(x + w)},{_num(y + ry)} L{_num(x + w)},{_num(y + h - ry)} "
                   f"A{_num(w / 2)},{_num(ry)} 0 0 1 {_num(x)},{_num(y + h - ry)} Z"),
                fill=fill, **stroke,
            )
            ET.SubElement(
                svg, "path",
                d=(f"M{_num(x)},{_num(y + ry)} A{_num(w / 2)},{_num(ry)} 0 0 0 "
                   f"{_num(x + w)},{_num(y + ry)}"),
                fill="none", **stroke,
            )
            _text(svg, lines, x + w / 2, middle, size=size,
                  colour=_font_colour(s), family=self.font_family)
        elif cell.shape == "actor":
            cx = x + w / 2
            head = min(w, h) * 0.12
            hip = y + h * 0.62
            g = ET.SubElement(svg, "g", fill="none", **stroke)
            ET.SubElement(g, "circle", cx=_num(cx), cy=_num(y + head), r=_num(head), fill=fill)
            for d in (
                f"M{_num(cx)},{_num(y + 2 * head)} L{_num(cx)},{_num(hip)}",
                f"M{_num(x + w * 0.2)},{_num(y + h * 0.35)} L{_num(x + w * 0.8)},{_num(y + h * 0.35)}",
                f"M{_num(cx)},{_num(hip)} L{_num(x + w * 0.25)},{_num(y + h)}",
                f"M{_num(cx)},{_num(hip)} L{_num(x + w * 0.75)},{_num(y + h)}",
            ):
                ET.SubElement(g, "path", d=d)
            _text(svg, lines, cx, y + h + size + 4, size=size,
                  colour=_font_colour(s), family=self.font_family)
        else:
            r = _radius(s)
            ET.SubElement(
                svg, "rect", x=_num(x), y=_num(y), width=_num(w), height=_num(h),
                rx=r, ry=r, fill=fill, **stroke,
            )
            _text(svg, lines, x + w / 2, middle, size=size,
                  colour=_font_colour(s), family=self.font_family)

    def _svg_edge_label(self, svg: ET.Element, cell: _Cell, s: dict[str, str]) -> None:
        size = float(s.get("fontSize", "11"))
        if cell.label_at is not None:
            lx, ly = cell.label_at
        else:
            (ax, ay), (bx, by) = cell.points[0], cell.points[-1]
            lx, ly = (ax + bx) / 2, (ay + by) / 2
        width = max(len(line) for line in cell.lines) * size * 0.6 + 8
        height = len(cell.lines) * size * 1.2 + 4
        ground = s.get("labelBackgroundColor", "none")
        if ground != "none":
            ET.SubElement(
                svg, "rect", x=_num(lx - width / 2), y=_num(ly - size - 2),
                width=_num(width), height=_num(height), fill=ground, opacity="0.9",
            )
        _text(svg, cell.lines, lx, ly, size=size, colour=_font_colour(s),
              family=self.font_family)


# --- helpers ------------------------------------------------------------------


def _box(box: Box) -> Box:
    x, y, w, h = box
    return (float(x), float(y), float(w), float(h))


def _num(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


def _fraction(value: float, start: float, extent: float) -> float:
    """Where ``value`` falls along a box's side, 0..1 — draw.io's exit/entry."""
    if extent <= 0:
        return 0.5
    return round(min(1.0, max(0.0, (value - start) / extent)), 4)


def _html(lines: list[str]) -> str:
    """A cell value: the lines escaped as HTML (every cell is ``html=1``) and
    joined with ``<br>``. The XML writer escapes the result once more."""
    return "<br>".join(html.escape(line) for line in lines)


def _style_string(style: dict[str, str], lead: str = "") -> str:
    """draw.io's ``key=value;`` form. A lead token goes first: draw.io reads a
    bare first token as the name of a registered style."""
    body = ";".join(f"{k}={v}" for k, v in style.items())
    return f"{lead};{body};" if lead else f"{body};"


def _radius(s: dict[str, str]) -> str:
    if s.get("rounded") != "1":
        return "0"
    if s.get("absoluteArcSize") == "1":
        return _num(float(s.get("arcSize", "20")) / 2)
    return "8"


def _dash(s: dict[str, str]) -> dict[str, str]:
    if s.get("dashed") != "1":
        return {}
    pattern = s.get("dashPattern")
    return {"stroke-dasharray": "2 6" if pattern else "8 5"}


def _opacity(s: dict[str, str]) -> dict[str, str]:
    return {"opacity": _num(float(s["opacity"]) / 100)} if "opacity" in s else {}


def _font_colour(s: dict[str, str]) -> str:
    return s.get("fontColor") or s.get("strokeColor") or "#000000"


def _text(
    parent: ET.Element, lines: list[str], x: float, y: float, *,
    size: float, colour: str, family: str, anchor: str = "middle",
) -> None:
    if not lines:
        return
    t = ET.SubElement(
        parent, "text", x=_num(x), y=_num(y), fill=colour,
        **{"font-family": f"{family}, Arial, sans-serif", "font-size": _num(size),
           "text-anchor": anchor},
    )
    for i, line in enumerate(lines):
        span = ET.SubElement(t, "tspan", x=_num(x), dy="0" if i == 0 else _num(size * 1.2))
        span.text = line
