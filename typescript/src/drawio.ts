/**
 * A diagram as a draw.io file: the `.drawio` an editor imports, and the
 * editable `.drawio.svg` that is a picture everywhere else.
 *
 * The TypeScript twin of `excalicore/drawio.py`, held to it by the golden
 * cases in `corpus/drawio/`: for the same diagram the two halves write the
 * same text, byte for byte.
 *
 * An Excalidraw-backed application usually knows more about its board than
 * the scene says: which box a region contains, which two boxes an arrow
 * joins. A converter working from the scene would have to guess that back
 * from pixels. So this module does not read a scene. It is a small builder
 * the application drives from its own model: containers, boxes and arrows at
 * absolute coordinates, each with a draw.io style. The builder does the parts
 * that are the same for every application and easy to get subtly wrong:
 *
 * - CONTAINMENT. A cell inside a container is stored relative to it, and a
 *   container must be written before anything placed in it, because draw.io
 *   resolves a parent by id as it reads. Coordinates go in absolute; the
 *   builder makes them relative and orders the cells.
 * - ATTACHMENT. An edge names its source and target, so it stays attached
 *   when a box is dragged in the editor. Its two end points are pinned to
 *   where they meet the boxes (`exitX`/`entryX`, perimeter off), and every
 *   point between them becomes a waypoint, so a bent route survives as drawn.
 * - TWO FILES. `toDrawio()` writes an uncompressed `mxfile`. `toSvg()` writes
 *   an SVG drawn here, by hand, to the same styles, with the `mxfile` carried
 *   in the root's `content` attribute. That is draw.io's convention for an
 *   editable SVG: an editor opens it as the diagram; anything else (a wiki
 *   without the draw.io app, a browser) shows the picture.
 *
 * What the builder does not do is decide anything: no palette, no mapping
 * from the application's kinds to shapes, no label wording. Styles are
 * draw.io style properties, passed through. The builder adds only the
 * structural ones a cell of its type needs, and a caller's value always wins.
 *
 * The XML is written by a few lines here, not by a DOM: no `DOMParser`, no
 * `XMLSerializer`, so it runs in Node as it does in a browser. The writer
 * reproduces Python's `xml.etree.ElementTree` exactly — attributes in
 * insertion order, `&#10;` for a newline in an attribute, `<x />` for an
 * empty element — and so do the number formats (`_num`'s two decimals with
 * round-half-even, a fraction printed as Python prints a float), because the
 * point is that the two halves write the same bytes.
 *
 * Two places where the halves can still differ, both in text no application
 * is likely to write: a style key that looks like an integer (a JS object
 * lists those first, Python keeps insertion order), and a label wrapped in
 * the SVG picture that holds characters outside the Basic Multilingual Plane
 * (`wrap` counts UTF-16 units here, code points in Python).
 *
 * Pure: no I/O, no framework, no DOM.
 */

import { union, wrap, type Box } from './geometry.ts'

export const DRAWIO_MEDIA_TYPE = 'application/vnd.jgraph.mxfile'
export const SVG_MEDIA_TYPE = 'image/svg+xml'

export type Shape = 'rect' | 'cylinder' | 'actor'

/** `[x, y, width, height]` — Python's `Box` tuple. (Not geometry's `Box`,
 *  which is an object; this is the shape the builder is called with.) */
export type BoxTuple = readonly [number, number, number, number]
/** `[x, y]`, any longer sequence tolerated as Python's `Sequence[float]`. */
export type Point = readonly number[]
/** draw.io style properties, passed through as `key=value;`. */
export type Style = Readonly<Record<string, string>>

/** What Python raises as `ValueError`: a bad id, shape, route or style
 *  number. Named so a caller (and the corpus) can tell it from a bug. */
export class ValueError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ValueError'
  }
}

export interface ContainerOptions { parent?: string | null; style?: Style }
export interface VertexOptions { shape?: Shape; parent?: string | null; style?: Style }
export interface EdgeOptions { labelAt?: Point | null; style?: Style }
export interface DiagramOptions { fontFamily?: string }
export interface SvgOptions { margin?: number; background?: string }

// The structural properties each kind of cell needs. The caller's style is
// laid over these, so any of them can be overridden deliberately.
const CONTAINER: readonly (readonly [string, string])[] = [
  ['whiteSpace', 'wrap'], ['html', '1'], ['container', '1'], ['collapsible', '0'],
  ['recursiveResize', '0'], ['verticalAlign', 'top'], ['align', 'left'],
  ['spacingLeft', '14'], ['spacingTop', '4'],
]
const VERTEX: readonly (readonly [string, string])[] = [['whiteSpace', 'wrap'], ['html', '1']]
const SHAPES: Readonly<Record<Shape, readonly [string, readonly (readonly [string, string])[]]>> = {
  rect: ['', []],
  cylinder: [
    'shape=cylinder3',
    [['boundedLbl', '1'], ['backgroundOutline', '1'], ['size', '10']],
  ],
  actor: [
    'shape=umlActor',
    [['verticalLabelPosition', 'bottom'], ['verticalAlign', 'top'], ['outlineConnect', '0']],
  ],
}
const EDGE: readonly (readonly [string, string])[] = [
  ['edgeStyle', 'none'], ['html', '1'], ['endArrow', 'classic'], ['endFill', '1'],
  ['exitPerimeter', '0'], ['entryPerimeter', '0'],
]

// Height of a cylinder's end ellipse in the SVG picture: draw.io's `size`.
const CYLINDER_RY = 10

type Pairs = Iterable<readonly [string, string]>
type Kind = 'container' | 'vertex' | 'edge'

interface Cell {
  id: string
  kind: Kind
  lines: string[]
  style: Map<string, string>
  parent: string | null
  box: BoxTuple
  shape: Shape
  source: string
  target: string
  points: [number, number][]
  labelAt: [number, number] | null
}

/** One draw.io page, built cell by cell at absolute coordinates. */
export class Diagram {
  name: string
  fontFamily: string
  private cells = new Map<string, Cell>()

  constructor(name: string, options: DiagramOptions = {}) {
    this.name = name
    this.fontFamily = options.fontFamily ?? 'Helvetica'
  }

  // --- building -------------------------------------------------------------

  /** A region other cells can sit inside. `label` is drawn inside the
   *  top-left corner. */
  container(id: string, label: string, box: BoxTuple, options: ContainerOptions = {}): void {
    this.add(blank(id, 'container', label ? [label] : [],
      merge(CONTAINER, entries(options.style)), options.parent ?? null, boxOf(box)))
  }

  /** A box. `lines` are its label, one entry per line. */
  vertex(id: string, lines: Iterable<string>, box: BoxTuple, options: VertexOptions = {}): void {
    const shape = options.shape ?? 'rect'
    if (!Object.hasOwn(SHAPES, shape)) {
      throw new ValueError(`unknown shape ${repr(shape)}: one of ${reprList(Object.keys(SHAPES).sort())}`)
    }
    const cell = blank(id, 'vertex', [...lines],
      merge(VERTEX, SHAPES[shape][1], entries(options.style)),
      options.parent ?? null, boxOf(box))
    cell.shape = shape
    this.add(cell)
  }

  /** An arrow from `source` to `target` along `points` (absolute, first and
   *  last on the two boxes). `labelAt` places the label in the SVG picture;
   *  draw.io places its own on the path. */
  edge(
    id: string, source: string, target: string, points: readonly Point[],
    lines: Iterable<string> = [], options: EdgeOptions = {},
  ): void {
    const pts = points.map((p): [number, number] => [p[0], p[1]])
    if (pts.length < 2) {
      throw new ValueError(`edge ${repr(id)}: a route needs at least two points`)
    }
    const at = options.labelAt
    const cell = blank(id, 'edge', [...lines], merge(EDGE, entries(options.style)), null,
      [0, 0, 0, 0])
    cell.source = source
    cell.target = target
    cell.points = pts
    cell.labelAt = at && at.length > 0 ? [at[0], at[1]] : null
    this.add(cell)
  }

  private add(cell: Cell): void {
    if (this.cells.has(cell.id) || cell.id === '0' || cell.id === '1') {
      throw new ValueError(`duplicate cell id ${repr(cell.id)}`)
    }
    this.cells.set(cell.id, cell)
  }

  // --- checking -------------------------------------------------------------

  /** Every cell, parents before children, edges last. Throws on a parent
   *  that is not a container, a containment cycle, or an edge whose end is
   *  not a box. */
  private ordered(): Cell[] {
    const cells = this.cells
    for (const cell of cells.values()) {
      if (cell.parent !== null) {
        const up = cells.get(cell.parent)
        if (up === undefined || up.kind !== 'container') {
          throw new ValueError(`${repr(cell.id)}: parent ${repr(cell.parent)} is not a container`)
        }
      }
      if (cell.kind === 'edge') {
        for (const end of [cell.source, cell.target]) {
          const to = cells.get(end)
          if (to === undefined || to.kind === 'edge') {
            throw new ValueError(`edge ${repr(cell.id)}: ${repr(end)} is not a box`)
          }
        }
      }
    }

    const depth = (start: Cell): number => {
      const seen = new Set<string>()
      let cell = start
      let d = 0
      while (cell.parent !== null) {
        if (seen.has(cell.id)) throw new ValueError(`containment cycle at ${repr(cell.id)}`)
        seen.add(cell.id)
        cell = cells.get(cell.parent) as Cell
        d += 1
      }
      return d
    }

    const rank = { container: 0, vertex: 1, edge: 2 }
    // Stable: within a rank and a depth, insertion order stands.
    return [...cells.values()]
      .map((cell) => ({ cell, rank: rank[cell.kind], depth: depth(cell) }))
      .sort((a, b) => a.rank - b.rank || a.depth - b.depth)
      .map((k) => k.cell)
  }

  private styleOf(cell: Cell): Map<string, string> {
    return merge([['fontFamily', this.fontFamily]], cell.style)
  }

  // --- the .drawio file -----------------------------------------------------

  private mxfile(): El {
    const mxfile = el('mxfile', { host: 'excalicore', type: 'device' })
    const diagram = sub(mxfile, 'diagram', {
      id: 'page-1', name: Array.from(this.name).slice(0, 80).join(''),
    })
    const graph = sub(diagram, 'mxGraphModel', {
      grid: '1', gridSize: '10', guides: '1', tooltips: '1', connect: '1',
      arrows: '1', fold: '1', page: '0', pageScale: '1', math: '0', shadow: '0',
    })
    const root = sub(graph, 'root', {})
    sub(root, 'mxCell', { id: '0' })
    sub(root, 'mxCell', { id: '1', parent: '0' })

    for (const cell of this.ordered()) {
      const style = this.styleOf(cell)
      if (cell.kind === 'edge') {
        this.writeEdge(root, cell, style)
        continue
      }
      const lead = cell.kind === 'vertex' ? SHAPES[cell.shape][0] : ''
      const node = sub(root, 'mxCell', {
        id: cell.id, value: htmlOf(cell.lines), style: styleString(style, lead),
        parent: cell.parent || '1', vertex: '1',
      })
      let [x, y] = cell.box
      const [, , w, h] = cell.box
      if (cell.parent !== null) {
        const [px, py] = (this.cells.get(cell.parent) as Cell).box
        x -= px
        y -= py
      }
      sub(node, 'mxGeometry', { x: num(x), y: num(y), width: num(w), height: num(h), as: 'geometry' })
    }
    return mxfile
  }

  private writeEdge(root: El, cell: Cell, style: Map<string, string>): void {
    const src = (this.cells.get(cell.source) as Cell).box
    const dst = (this.cells.get(cell.target) as Cell).box
    const [sx, sy] = cell.points[0]
    const [ex, ey] = cell.points[cell.points.length - 1]
    const pinned = merge(style, [
      ['exitX', pyFloatStr(fraction(sx, src[0], src[2]))],
      ['exitY', pyFloatStr(fraction(sy, src[1], src[3]))],
      ['entryX', pyFloatStr(fraction(ex, dst[0], dst[2]))],
      ['entryY', pyFloatStr(fraction(ey, dst[1], dst[3]))],
    ])
    // An edge sits on the root layer, so its points are absolute: a cell
    // inside a container would move with the container, and an arrow
    // between two containers belongs to neither.
    const node = sub(root, 'mxCell', {
      id: cell.id, value: htmlOf(cell.lines), style: styleString(pinned),
      parent: '1', edge: '1', source: cell.source, target: cell.target,
    })
    const g = sub(node, 'mxGeometry', { relative: '1', as: 'geometry' })
    sub(g, 'mxPoint', { x: num(sx), y: num(sy), as: 'sourcePoint' })
    sub(g, 'mxPoint', { x: num(ex), y: num(ey), as: 'targetPoint' })
    if (cell.points.length > 2) {
      const arr = sub(g, 'Array', { as: 'points' })
      for (const [px, py] of cell.points.slice(1, -1)) {
        sub(arr, 'mxPoint', { x: num(px), y: num(py) })
      }
    }
  }

  /** The `mxfile` as compact XML text — what `toSvg()` carries in `content`.
   *  (Python's `to_mxfile()` returns the element tree; there is no DOM here,
   *  so this is its serialisation.) */
  toMxfile(): string {
    return serialize(this.mxfile())
  }

  /** The `.drawio` file's text: an uncompressed `mxfile`, indented two
   *  spaces, no XML declaration. Write it as UTF-8. */
  toDrawio(): string {
    const tree = this.mxfile()
    indent(tree)
    return serialize(tree)
  }

  // --- the .drawio.svg file -------------------------------------------------

  /** The box enclosing every box and every route point, `[x, y, w, h]`;
   *  `[0, 0, 0, 0]` for an empty diagram. */
  bounds(): BoxTuple {
    const boxes: Box[] = []
    for (const c of this.cells.values()) {
      if (c.kind !== 'edge') boxes.push({ x: c.box[0], y: c.box[1], width: c.box[2], height: c.box[3] })
    }
    for (const c of this.cells.values()) {
      for (const [x, y] of c.points) boxes.push({ x, y, width: 0, height: 0 })
    }
    const u = union(boxes)
    return u ? [u.x, u.y, u.width, u.height] : [0, 0, 0, 0]
  }

  /**
   * The diagram drawn as SVG, with the `mxfile` in `content`.
   *
   * draw.io discards this picture when it opens the file and rebuilds one
   * from `content`; everywhere else, this picture is what is seen. It follows
   * the same styles: fill, stroke, dash, rounding, font colour and size. SVG
   * text never wraps itself, so a box's lines are wrapped here to its width,
   * as draw.io would. Write it as UTF-8.
   */
  toSvg(options: SvgOptions = {}): string {
    const margin = options.margin ?? 20
    const background = options.background ?? '#ffffff'
    const [bx, by, bw, bh] = this.bounds()
    // Room below for an actor's caption, which hangs under its box.
    const x0 = bx - margin
    const y0 = by - margin
    const w = bw + 2 * margin
    const h = bh + 2 * margin + 30

    const svg = el('svg', {
      xmlns: 'http://www.w3.org/2000/svg', version: '1.1',
      width: num(w), height: num(h),
      viewBox: `${num(x0)} ${num(y0)} ${num(w)} ${num(h)}`,
      content: this.toMxfile(),
      style: `background-color:${background}`,
    })
    const defs = sub(svg, 'defs', {})
    sub(svg, 'rect', { x: num(x0), y: num(y0), width: num(w), height: num(h), fill: background })

    const markers = new Map<string, string>()
    const marker = (colour: string): string => {
      let mid = markers.get(colour)
      if (mid === undefined) {
        mid = `arrow-${markers.size}`
        const m = sub(defs, 'marker', {
          id: mid, viewBox: '0 0 10 10', refX: '9', refY: '5',
          markerWidth: '6', markerHeight: '6', orient: 'auto-start-reverse',
        })
        sub(m, 'path', { d: 'M0,0 L10,5 L0,10 z', fill: colour })
        markers.set(colour, mid)
      }
      return mid
    }

    const ordered = this.ordered()
    for (const cell of ordered) if (cell.kind === 'container') this.svgContainer(svg, cell)
    for (const cell of ordered) if (cell.kind === 'vertex') this.svgVertex(svg, cell)
    // Arrows after every box, labels after every arrow: a label must never
    // be crossed by a line drawn after it.
    const labels: [Cell, Map<string, string>][] = []
    for (const cell of ordered) {
      if (cell.kind !== 'edge') continue
      const s = this.styleOf(cell)
      const stroke = s.get('strokeColor') ?? '#000000'
      sub(svg, 'polyline', {
        points: cell.points.map(([x, y]) => `${num(x)},${num(y)}`).join(' '),
        fill: 'none', stroke,
        'stroke-width': s.get('strokeWidth') ?? '1',
        'marker-end': `url(#${marker(stroke)})`,
        ...dash(s), ...opacity(s),
      })
      if (cell.lines.length) labels.push([cell, s])
    }
    for (const [cell, s] of labels) this.svgEdgeLabel(svg, cell, s)

    return `<?xml version="1.0" encoding="UTF-8"?>\n${serialize(svg)}`
  }

  private svgContainer(svg: El, cell: Cell): void {
    const s = this.styleOf(cell)
    const [x, y, w, h] = cell.box
    const r = radius(s)
    sub(svg, 'rect', {
      x: num(x), y: num(y), width: num(w), height: num(h),
      rx: r, ry: r, fill: s.get('fillColor') ?? 'none',
      stroke: s.get('strokeColor') ?? '#000000',
      'stroke-width': s.get('strokeWidth') ?? '1', ...dash(s), ...opacity(s),
    })
    const size = pyFloat(s.get('fontSize') ?? '12')
    text(svg, cell.lines, x + pyFloat(s.get('spacingLeft') ?? '0'), y + size + 8,
      { size, colour: fontColour(s), family: this.fontFamily, anchor: 'start' })
  }

  private svgVertex(svg: El, cell: Cell): void {
    const s = this.styleOf(cell)
    const [x, y, w, h] = cell.box
    const size = pyFloat(s.get('fontSize') ?? '12')
    const stroke = {
      stroke: s.get('strokeColor') ?? '#000000',
      'stroke-width': s.get('strokeWidth') ?? '1.5',
      ...dash(s), ...opacity(s),
    }
    const fill = s.get('fillColor') ?? '#ffffff'
    const cols = Math.max(8, Math.trunc((w - 12) / (size * 0.55)))
    const lines = cell.lines.flatMap((line) => wrap(line, cols, 4))
    const middle = y + h / 2 + size * 0.35 - (lines.length - 1) * size * 0.6
    const label = { size, colour: fontColour(s), family: this.fontFamily }

    if (cell.shape === 'cylinder') {
      const ry = CYLINDER_RY
      sub(svg, 'path', {
        d: `M${num(x)},${num(y + ry)} A${num(w / 2)},${num(ry)} 0 0 1 `
          + `${num(x + w)},${num(y + ry)} L${num(x + w)},${num(y + h - ry)} `
          + `A${num(w / 2)},${num(ry)} 0 0 1 ${num(x)},${num(y + h - ry)} Z`,
        fill, ...stroke,
      })
      sub(svg, 'path', {
        d: `M${num(x)},${num(y + ry)} A${num(w / 2)},${num(ry)} 0 0 0 ${num(x + w)},${num(y + ry)}`,
        fill: 'none', ...stroke,
      })
      text(svg, lines, x + w / 2, middle, label)
    } else if (cell.shape === 'actor') {
      const cx = x + w / 2
      const head = Math.min(w, h) * 0.12
      const hip = y + h * 0.62
      const g = sub(svg, 'g', { fill: 'none', ...stroke })
      sub(g, 'circle', { cx: num(cx), cy: num(y + head), r: num(head), fill })
      for (const d of [
        `M${num(cx)},${num(y + 2 * head)} L${num(cx)},${num(hip)}`,
        `M${num(x + w * 0.2)},${num(y + h * 0.35)} L${num(x + w * 0.8)},${num(y + h * 0.35)}`,
        `M${num(cx)},${num(hip)} L${num(x + w * 0.25)},${num(y + h)}`,
        `M${num(cx)},${num(hip)} L${num(x + w * 0.75)},${num(y + h)}`,
      ]) sub(g, 'path', { d })
      text(svg, lines, cx, y + h + size + 4, label)
    } else {
      const r = radius(s)
      sub(svg, 'rect', {
        x: num(x), y: num(y), width: num(w), height: num(h), rx: r, ry: r, fill, ...stroke,
      })
      text(svg, lines, x + w / 2, middle, label)
    }
  }

  private svgEdgeLabel(svg: El, cell: Cell, s: Map<string, string>): void {
    const size = pyFloat(s.get('fontSize') ?? '11')
    let lx: number
    let ly: number
    if (cell.labelAt !== null) {
      ;[lx, ly] = cell.labelAt
    } else {
      const [ax, ay] = cell.points[0]
      const [bx, by] = cell.points[cell.points.length - 1]
      lx = (ax + bx) / 2
      ly = (ay + by) / 2
    }
    const width = Math.max(...cell.lines.map(length)) * size * 0.6 + 8
    const height = cell.lines.length * size * 1.2 + 4
    const ground = s.get('labelBackgroundColor') ?? 'none'
    if (ground !== 'none') {
      sub(svg, 'rect', {
        x: num(lx - width / 2), y: num(ly - size - 2),
        width: num(width), height: num(height), fill: ground, opacity: '0.9',
      })
    }
    text(svg, cell.lines, lx, ly, { size, colour: fontColour(s), family: this.fontFamily })
  }
}

// --- helpers ------------------------------------------------------------------

function blank(
  id: string, kind: Kind, lines: string[], style: Map<string, string>,
  parent: string | null, box: BoxTuple,
): Cell {
  return {
    id, kind, lines, style, parent, box, shape: 'rect',
    source: '', target: '', points: [], labelAt: null,
  }
}

function boxOf(box: BoxTuple): BoxTuple {
  return [box[0], box[1], box[2], box[3]]
}

function entries(style: Style | undefined): Pairs {
  return style ? Object.entries(style) : []
}

/** Python's `{**a, **b}`: later keys win, a key keeps its first position. */
function merge(...parts: Pairs[]): Map<string, string> {
  const out = new Map<string, string>()
  for (const part of parts) for (const [k, v] of part) out.set(k, v)
  return out
}

/** Python's `f"{value:.2f}".rstrip("0").rstrip(".") or "0"`. */
function num(value: number): string {
  return (fixed(value, 2).replace(/0+$/, '').replace(/\.+$/, '')) || '0'
}

/** Python's `f"{value:.{digits}f}"`. JavaScript's `toFixed` rounds an exact
 *  tie up; Python rounds it to even, so a tie (a multiple of 1/2^(digits+1),
 *  odd — 0.125 at two digits) is settled here, in integers. */
function fixed(value: number, digits: number): string {
  if (Number.isNaN(value)) return 'nan'
  if (!Number.isFinite(value)) return value < 0 ? '-inf' : 'inf'
  const sign = value < 0 || Object.is(value, -0) ? '-' : ''
  const a = Math.abs(value)
  if (a >= 1e21) return `${sign}${BigInt(a)}.${'0'.repeat(digits)}`
  const t = a * 2 ** (digits + 1)
  if (Number.isInteger(t) && t % 2 === 1) {
    let units = (BigInt(t) * 5n ** BigInt(digits)) / 2n
    if (units % 2n === 1n) units += 1n
    const s = units.toString().padStart(digits + 1, '0')
    return `${sign}${s.slice(0, -digits)}.${s.slice(-digits)}`
  }
  return sign + a.toFixed(digits)
}

/** Python's `round(value, digits)` for a finite value: half to even. */
function roundTo(value: number, digits: number): number {
  const a = Math.abs(value)
  const t = a * 2 ** (digits + 1)
  if (Number.isInteger(t) && t % 2 === 1) {
    let units = (BigInt(t) * 5n ** BigInt(digits)) / 2n
    if (units % 2n === 1n) units += 1n
    return Math.sign(value) * (Number(units) / 10 ** digits)
  }
  return Number(value.toFixed(digits))
}

/** Python's `str(float)` for a value in [0, 1]: "0.0", "1.0", "0.3333". */
function pyFloatStr(value: number): string {
  return Number.isInteger(value) ? value.toFixed(1) : String(value)
}

/** Where `value` falls along a box's side, 0..1 — draw.io's exit/entry. */
function fraction(value: number, start: number, extent: number): number {
  if (extent <= 0) return 0.5
  return roundTo(Math.min(1, Math.max(0, (value - start) / extent)), 4)
}

/** Python's `float(text)` on a style value: the same strings accepted
 *  (underscores between digits, `inf`, `nan`), the same `ValueError`. */
function pyFloat(text: string): number {
  const s = text.trim()
  if (/^[+-]?((\d+(_\d+)*)(\.(\d+(_\d+)*)?)?|\.\d+(_\d+)*)([eE][+-]?\d+(_\d+)*)?$/.test(s)) {
    return Number(s.replaceAll('_', ''))
  }
  if (/^[+-]?(inf|infinity)$/i.test(s)) return s.startsWith('-') ? -Infinity : Infinity
  if (/^[+-]?nan$/i.test(s)) return NaN
  throw new ValueError(`could not convert string to float: ${repr(text)}`)
}

/** Python's `repr(str)`, for the messages that quote an id. */
function repr(s: string): string {
  const quote = s.includes("'") && !s.includes('"') ? '"' : "'"
  let out = ''
  for (const ch of s) {
    const c = ch.codePointAt(0) as number
    if (ch === '\\') out += '\\\\'
    else if (ch === quote) out += `\\${quote}`
    else if (ch === '\n') out += '\\n'
    else if (ch === '\r') out += '\\r'
    else if (ch === '\t') out += '\\t'
    else if (c < 0x20 || (c >= 0x7f && c < 0xa0)) out += `\\x${c.toString(16).padStart(2, '0')}`
    else out += ch
  }
  return quote + out + quote
}

function reprList(items: string[]): string {
  return `[${items.map(repr).join(', ')}]`
}

/** `len(str)` in Python: code points, not UTF-16 units. */
function length(s: string): number {
  return Array.from(s).length
}

/** A cell value: the lines escaped as HTML (every cell is `html=1`) and
 *  joined with `<br>`. The XML writer escapes the result once more. */
function htmlOf(lines: string[]): string {
  return lines.map(htmlEscape).join('<br>')
}

/** Python's `html.escape(s)`, quotes included. */
function htmlEscape(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#x27;' })[c] as string)
}

/** draw.io's `key=value;` form. A lead token goes first: draw.io reads a
 *  bare first token as the name of a registered style. */
function styleString(style: Map<string, string>, lead = ''): string {
  const body = [...style].map(([k, v]) => `${k}=${v}`).join(';')
  return lead ? `${lead};${body};` : `${body};`
}

function radius(s: Map<string, string>): string {
  if (s.get('rounded') !== '1') return '0'
  if (s.get('absoluteArcSize') === '1') return num(pyFloat(s.get('arcSize') ?? '20') / 2)
  return '8'
}

function dash(s: Map<string, string>): Record<string, string> {
  if (s.get('dashed') !== '1') return {}
  return { 'stroke-dasharray': s.get('dashPattern') ? '2 6' : '8 5' }
}

function opacity(s: Map<string, string>): Record<string, string> {
  const o = s.get('opacity')
  return o === undefined ? {} : { opacity: num(pyFloat(o) / 100) }
}

function fontColour(s: Map<string, string>): string {
  return s.get('fontColor') || s.get('strokeColor') || '#000000'
}

interface Label { size: number; colour: string; family: string; anchor?: string }

function text(parent: El, lines: string[], x: number, y: number, label: Label): void {
  if (!lines.length) return
  const t = sub(parent, 'text', {
    x: num(x), y: num(y), fill: label.colour,
    'font-family': `${label.family}, Arial, sans-serif`, 'font-size': num(label.size),
    'text-anchor': label.anchor ?? 'middle',
  })
  lines.forEach((line, i) => {
    const span = sub(t, 'tspan', { x: num(x), dy: i === 0 ? '0' : num(label.size * 1.2) })
    span.text = line
  })
}

// --- the XML writer -------------------------------------------------------------
//
// The part of `xml.etree.ElementTree` this module uses, and nothing else.

interface El {
  tag: string
  attrs: Map<string, string>
  children: El[]
  text: string
  tail: string
}

function el(tag: string, attrs: Readonly<Record<string, string>>): El {
  return { tag, attrs: new Map(Object.entries(attrs)), children: [], text: '', tail: '' }
}

function sub(parent: El, tag: string, attrs: Readonly<Record<string, string>>): El {
  const child = el(tag, attrs)
  parent.children.push(child)
  return child
}

const ATTRIBUTE_ESCAPES: Readonly<Record<string, string>> = {
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;',
  '\r': '&#13;', '\n': '&#10;', '\t': '&#09;',
}

function escapeAttribute(s: string): string {
  return s.replace(/[&<>"\r\n\t]/g, (c) => ATTRIBUTE_ESCAPES[c] as string)
}

function escapeText(s: string): string {
  return s.replace(/[&<>]/g, (c) => ATTRIBUTE_ESCAPES[c] as string)
}

/** `ET.tostring(el, encoding="unicode")`: attributes in insertion order, an
 *  element with neither text nor children written as `<x />`. */
function serialize(e: El): string {
  let out = `<${e.tag}`
  for (const [k, v] of e.attrs) out += ` ${k}="${escapeAttribute(v)}"`
  if (e.text || e.children.length) {
    out += `>${escapeText(e.text)}${e.children.map(serialize).join('')}</${e.tag}>`
  } else {
    out += ' />'
  }
  return e.tail ? out + escapeText(e.tail) : out
}

/** `ET.indent(tree)`, two spaces a level: an element with children gets a
 *  newline and its children's indentation as text, and each child the same
 *  as tail, the last one dedented back to its parent's. */
function indent(tree: El): void {
  if (!tree.children.length) return
  const at = (level: number): string => `\n${'  '.repeat(level)}`
  const indentChildren = (e: El, level: number): void => {
    const inner = at(level + 1)
    if (!e.text || !e.text.trim()) e.text = inner
    for (const child of e.children) {
      if (child.children.length) indentChildren(child, level + 1)
      if (!child.tail || !child.tail.trim()) child.tail = inner
    }
    const last = e.children[e.children.length - 1]
    if (!last.tail.trim()) last.tail = at(level)
  }
  indentChildren(tree, 0)
}
