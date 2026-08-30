/**
 * The geometry module — what an arrow and a label do once the boxes are placed.
 *
 * Every Excalidraw-backed application ends up answering the same three
 * questions once its boxes are on the sheet: where does an arrow between two
 * boxes go, how does an arrow the user bent survive the boxes moving, and how
 * does a label stay legible. This module holds the primitives every
 * application needs to answer them — box arithmetic, which face an arrow
 * leaves and arrives on, a bent route remembered as a SHAPE rather than a
 * place, an arrow's kind read out of Excalidraw's two unrelated fields, and
 * greedy word-wrap to a column budget. The layout ENGINE — where a box goes,
 * how a route is chosen among several — stays with the application; this
 * module is what the engine is built out of.
 *
 * `geometry` is the lowest module in this package: `stencils` imports its box
 * arithmetic rather than carrying its own copy.
 *
 * Words:
 * - a BOX is `{x, y, width, height}`, Excalidraw's own field names, so an
 *   element structurally IS a box;
 * - a FACE is `left | right | top | bottom`, a side of a box;
 * - an ANCHOR is where an arrow meets a box, as unit fractions `{u, v}` of
 *   its width and height — deliberately unclamped, so a point just outside
 *   the box says so;
 * - a BEND is a route's interior point as `{t, d}`: `t` the fraction along
 *   the chord from anchor to anchor, `d` the perpendicular offset. A route
 *   with no bends is a straight line;
 * - the KIND of an arrow is `sharp | curved | elbow`, one word for
 *   Excalidraw's two fields;
 * - the CHORD is the segment between an arrow's two anchors.
 *
 * The last section — `normalizeBoundArrows` and `topAlignCrowdedLabels` — is
 * TypeScript only. It is the pass a sketch application runs in the browser
 * between a model's reply and `convertToExcalidrawElements`; no server has a
 * use for it today, so no Python twin exists for it.
 *
 * Nothing here depends on Excalidraw or the DOM. Points are `[x, y]` pairs,
 * Excalidraw's own shape, except where a function's own reference
 * implementation used `{x, y}` — each such case says so in its doc comment.
 */

export interface Box { x: number; y: number; width: number; height: number }
export type Point = readonly [number, number]

// Loosely typed on purpose, like `stencils.ts`'s `Element`: an element is
// whatever JSON an application feeds its canvas, and pinning every field
// would turn a malformed skeleton into a compile error instead of a passthrough.
export type Element = Record<string, unknown>

function num(v: unknown, fallback = 0): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback
}

// --- boxes ---------------------------------------------------------------------

/** An element's box. A linear element (line, arrow, freedraw) keeps its
 *  origin at its FIRST point and its points relative to it, so a stroke drawn
 *  right-to-left has an origin at its right end and points that run negative;
 *  its box starts at the least point, not at the origin. Reading `x` as the
 *  left edge is how a hand-drawn symbol got a frame a stroke's width off. */
export function boxOf(el: Element): Box {
  let x = num(el.x)
  let y = num(el.y)
  if (Array.isArray(el.points) && el.points.length) {
    let minX = Infinity
    let minY = Infinity
    for (const p of el.points as unknown[]) {
      if (Array.isArray(p) && p.length >= 2) {
        minX = Math.min(minX, num(p[0]))
        minY = Math.min(minY, num(p[1]))
      }
    }
    if (Number.isFinite(minX)) x += minX
    if (Number.isFinite(minY)) y += minY
  }
  return { x, y, width: num(el.width), height: num(el.height) }
}

/** The box enclosing every box given, or `null` for none. Takes boxes rather
 *  than elements — `union(boxes.map(boxOf))` is the element-list version an
 *  application reaches for when it has a mix of shapes and text. */
export function union(boxes: readonly Box[]): Box | null {
  if (!boxes.length) return null
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity
  for (const b of boxes) {
    x1 = Math.min(x1, b.x)
    y1 = Math.min(y1, b.y)
    x2 = Math.max(x2, b.x + b.width)
    y2 = Math.max(y2, b.y + b.height)
  }
  return { x: x1, y: y1, width: x2 - x1, height: y2 - y1 }
}

/** The centre point of a box. */
export function centre(box: Box): Point {
  return [box.x + box.width / 2, box.y + box.height / 2]
}

/** Whether a point sits inside a box, edges inclusive — a dropped box counts
 *  as landing in the zone whose border it is dragged onto. */
export function contains(box: Box, point: Point): boolean {
  return (
    point[0] >= box.x && point[0] <= box.x + box.width &&
    point[1] >= box.y && point[1] <= box.y + box.height
  )
}

/** Whether two boxes share any area. Boxes that only touch — a shared edge or
 *  a shared corner — do NOT overlap; the strict inequalities are what let two
 *  arranged rows sit flush against each other without tripping a collision. */
export function overlap(a: Box, b: Box): boolean {
  return (
    a.x < b.x + b.width && b.x < a.x + a.width &&
    a.y < b.y + b.height && b.y < a.y + a.height
  )
}

/** A box's area. */
export function area(box: Box): number {
  return box.width * box.height
}

// --- faces and anchors -----------------------------------------------------------

export type Side = 'left' | 'right' | 'top' | 'bottom'

/** Which face of `a` and which face of `b` an arrow between them should
 *  leave and arrive on. Whichever axis separates the centres MORE decides, so
 *  an arrow leaves and arrives where a reader expects rather than cutting a
 *  corner; a tie (equal separation on both axes) goes to the horizontal
 *  axis, since `dx` is compared with `>=`. */
export function facingSides(a: Box, b: Box): [Side, Side] {
  const [acx, acy] = centre(a)
  const [bcx, bcy] = centre(b)
  const dx = bcx - acx
  const dy = bcy - acy
  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx >= 0 ? ['right', 'left'] : ['left', 'right']
  }
  return dy >= 0 ? ['bottom', 'top'] : ['top', 'bottom']
}

/** The point a fraction `t` of the way along one face of a box, `t=0` at the
 *  face's first corner in reading order (top: left→right, bottom: left→right,
 *  left: top→bottom, right: top→bottom). */
export function pointOnSide(box: Box, side: Side, t: number): Point {
  if (side === 'top') return [box.x + box.width * t, box.y]
  if (side === 'bottom') return [box.x + box.width * t, box.y + box.height]
  if (side === 'left') return [box.x, box.y + box.height * t]
  return [box.x + box.width, box.y + box.height * t]
}

/** Where a box sits along the axis a face SPREADS on — the sort key for
 *  several arrows sharing one face. A `top`/`bottom` face spreads along x, so
 *  the key is the other box's x-centre; a `left`/`right` face spreads along
 *  y, so it is the other box's y-centre. Sorting a face's arrivals by this is
 *  what keeps them from crossing each other in the last few pixels before
 *  they land. */
export function along(other: Box, side: Side): number {
  const [cx, cy] = centre(other)
  return side === 'top' || side === 'bottom' ? cx : cy
}

/** A point as unit fractions of a box's width and height — the endpoint half
 *  of shape memory (GMF's IdentityAnchor, Excalidraw's own `fixedPoint` for
 *  elbow arrows). Deliberately NOT clamped to the box: an arrow's end often
 *  sits a hair off the face it meets, and rounding it onto the face would
 *  move the line the user drew. Reading a point and writing it back with
 *  `anchorXY` is then exactly the identity. A zero-sized box reads as
 *  1&nbsp;px wide/tall rather than dividing by zero. */
export function anchorUV(point: Point, box: Box): { u: number; v: number } {
  const w = box.width || 1
  const h = box.height || 1
  return { u: (point[0] - box.x) / w, v: (point[1] - box.y) / h }
}

/** That fraction back on the box, wherever the box now is. */
export function anchorXY(uv: { u: number; v: number }, box: Box): Point {
  return [box.x + uv.u * box.width, box.y + uv.v * box.height]
}

/** The fraction along a centre-to-centre segment `(dx, dy)` at which it exits
 *  `box`'s bounding box, measured from the box's own centre. Used to trim a
 *  centre-to-centre line back to the box's edge without ever computing an
 *  intersection: the smaller of how far the segment can travel before it
 *  clears the box horizontally or vertically. */
export function exitT(box: Box, dx: number, dy: number): number {
  const tx = dx === 0 ? Infinity : box.width / 2 / Math.abs(dx)
  const ty = dy === 0 ? Infinity : box.height / 2 / Math.abs(dy)
  return Math.min(tx, ty)
}

/** The segment between two boxes' centres, trimmed `gap` px outside each —
 *  the shape whose binding focus Excalidraw derives is exactly 0. When the
 *  boxes overlap or nest, there is no sane trim (the exit points cross or the
 *  centres coincide): the raw centre-to-centre line is returned instead, on
 *  the same reasoning as the twins' own phase-3 fallback — the binding focus
 *  is still 0, and Excalidraw re-routes it on the next move regardless. */
export function centreSegment(a: Box, b: Box, gap: number): { x1: number; y1: number; x2: number; y2: number } {
  const [ax, ay] = centre(a)
  const [bx, by] = centre(b)
  const dx = bx - ax
  const dy = by - ay
  const len = Math.hypot(dx, dy)
  if (len < 1) {
    return { x1: ax, y1: ay, x2: bx, y2: by }
  }
  let t0 = exitT(a, dx, dy) + gap / len
  let t1 = 1 - exitT(b, dx, dy) - gap / len
  if (!(t0 < t1)) {
    t0 = 0
    t1 = 1
  }
  return { x1: ax + dx * t0, y1: ay + dy * t0, x2: ax + dx * t1, y2: ay + dy * t1 }
}

// --- shape memory ------------------------------------------------------------
//
// A hand-drawn bend used to be stored as absolute sheet coordinates, which
// made it a statement about the page rather than about the arrow. Move
// either box and those coordinates describe a line that no longer reaches
// its own endpoints. Each interior point is stored instead as `{t, d}`
// against the segment between the arrow's two ANCHORS: `t` the fraction
// along it, `d` the signed perpendicular offset in pixels — Eclipse GMF's
// RelativeBendpoints idea, in the simpler of its two forms. The endpoints
// themselves are never stored: they are always the anchors the router just
// computed, refitted between them on every draw.

export interface Bend { t: number; d: number }

/** A route's interior points, expressed relative to its own chord (first
 *  point to last). A route with fewer than three points, or whose two ends
 *  coincide (a zero-length chord — nothing to measure `t`/`d` against), has
 *  nothing to remember. */
export function relativeBends(points: readonly Point[]): Bend[] {
  if (points.length < 3) return []
  const [ax, ay] = points[0]
  const [bx, by] = points[points.length - 1]
  const vx = bx - ax
  const vy = by - ay
  const length = Math.hypot(vx, vy)
  if (length < 1e-6) return []
  const out: Bend[] = []
  for (const [px, py] of points.slice(1, -1)) {
    const wx = px - ax
    const wy = py - ay
    out.push({
      t: (wx * vx + wy * vy) / (length * length),
      d: (vx * wy - vy * wx) / length,
    })
  }
  return out
}

/** The route those bends describe, refitted between live anchors `a` and
 *  `b`. With no bends this is just the straight segment `[a, b]`; with `a`
 *  and `b` coincident there is no chord to lay the bends against, so the
 *  route degenerates to the two (equal) endpoints. */
export function absoluteRoute(bends: readonly Bend[], a: Point, b: Point): Point[] {
  const [ax, ay] = a
  const [bx, by] = b
  const vx = bx - ax
  const vy = by - ay
  const length = Math.hypot(vx, vy)
  if (length < 1e-6) return [[ax, ay], [bx, by]]
  const nx = -vy / length
  const ny = vx / length
  const points: Point[] = [[ax, ay]]
  for (const { t, d } of bends) {
    points.push([ax + t * vx + d * nx, ay + t * vy + d * ny])
  }
  points.push([bx, by])
  return points
}

export type ArrowKind = 'sharp' | 'curved' | 'elbow'

/** Which of the toolbox's three arrow types an element is drawn as.
 *  Excalidraw splits sharp/curved/elbow across two unrelated fields — an
 *  elbow arrow is `elbowed`, a curved one carries a `roundness` — which is a
 *  shape that cannot be stored, compared, or handed to a renderer. Read into
 *  one word here; `elbowed` wins when both are set, since an elbow arrow
 *  keeps whatever stale `roundness` an earlier type left behind. */
export function arrowKind(element: Element): ArrowKind {
  if (element.elbowed) return 'elbow'
  return element.roundness ? 'curved' : 'sharp'
}

/** The two fields Excalidraw wants for a given kind — the write side of
 *  `arrowKind`. Sharp is what the app itself draws when nothing was chosen,
 *  and what an older geometry says by saying nothing; `elbowed` is present
 *  (and `true`) only for an elbow, never `false` — the renderer spreads this
 *  object in, and a present-but-false key is not the same as an absent one
 *  to code that checks `'elbowed' in element`. */
export function arrowFields(kind: ArrowKind): { roundness: { type: 2 } | null; elbowed?: true } {
  if (kind === 'curved') return { roundness: { type: 2 } }
  if (kind === 'elbow') return { roundness: null, elbowed: true }
  return { roundness: null }
}

/** An arrow element's `x`, `y`, `width`, `height` and `points` from its
 *  absolute route. Excalidraw wants points relative to the element's own
 *  origin, and the box is the EXTENT of the point cloud, not a box ending at
 *  the last point — an elbow that doubles back on itself would otherwise be
 *  handed a negative width or height and render as a straight line through
 *  the corner it was meant to turn. The origin is always the route's first
 *  point, matching `boxOf`'s rule for a linear element. */
export function arrowElement(
  points: readonly Point[],
): { x: number; y: number; width: number; height: number; points: Point[] } {
  const [sx, sy] = points[0]
  const rel: Point[] = points.map(([x, y]) => [x - sx, y - sy])
  const xs = rel.map((p) => p[0])
  const ys = rel.map((p) => p[1])
  return {
    x: sx,
    y: sy,
    width: Math.max(...xs) - Math.min(...xs),
    height: Math.max(...ys) - Math.min(...ys),
    points: rel,
  }
}

// --- labels ------------------------------------------------------------------

/** One line cut to `cols` characters with a trailing ellipsis. A line
 *  already at or over the budget loses its last character to make room for
 *  the mark; a shorter line simply gets it appended. */
export function ellipsise(line: string, cols: number): string {
  return line.length >= cols ? line.slice(0, cols - 1) + '…' : line + '…'
}

/** Greedy word wrap to `cols` characters per line, capped at `maxLines` with
 *  an ellipsis on the last line when the text does not fit. A word longer
 *  than the budget on its own is cut to fit, with its own ellipsis, rather
 *  than being pushed whole onto an overflowing line. */
export function wrap(text: string, cols: number, maxLines: number): string[] {
  const words = (text || '').trim().split(/\s+/).filter(Boolean)
  const lines: string[] = []
  let line = ''
  for (const raw of words) {
    const word = raw.length > cols ? raw.slice(0, cols - 1) + '…' : raw
    const next = line ? `${line} ${word}` : word
    if (next.length <= cols) {
      line = next
      continue
    }
    lines.push(line)
    if (lines.length === maxLines) {
      lines[maxLines - 1] = ellipsise(lines[maxLines - 1], cols)
      return lines
    }
    line = word
  }
  if (line) {
    if (lines.length < maxLines) lines.push(line)
    else lines[maxLines - 1] = ellipsise(lines[maxLines - 1], cols)
  }
  return lines
}

/** The first `maxWords` words of `text`, with a trailing ellipsis appended
 *  (as its own word, not fused onto the last one) when there were more. The
 *  full text is never lost — this is only ever what gets DRAWN. */
export function terse(text: string, maxWords: number): string {
  const words = (text || '').trim().split(/\s+/).filter(Boolean)
  if (!words.length) return ''
  const kept = words.slice(0, maxWords).join(' ')
  return words.length > maxWords ? `${kept}…` : kept
}

/** How many lines `wrap` would produce for `text` at `cols`, uncapped — what
 *  a server needs to size a label's box before the client ever draws it.
 *  Defined as `wrap`'s own line count (rather than as an independent
 *  character-counting loop) so the two can never drift apart the way the
 *  Bastion's Python `_text_lines` and TypeScript `wrapLabel` did: `_text_lines`
 *  undercounts an empty string as one line where `wrap` draws none, and
 *  overcounts a single word longer than the budget as two lines because it
 *  never accounts for that word being cut to fit on one. */
export function lineCount(text: string, cols: number): number {
  return wrap(text, cols, Number.MAX_SAFE_INTEGER).length
}

// --- the skeleton pipeline — TypeScript only ------------------------------------
//
// `normalizeBoundArrows` and `topAlignCrowdedLabels` are the Armory's and the
// Academy's byte-identical twin passes, moved here unchanged in behaviour.
// They run in the browser between a model's reply and
// `convertToExcalidrawElements`; nothing on the server has a use for them, so
// there is no Python twin.

export interface NormalizeOptions {
  /** px between a shape's edge and an arrow's tip. */
  gap?: number
  /** px between parallel arrows sharing an endpoint pair. */
  spread?: number
  /** px an arrow is pushed past a box it would otherwise cross. */
  clear?: number
  /** px kept between two arrows' label anchors. */
  minSeparation?: number
  /** the size assumed for a skeleton shape with no declared width/height —
   *  must match whatever `convertToExcalidrawElements` itself stubs in. */
  defaultDimension?: number
}

const NOT_BINDABLE = new Set(['arrow', 'line', 'freedraw'])

function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

interface InternalBox { x: number; y: number; w: number; h: number }

function internalBoxOf(raw: unknown, defaultDimension: number): { id: string; box: InternalBox } | null {
  if (!raw || typeof raw !== 'object') return null
  const e = raw as Record<string, unknown>
  if (e.isDeleted) return null
  const id = e.id
  const type = e.type
  if (typeof id !== 'string' || typeof type !== 'string') return null
  if (NOT_BINDABLE.has(type)) return null
  if (!isNum(e.x) || !isNum(e.y)) return null
  return {
    id,
    box: {
      x: e.x,
      y: e.y,
      w: isNum(e.width) ? e.width : defaultDimension,
      h: isNum(e.height) ? e.height : defaultDimension,
    },
  }
}

function boundId(v: unknown): string | null {
  if (!v || typeof v !== 'object') return null
  const id = (v as Record<string, unknown>).id
  return typeof id === 'string' ? id : null
}

/** Liang-Barsky: does the segment `(x1,y1)→(x2,y2)` meet box `b`? */
function segmentMeetsBox(x1: number, y1: number, x2: number, y2: number, b: InternalBox): boolean {
  let t0 = 0
  let t1 = 1
  const dx = x2 - x1
  const dy = y2 - y1
  const p = [-dx, dx, -dy, dy]
  const q = [x1 - b.x, b.x + b.w - x1, y1 - b.y, b.y + b.h - y1]
  for (let i = 0; i < 4; i++) {
    if (p[i] === 0) {
      if (q[i] < 0) return false
      continue
    }
    const r = q[i] / p[i]
    if (p[i] < 0) {
      if (r > t1) return false
      if (r > t0) t0 = r
    } else {
      if (r < t0) return false
      if (r < t1) t1 = r
    }
  }
  return true
}

function internalExitT(b: InternalBox, dx: number, dy: number): number {
  const tx = dx === 0 ? Infinity : b.w / 2 / Math.abs(dx)
  const ty = dy === 0 ? Infinity : b.h / 2 / Math.abs(dy)
  return Math.min(tx, ty)
}

/** Rewrite every arrow skeleton bound at BOTH ends to shapes with known
 *  geometry — looked up in `skeletons` itself, then `board` (skeletons win)
 *  — so its points run edge-to-edge along the centre-to-centre line. Arrows
 *  sharing an endpoint pair are fanned onto parallel offset lines; a segment
 *  that would cross a third box is pushed clear of it; two arrows whose
 *  label anchors would land too close are pushed apart. Anything that
 *  cannot be routed — a binding to a non-bindable type, a missing endpoint,
 *  coincident shapes — passes through untouched (a poisonous binding to a
 *  line/arrow/freedraw is stripped first, since a binding to one of those
 *  makes `convertToExcalidrawElements` throw and loses the whole batch).
 *  Never mutates `skeletons` or `board`. */
export function normalizeBoundArrows(
  skeletons: readonly unknown[],
  board: readonly unknown[],
  options?: NormalizeOptions,
): unknown[] {
  const gap = options?.gap ?? 6
  const spread = options?.spread ?? 48
  const clear = options?.clear ?? 20
  const minSeparation = options?.minSeparation ?? 48
  const defaultDimension = options?.defaultDimension ?? 100

  const geo = new Map<string, InternalBox>()
  const unbindable = new Set<string>()
  for (const el of [...board, ...skeletons]) {
    const got = internalBoxOf(el, defaultDimension)
    if (got) geo.set(got.id, got.box)
    if (el && typeof el === 'object') {
      const t = el as Record<string, unknown>
      if (typeof t.id === 'string' && typeof t.type === 'string' && NOT_BINDABLE.has(t.type)) {
        unbindable.add(t.id)
      }
    }
  }

  // Arrows sharing the same UNORDERED endpoint pair would all ride the same
  // centre-to-centre line — stacked dead on top of each other, labels
  // garbled. Fan each such group onto parallel offset lines.
  const pairIndexes = new Map<string, number[]>()
  skeletons.forEach((raw, i) => {
    if (!raw || typeof raw !== 'object') return
    const e = raw as Record<string, unknown>
    if (e.type !== 'arrow') return
    const s = boundId(e.start)
    const t = boundId(e.end)
    if (!s || !t || !geo.has(s) || !geo.has(t)) return
    const key = [s, t].sort().join('\u0000')
    const got = pairIndexes.get(key)
    if (got) got.push(i)
    else pairIndexes.set(key, [i])
  })
  const fan = new Map<number, { ox: number; oy: number }>()
  for (const [key, idxs] of pairIndexes) {
    if (idxs.length < 2) continue
    const [p, q] = key.split('\u0000')
    const a = geo.get(p)!
    const b = geo.get(q)!
    const dx = b.x + b.w / 2 - (a.x + a.w / 2)
    const dy = b.y + b.h / 2 - (a.y + a.h / 2)
    const len = Math.hypot(dx, dy)
    if (len < 1) continue
    const px = -dy / len
    const py = dx / len
    const halfA = (a.w / 2) * Math.abs(px) + (a.h / 2) * Math.abs(py)
    const halfB = (b.w / 2) * Math.abs(px) + (b.h / 2) * Math.abs(py)
    const maxOff = Math.max(0, Math.min(halfA, halfB) - 10)
    const step = Math.min(spread, (2 * maxOff) / (idxs.length - 1))
    idxs.forEach((idx, k) => {
      const d = (k - (idxs.length - 1) / 2) * step
      fan.set(idx, { ox: px * d, oy: py * d })
    })
  }

  // Phase 1 — route every both-ends-bound arrow: fan offset, then obstacle
  // avoidance.
  type Routed = { e: Record<string, unknown>; a: InternalBox; b: InternalBox; ax: number; ay: number; bx: number; by: number }
  const routed = new Map<number, Routed>()
  const passthrough = new Map<number, unknown>()
  skeletons.forEach((raw, idx) => {
    if (!raw || typeof raw !== 'object') return
    let e = raw as Record<string, unknown>
    if (e.type !== 'arrow') return
    const sId = boundId(e.start)
    const tId = boundId(e.end)
    if ((sId && unbindable.has(sId)) || (tId && unbindable.has(tId))) {
      e = { ...e }
      if (sId && unbindable.has(sId)) delete e.start
      if (tId && unbindable.has(tId)) delete e.end
    }
    const a = geo.get(boundId(e.start) ?? '')
    const b = geo.get(boundId(e.end) ?? '')
    if (!a || !b) {
      passthrough.set(idx, e)
      return
    }
    const off = fan.get(idx) ?? { ox: 0, oy: 0 }
    let ax = a.x + a.w / 2 + off.ox
    let ay = a.y + a.h / 2 + off.oy
    let bx = b.x + b.w / 2 + off.ox
    let by = b.y + b.h / 2 + off.oy
    const dx = bx - ax
    const dy = by - ay
    const len = Math.hypot(dx, dy)
    if (len < 1) {
      passthrough.set(idx, e)
      return
    }

    // Route AROUND intermediate shapes: shift the whole segment perpendicular
    // just far enough to clear every box it crosses, capped so both ends stay
    // attached to their own shapes.
    {
      const px = -dy / len
      const py = dx / len
      const sIdNow = boundId(e.start)
      const tIdNow = boundId(e.end)
      let needPlus = 0
      let needMinus = 0
      for (const [gid, g] of geo) {
        if (gid === sIdNow || gid === tIdNow) continue
        if (!segmentMeetsBox(ax, ay, bx, by, g)) continue
        const d = (g.x + g.w / 2 - ax) * px + (g.y + g.h / 2 - ay) * py
        const req = (g.w / 2) * Math.abs(px) + (g.h / 2) * Math.abs(py) + clear
        needPlus = Math.max(needPlus, d + req)
        needMinus = Math.max(needMinus, req - d)
      }
      if (needPlus > 0 || needMinus > 0) {
        const capA = (a.w / 2) * Math.abs(px) + (a.h / 2) * Math.abs(py)
        const capB = (b.w / 2) * Math.abs(px) + (b.h / 2) * Math.abs(py)
        const cap = Math.max(0, Math.min(capA, capB) - 6)
        const delta = needPlus <= needMinus ? Math.min(needPlus, cap) : -Math.min(needMinus, cap)
        ax += px * delta
        ay += py * delta
        bx += px * delta
        by += py * delta
      }
    }
    routed.set(idx, { e, a, b, ax, ay, bx, by })
  })

  // Phase 2 — midpoint separation: a bound label always sits at its arrow's
  // midpoint, so two crossing arrows type their labels over each other even
  // though the lines themselves read fine.
  const anchorOf = (r: Routed): [number, number] => {
    const dx = r.bx - r.ax
    const dy = r.by - r.ay
    const len = Math.hypot(dx, dy)
    let t0 = internalExitT(r.a, dx, dy) + gap / len
    let t1 = 1 - internalExitT(r.b, dx, dy) - gap / len
    if (!(t0 < t1)) {
      t0 = 0
      t1 = 1
    }
    const tm = (t0 + t1) / 2
    return [r.ax + dx * tm, r.ay + dy * tm]
  }
  const keys = [...routed.keys()].sort((m, n) => m - n)
  for (let i = 0; i < keys.length; i++) {
    for (let j = i + 1; j < keys.length; j++) {
      const A = routed.get(keys[i])!
      const B = routed.get(keys[j])!
      const [amx, amy] = anchorOf(A)
      const [bmx, bmy] = anchorOf(B)
      const dxm = bmx - amx
      const dym = bmy - amy
      const dist = Math.hypot(dxm, dym)
      if (dist >= minSeparation) continue
      const dlen = Math.hypot(B.bx - B.ax, B.by - B.ay)
      if (dlen < 1) continue
      const px = -(B.by - B.ay) / dlen
      const py = (B.bx - B.ax) / dlen
      const proj = Math.abs(dxm * px + dym * py)
      const side = dxm * px + dym * py >= 0 ? 1 : -1
      const needed = Math.sqrt(Math.max(0, proj * proj + minSeparation * minSeparation - dist * dist)) - proj + 2
      const capA = (B.a.w / 2) * Math.abs(px) + (B.a.h / 2) * Math.abs(py)
      const capB = (B.b.w / 2) * Math.abs(px) + (B.b.h / 2) * Math.abs(py)
      const cap = Math.max(0, Math.min(capA, capB) - 6)
      const delta = side * Math.min(needed, cap)
      B.ax += px * delta
      B.ay += py * delta
      B.bx += px * delta
      B.by += py * delta
    }
  }

  // Phase 3 — emit, trimming each routed segment to just outside its two
  // shapes' bounding boxes.
  return skeletons.map((raw, idx) => {
    const r = routed.get(idx)
    if (!r) return passthrough.get(idx) ?? raw
    const { e, a, b, ax, ay, bx, by } = r
    const dx = bx - ax
    const dy = by - ay
    const len = Math.hypot(dx, dy)
    let t0 = internalExitT(a, dx, dy) + gap / len
    let t1 = 1 - internalExitT(b, dx, dy) - gap / len
    if (!(t0 < t1)) {
      // Overlapping/nested shapes: fall back to the raw centre line; the
      // binding focus is still 0 and Excalidraw re-routes on any move.
      t0 = 0
      t1 = 1
    }
    const sx = ax + dx * t0
    const sy = ay + dy * t0
    const ex = ax + dx * t1
    const ey = ay + dy * t1
    return {
      ...e,
      x: sx,
      y: sy,
      width: Math.abs(ex - sx),
      height: Math.abs(ey - sy),
      points: [[0, 0], [ex - sx, ey - sy]],
    }
  })
}

/** Shapes whose label rides inside them; free elements of these types sitting
 *  inside such a shape crowd a middle-aligned label into garble. */
const LABELLED = new Set(['rectangle', 'ellipse', 'diamond'])
const CROWDING = new Set(['text', 'rectangle', 'ellipse', 'diamond', 'image'])

/** A labelled shape's name defaults to the vertical CENTRE of the box — the
 *  moment another element is drawn inside that box, name and content garble
 *  each other. Top-align the label of any shape that contains another
 *  element (or a pending stencil placement, which is about to become one),
 *  unless the author pinned `verticalAlign` explicitly. Never mutates
 *  `skeletons`. */
export function topAlignCrowdedLabels(skeletons: readonly unknown[]): unknown[] {
  return skeletons.map((raw) => {
    if (!raw || typeof raw !== 'object') return raw
    const e = raw as Record<string, unknown>
    const label = e.label as Record<string, unknown> | undefined
    if (
      typeof e.type !== 'string' || !LABELLED.has(e.type) ||
      !label || typeof label !== 'object' || label.verticalAlign ||
      !isNum(e.x) || !isNum(e.y) || !isNum(e.width) || !isNum(e.height)
    ) {
      return raw
    }
    const crowded = skeletons.some((other) => {
      if (other === raw || !other || typeof other !== 'object') return false
      const o = other as Record<string, unknown>
      const isStamp = typeof o.stencil === 'string'
      if (!isStamp && (typeof o.type !== 'string' || !CROWDING.has(o.type))) return false
      if (!isNum(o.x) || !isNum(o.y)) return false
      const cx = o.x + (isNum(o.width) ? o.width / 2 : 0)
      const cy = o.y + (isNum(o.height) ? o.height / 2 : 0)
      return (
        cx > (e.x as number) && cx < (e.x as number) + (e.width as number) &&
        cy > (e.y as number) && cy < (e.y as number) + (e.height as number)
      )
    })
    if (!crowded) return raw
    return { ...e, label: { ...label, verticalAlign: 'top' } }
  })
}
