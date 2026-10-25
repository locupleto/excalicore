/**
 * The elements module — complete Excalidraw elements, built without a canvas.
 *
 * Excalidraw makes an element complete when the user draws it: an id, a seed
 * for the rough renderer, version counters, the style fields, and — for the
 * shapes that hold text or take an arrow — the two-way references that keep a
 * label in its box and an arrow on its shape. A server that draws for a person
 * (an agent adding a box, a script sketching a flow) has no canvas to do that,
 * and an element missing any of it fails quietly: a field Excalidraw expects as
 * `null` arrives as `undefined`, a label detaches, an arrow floats free of the
 * box it was bound to.
 *
 * This module builds elements that are complete in that sense and keeps the
 * references consistent when they change:
 *
 * - base fields (`baseElement`) and the four builders on top of it:
 *   `textElement`, `shapeElement` (rectangle, ellipse, diamond), `frameElement`
 *   and `linearElement` (arrow, line);
 * - text: `measureText` and `wrapText` estimate what the canvas will measure
 *   exactly once the text is edited (a server has no font metrics), and a text
 *   can be centred and wrapped inside a container;
 * - labels: `addLabel` binds a text into a box BOTH ways (`containerId` on the
 *   text, a `text` entry in the box's `boundElements`) and grows the box to hold
 *   it; `fitLabel` keeps it centred after the box moves;
 * - arrows: `routeBetween` finds an arrow's route from the boxes at its ends,
 *   `bindEnd` binds an end to a shape both ways, `refitArrow` puts bound ends
 *   back on their shapes' edges after a shape moved, and `detach` removes an
 *   element without leaving a dangling reference.
 *
 * Built on `geometry` — the box arithmetic, the route-to-element conversion and
 * the exit point of a ray from a box. The mutating functions change the objects
 * they are given and RETURN the other elements they changed, so the caller can
 * store exactly those; they do not bump `version`, because only the caller
 * knows whether an element already exists on a canvas (use `touch`).
 *
 * The module has no opinion about what the elements mean, which colours or
 * fonts to use, or how roughness is chosen: those are parameters. Plain
 * functions over plain objects — no I/O, no DOM, no Excalidraw import.
 *
 * This is the twin of `excalicore.elements` (Python), held to it by
 * `corpus/elements/`. Three places where JavaScript differs from Python are
 * handled on purpose, so the two return the same numbers:
 *
 * - Python's `round(x, 2)` is correctly rounded with ties to even; `toFixed`
 *   and `Math.round` are not (`roundTo2`);
 * - Python's `sum()` of floats is compensated since 3.12 (`pySum`), and its
 *   strings count codepoints, not UTF-16 units, so every length and slice of
 *   text here goes by codepoint;
 * - Python reads a glyph's East Asian Width from `unicodedata`; `fontmetrics`
 *   carries Python's table of wide ranges (`isWide`). A glyph Unicode added
 *   after the Python used to generate that table is read as narrow.
 *
 * Ids, seeds, version nonces and timestamps come from a source that a caller
 * may replace (`setSource`), so the same scene can be rendered identically
 * every time.
 */

import { arrowElement, boxOf, centre, exitT } from './geometry.ts'
import type { Box } from './geometry.ts'
import { ADVANCE, METRICS, isWide } from './fontmetrics.ts'

// --- Excalidraw's vocabulary ---------------------------------------------------------

export const SHAPES = ['rectangle', 'ellipse', 'diamond'] as const
export const LINEAR = ['arrow', 'line'] as const
/** What an arrow may bind to. */
export const BINDABLE = ['rectangle', 'ellipse', 'diamond', 'text', 'frame'] as const
/** Every kind this module builds. */
export const KINDS = ['text', ...SHAPES, ...LINEAR, 'frame'] as const
export const ARROWHEADS = [
  'arrow', 'bar', 'dot', 'circle', 'circle_outline', 'triangle',
  'triangle_outline', 'diamond', 'diamond_outline', 'crowfoot_one',
  'crowfoot_many', 'crowfoot_one_or_many',
] as const
export const STROKE_STYLES = ['solid', 'dashed', 'dotted'] as const

/** Excalidraw's font family ids (`constants.FONT_FAMILY`). */
export const FONT_VIRGIL = 1
export const FONT_HELVETICA = 2
export const FONT_CASCADIA = 3
export const FONT_EXCALIFONT = 5
export const FONT_NUNITO = 6
/** Unitless line height by font family, as Excalidraw's font metadata has it. */
export const LINE_HEIGHT: Readonly<Record<number, number>> = {
  [FONT_VIRGIL]: 1.25,
  [FONT_HELVETICA]: 1.15,
  [FONT_CASCADIA]: 1.2,
  [FONT_EXCALIFONT]: 1.25,
  [FONT_NUNITO]: 1.35,
}
export const DEFAULT_LINE_HEIGHT = 1.25

/** Excalidraw's own default stroke colour. */
export const INK = '#1e1e1e'
/** Excalidraw's frame outline (`FRAME_STYLE.strokeColor`). */
export const FRAME_INK = '#bbb'
export const FONT_SIZE = 20 // Excalidraw's DEFAULT_FONT_SIZE
export const PADDING = 5 // Excalidraw's BOUND_TEXT_PADDING
export const BIND_GAP = 4.0 // an arrow's end stands this far off its shape
/** The flat glyph width (a fraction of the font size) the estimate used before
 *  per-glyph widths: kept as the floor of an empty text and an opt-in `charEm`. */
export const CHAR_EM = 0.55

const ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-'

/** An element, as a plain object. Excalidraw's elements are open records (an
 *  application adds its own `customData`), so the fields are not typed here. */
export type El = Record<string, any>
export type Pt = [number, number]
/** Elements by id. */
export type ById = Readonly<Record<string, El>>

const has = (o: object, key: string): boolean => Object.hasOwn(o, key)

// --- small things ---------------------------------------------------------------------

/** Where ids, nonces and timestamps come from. */
export interface Source {
  /** A new element id. */
  id?: () => string
  /** A `seed` or `versionNonce`. */
  nonce?: () => number
  /** Epoch milliseconds, as an element's `updated`. */
  now?: () => number
}

/** The Web Crypto random source, present in every browser and in Node 19+.
 *  Declared here because the build compiles without DOM or Node types. */
const webCrypto = (globalThis as unknown as { crypto: { getRandomValues<T extends ArrayBufferView>(a: T): T } }).crypto

function defaultId(): string {
  const bytes = new Uint8Array(21)
  webCrypto.getRandomValues(bytes)
  // 64 letters, 256 bytes: the low six bits are uniform.
  return Array.from(bytes, (b) => ALPHABET[b & 63]).join('')
}

function defaultNonce(): number {
  const word = new Uint32Array(1)
  for (;;) {
    webCrypto.getRandomValues(word)
    const n = word[0] >>> 1 // 0 .. 2^31 - 1, uniform
    if (n > 0) return n
  }
}

const defaultNow = (): number => Date.now()

let source: Required<Source> = { id: defaultId, nonce: defaultNonce, now: defaultNow }

/**
 * Replace where `newId`, `nonce` and `nowMs` get their values, so a caller can
 * render the same scene identically every time (fixed seeds). Each is a
 * zero-argument function; one left out gets its default back, so
 * `setSource()` restores all three. Every call replaces the whole source —
 * to change one and keep another, pass both.
 */
export function setSource(next: Source = {}): void {
  source = {
    id: next.id ?? defaultId,
    nonce: next.nonce ?? defaultNonce,
    now: next.now ?? defaultNow,
  }
}

/** An id the way Excalidraw makes them: 21 characters of nanoid's alphabet. */
export function newId(): string {
  return source.id()
}

/** A `seed` or `versionNonce`: a random positive 31-bit integer. */
export function nonce(): number {
  return source.nonce()
}

/** Epoch milliseconds, as an element's `updated`. */
export function nowMs(): number {
  return source.now()
}

/** Record that an existing element changed: `version` up by one, a fresh
 *  `versionNonce`, a new `updated`. Excalidraw reconciles by these, so an
 *  edit made without them can be discarded as stale. Returns the element. */
export function touch(element: El): El {
  element.version = Math.trunc(Number(element.version || 0)) + 1
  element.versionNonce = nonce()
  element.updated = nowMs()
  return element
}

// --- numbers the way Python does them ---------------------------------------------------

/** Python's `round(x, 2)`: the double's exact decimal value rounded to the
 *  nearest hundredth, an exact tie going to the even one. (`toFixed` rounds
 *  ties up; `Math.round(x * 100) / 100` also sees ties that are not.) */
function roundTo2(x: number): number {
  if (!Number.isFinite(x)) return x
  const eighths = x * 8
  if (Number.isInteger(eighths) && Math.abs(eighths % 2) === 1) {
    // x is odd/8: exactly halfway between two hundredths (0.125 -> 0.12, 0.375 -> 0.38).
    const hundredths = x * 100 // exact: odd * 12.5
    const lower = Math.floor(hundredths)
    return (lower % 2 === 0 ? lower : lower + 1) / 100
  }
  return Number(x.toFixed(2))
}

/** Python 3.12+'s `sum()` of floats: Neumaier-compensated, so the same terms
 *  give the same total in both halves, not one that differs in the last place. */
function pySum(terms: Iterable<number>): number {
  let total = 0
  let c = 0
  for (const x of terms) {
    const t = total + x
    if (Math.abs(total) >= Math.abs(x)) c += total - t + x
    else c += x - t + total
    total = t
  }
  return c !== 0 && Number.isFinite(c) ? total + c : total
}

/** `Math.round` by Python's definition in this module: halves go up. */
function jsRound(x: number): number {
  return Math.floor(x + 0.5)
}

// --- text -----------------------------------------------------------------------------

/** The unitless line height of a font family. */
export function lineHeight(font: number): number {
  return LINE_HEIGHT[font] ?? DEFAULT_LINE_HEIGHT
}

/** One glyph's advance at `size`: the font's own width, else (a glyph the
 *  tables lack) the font's average, or a full em for wide East-Asian forms. */
function advance(ch: string, size: number, font: number): number {
  const table = ADVANCE[font] ?? ADVANCE[FONT_EXCALIFONT]
  const w = table.get(ch)
  if (w !== undefined) return (w * size) / 1000
  if (isWide(ch)) return size
  return ((METRICS[font] ?? METRICS[FONT_EXCALIFONT])[0] * size) / 1000
}

export interface TextOptions {
  /** Every glyph this many ems wide: the old flat estimate. */
  charEm?: number | null
}

/** The width of one line. With `charEm` every glyph is that many ems wide
 *  (the old flat estimate); without, each glyph has the width of the font
 *  family, so `WIDE CAPS` are not measured like `narrow lowercase`. */
export function textWidth(line: string, size: number, font: number, options: TextOptions = {}): number {
  const { charEm = null } = options
  if (charEm !== null) return Array.from(line).length * size * charEm
  return pySum(Array.from(line, (ch) => advance(ch, size, font)))
}

/** The box a text takes, estimated, as `[width, height]`: widest line (summed
 *  glyph advances of the font family) by lines times the line height. The
 *  canvas measures exactly the moment the text is edited, so this only has to
 *  be close, and never short. */
export function measureText(text: string, size: number, font: number, options: TextOptions = {}): [number, number] {
  const { charEm = null } = options
  const lines = text.split('\n')
  const width = Math.max(...lines.map((line) => textWidth(line, size, font, options)))
  const floor = size * (charEm !== null ? charEm : CHAR_EM)
  return [roundTo2(Math.max(width, floor)), roundTo2(lines.length * size * lineHeight(font))]
}

/** Wrap `text` to `width` pixels the way the canvas wraps text bound to a
 *  box: line breaks kept, words kept whole while they fit, a word wider than
 *  the box broken across lines. Widths are the font's own. */
export function wrapText(
  text: string, width: number, size: number, font: number = FONT_EXCALIFONT, options: TextOptions = {},
): string {
  const lines: string[] = []
  for (const paragraph of text.split('\n')) {
    let line = ''
    for (const w of paragraph.split(' ')) {
      let word = w
      const cand = line ? `${line} ${word}` : word
      if (textWidth(cand, size, font, options) <= width) {
        line = cand
        continue
      }
      if (line) {
        lines.push(line)
        line = ''
      }
      let glyphs = Array.from(word)
      while (textWidth(word, size, font, options) > width && glyphs.length > 1) {
        let n = 1
        while (n < glyphs.length - 1 && textWidth(glyphs.slice(0, n + 1).join(''), size, font, options) <= width) n++
        lines.push(glyphs.slice(0, n).join(''))
        glyphs = glyphs.slice(n)
        word = glyphs.join('')
      }
      line = word
    }
    lines.push(line)
  }
  return lines.join('\n')
}

/** The room a container offers bound text, as Excalidraw's
 *  `getBoundTextMaxWidth` / `getBoundTextMaxHeight` / `getContainerCoords`
 *  have it: `[maxWidth, maxHeight, left, top]`. A rectangle offers its box
 *  less the padding; an ellipse the box of the rectangle inscribed in it
 *  (`w / sqrt 2`); a diamond half its width and height. */
export function textRoom(container: El, padding: number = PADDING): [number, number, number, number] {
  const w: number = container.width
  const h: number = container.height
  const kind = container.type
  let left: number = container.x + padding
  let top: number = container.y + padding
  if (kind === 'ellipse') {
    left += (w / 2) * (1 - Math.sqrt(2) / 2)
    top += (h / 2) * (1 - Math.sqrt(2) / 2)
    return [jsRound((w / 2) * Math.sqrt(2)) - 2 * padding, jsRound((h / 2) * Math.sqrt(2)) - 2 * padding, left, top]
  }
  if (kind === 'diamond') {
    return [jsRound(w / 2) - 2 * padding, jsRound(h / 2) - 2 * padding, left + w / 4, top + h / 4]
  }
  return [w - 2 * padding, h - 2 * padding, left, top]
}

/** The container height that holds `textHeight` of bound text: Excalidraw's
 *  `computeContainerDimensionForBoundText`. */
export function containerHeightFor(textHeight: number, kind: string | null | undefined, padding: number = PADDING): number {
  const d = Math.ceil(textHeight)
  if (kind === 'ellipse') return jsRound(((d + 2 * padding) / Math.sqrt(2)) * 2)
  if (kind === 'diamond') return 2 * (d + 2 * padding)
  return d + 2 * padding
}

/** `text` wrapped to the width a container offers it and centred in the room
 *  it offers: the wrapped text, its width and height, and its top-left corner. */
function inContainer(
  container: El, text: string, size: number, font: number, padding: number,
): [string, number, number, number, number] {
  const [maxW, maxH, left, top] = textRoom(container, padding)
  const wrapped = wrapText(text, maxW, size, font)
  const [w, h] = measureText(wrapped, size, font)
  return [wrapped, w, h, left + (maxW - w) / 2, top + (maxH - h) / 2]
}

// --- the builders ---------------------------------------------------------------------

/** The fields every Excalidraw element carries, with Excalidraw's defaults.
 *  `index` is `null`, which Excalidraw defines as "not yet assigned to a
 *  scene": it assigns the fractional index when the elements are loaded, and
 *  inventing one here would collide with the elements already there. Anything
 *  else in the options replaces a default. */
export function baseElement(
  kind: string, x: number, y: number, w: number, h: number, options: { roughness: number } & El,
): El {
  const { roughness, ...over } = options
  // Evaluated in this order, as the Python twin does, so a counting source
  // gives both halves the same ids.
  const id = newId()
  const seed = nonce()
  const versionNonce = nonce()
  const updated = nowMs()
  return {
    id,
    type: kind,
    x, y, width: w, height: h,
    angle: 0,
    strokeColor: INK,
    backgroundColor: 'transparent',
    fillStyle: 'solid',
    strokeWidth: 2,
    strokeStyle: 'solid',
    roughness,
    opacity: 100,
    groupIds: [],
    frameId: null,
    index: null,
    roundness: null,
    seed,
    version: 1,
    versionNonce,
    isDeleted: false,
    boundElements: null,
    updated,
    link: null,
    locked: false,
    ...over,
  }
}

export interface TextElementOptions extends El {
  font: number
  roughness: number
  size?: number
  container?: El | null
  padding?: number
}

/** A text element: free-standing at `(x, y)`, or, given `container`, wrapped
 *  to the container's width and centred in it (`containerId` set). This
 *  builds the text only; `addLabel` also binds it into the box. */
export function textElement(text: string, x: number, y: number, options: TextElementOptions): El {
  const { size = FONT_SIZE, font, roughness, container = null, padding = PADDING, ...over } = options
  const original = text
  let w: number
  let h: number
  if (container !== null) {
    ;[text, w, h, x, y] = inContainer(container, text, size, font, padding)
  } else {
    ;[w, h] = measureText(text, size, font)
  }
  return baseElement('text', x, y, w, h, {
    roughness,
    text,
    originalText: original,
    fontSize: size,
    fontFamily: font,
    textAlign: container !== null ? 'center' : 'left',
    verticalAlign: container !== null ? 'middle' : 'top',
    containerId: container !== null ? container.id : null,
    autoResize: true,
    lineHeight: lineHeight(font),
    ...over,
  })
}

/** A rectangle, ellipse or diamond. A rectangle and a diamond carry the
 *  rounded-corner `roundness` Excalidraw gives them by default. */
export function shapeElement(
  kind: string, x: number, y: number, w: number, h: number, options: { roughness: number } & El,
): El {
  if (!(SHAPES as readonly string[]).includes(kind)) {
    throw new Error(`a shape is one of ${SHAPES.join(', ')}, not '${kind}'`)
  }
  const roundness = kind === 'rectangle' ? { type: 3 } : kind === 'diamond' ? { type: 2 } : null
  return baseElement(kind, x, y, w, h, { roundness, ...options })
}

/** A frame, named `name` (`null` for no name), in Excalidraw's frame outline. */
export function frameElement(
  x: number, y: number, w: number, h: number, name: string | null = null, options: El = {},
): El {
  const { roughness = 0, ...over } = options
  return baseElement('frame', x, y, w, h, {
    roughness,
    strokeColor: FRAME_INK,
    name: name || null,
    ...over,
  })
}

export interface LinearElementOptions extends El {
  roughness: number
  startHead?: string | null
  endHead?: string | null
}

/** An arrow or a line along an absolute `route` — its origin at the first
 *  point, its points relative to that, as Excalidraw wants (`arrowElement` in
 *  `geometry`). Unbound at both ends; see `bindEnd`. */
export function linearElement(kind: string, route: readonly (readonly [number, number])[], options: LinearElementOptions): El {
  if (!(LINEAR as readonly string[]).includes(kind)) {
    throw new Error(`a linear element is one of ${LINEAR.join(', ')}, not '${kind}'`)
  }
  const { roughness, startHead = null, endHead = null, ...over } = options
  const geo = arrowElement(route)
  const el = baseElement(kind, geo.x, geo.y, geo.width, geo.height, {
    roughness,
    points: geo.points.map((p) => [p[0], p[1]]),
    lastCommittedPoint: null,
    startBinding: null,
    endBinding: null,
    startArrowhead: startHead,
    endArrowhead: endHead,
    ...over,
  })
  if (kind === 'arrow') el.elbowed = false
  return el
}

// --- where an arrow ends --------------------------------------------------------------

/** Where a ray from the centre of `box` toward `aim` leaves the SHAPE drawn
 *  in it — an ellipse and a diamond are inside their bounding box — plus
 *  `gap`. If `aim` is inside the shape the ray stops at `aim`. */
export function boundaryPoint(shape: string, box: Box, aim: readonly [number, number], gap: number = BIND_GAP): Pt {
  const [cx, cy] = centre(box)
  const dx = aim[0] - cx
  const dy = aim[1] - cy
  const length = Math.hypot(dx, dy)
  if (length < 1e-6) return [cx, cy]
  const t = Math.min(exitT(box, dx, dy, shape), 1.0)
  const reach = length * t + gap
  return [cx + (dx / length) * reach, cy + (dy / length) * reach]
}

/** A shape at the end of an arrow: its kind and its box. */
export type End = readonly [string, Box]

/** The absolute route of an arrow whose ends stand on shapes.
 *
 *  `points` is the route as far as the caller knows it (two or more points)
 *  or `null`; `start` and `end` are `[shape, box]` for an end that stands on a
 *  shape, `null` for a free end. A shape end is moved onto the shape's edge,
 *  aimed at the next point. With no `points` both ends must be shapes and the
 *  route is the line between their centres, trimmed to their edges. Throws
 *  when there is nothing to draw. */
export function routeBetween(
  points: readonly (readonly [number, number])[] | null,
  start: End | null = null,
  end: End | null = null,
  options: { gap?: number } = {},
): Pt[] {
  const { gap = BIND_GAP } = options
  let route: Pt[]
  if (points === null) {
    if (start === null || end === null) throw new Error('a route needs points, or a shape at both ends')
    route = [[...centre(start[1])], [...centre(end[1])]]
  } else {
    route = points.map((p) => [p[0], p[1]])
  }
  if (start !== null) {
    route[0] = boundaryPoint(start[0], start[1], route.length > 1 ? route[1] : centre(start[1]), gap)
  }
  if (end !== null) {
    route[route.length - 1] = boundaryPoint(end[0], end[1], route[route.length - 2], gap)
  }
  if (start !== null && end !== null && route.length === 2) {
    route = [
      boundaryPoint(start[0], start[1], centre(end[1]), gap),
      boundaryPoint(end[0], end[1], centre(start[1]), gap),
    ]
  }
  return route
}

/** A linear element's route in absolute coordinates. */
export function routeOf(linear: El): Pt[] {
  return (linear.points as number[][]).map((p) => [linear.x + p[0], linear.y + p[1]])
}

/** Give a linear element a new absolute route: its origin, size and relative
 *  points together. */
export function setRoute(linear: El, route: readonly (readonly [number, number])[]): void {
  const geo = arrowElement(route)
  Object.assign(linear, {
    x: geo.x,
    y: geo.y,
    width: geo.width,
    height: geo.height,
    points: geo.points.map((p) => [p[0], p[1]]),
  })
}

// --- references that stay consistent ---------------------------------------------------

/** Take `memberId` out of `host`'s `boundElements`. True if it was there. */
export function unlistBound(host: El, memberId: string): boolean {
  const listed: El[] = host.boundElements || []
  const kept = listed.filter((b) => b.id !== memberId)
  if (kept.length === listed.length) return false
  host.boundElements = kept.length ? kept : null
  return true
}

/** The text bound into `container`, if any (looked up in `byId`). */
export function labelOf(container: El, byId: ById): El | null {
  for (const b of (container.boundElements || []) as El[]) {
    if (b.type === 'text' && typeof b.id === 'string' && has(byId, b.id)) return byId[b.id]
  }
  return null
}

export interface AddLabelOptions extends El {
  font: number
  roughness: number
  size?: number
  padding?: number
}

/** Bind `text` into `container` as its label and return the new text.
 *
 *  The text is wrapped to the box and centred in it; if it needs more height
 *  than the box has, the box grows (its width never does). The binding is made
 *  both ways. The container's stroke colour is the text's unless the options
 *  say otherwise (a transparent stroke falls back to `INK`). The caller stores
 *  the label after its box, so it paints on top, and `touch`es the container
 *  if it already existed. */
export function addLabel(container: El, text: string, options: AddLabelOptions): El {
  const { size = FONT_SIZE, font, roughness, padding = PADDING, ...rest } = options
  const stroke = container.strokeColor || INK
  const over: El = { strokeColor: stroke === 'transparent' ? INK : stroke, ...rest }
  const build = (): El =>
    textElement(text, container.x, container.y, { size, font, roughness, container, padding, ...over })
  let label = build()
  const need = containerHeightFor(label.height, container.type, padding)
  if (need > container.height) {
    container.height = need
    label = build()
  }
  container.boundElements = [...(container.boundElements || []), { id: label.id, type: 'text' }]
  return label
}

/** Lay `label` out again inside `container` — after the box moved or was
 *  resized, or with new `text` or `size` — wrapped, centred, and growing the
 *  box if it needs more height. Returns the elements changed (the label, and
 *  the container if it grew). */
export function fitLabel(
  container: El, label: El, options: { text?: string | null; size?: number | null; padding?: number } = {},
): El[] {
  const { text = null, size = null, padding = PADDING } = options
  if (text !== null) label.originalText = text
  if (size !== null) label.fontSize = size
  const changed: El[] = [label]
  let [wrapped, w, h, x, y] = inContainer(container, label.originalText, label.fontSize, label.fontFamily, padding)
  const need = containerHeightFor(h, container.type, padding)
  if (need > container.height) {
    container.height = need
    changed.push(container)
    ;[wrapped, w, h, x, y] = inContainer(container, label.originalText, label.fontSize, label.fontFamily, padding)
  }
  Object.assign(label, { x, y, width: w, height: h, text: wrapped })
  return changed
}

/** Bind one end (`'start'` or `'end'`) of `arrow` to `host`, or free it with
 *  `host = null`, keeping both directions in step: the arrow's binding names
 *  the host and the host's `boundElements` names the arrow. An end that was
 *  bound to something else is removed from that element's list (found in
 *  `byId`). Only the binding changes; call `refitArrow` to move the end onto
 *  the host. Returns the other elements changed. */
export function bindEnd(
  arrow: El, which: string, host: El | null, options: { byId?: ById | null; gap?: number } = {},
): El[] {
  const { byId = null, gap = BIND_GAP } = options
  if (which !== 'start' && which !== 'end') throw new Error('which is "start" or "end"')
  const field = which === 'start' ? 'startBinding' : 'endBinding'
  const changed: El[] = []
  const old = arrow[field]
  if (old && byId !== null && typeof old.elementId === 'string' && has(byId, old.elementId)) {
    const previous = byId[old.elementId]
    if (previous !== host && unlistBound(previous, arrow.id)) changed.push(previous)
  }
  arrow[field] = null
  if (host !== null) {
    arrow[field] = { elementId: host.id, focus: 0, gap }
    const listed: El[] = host.boundElements || []
    if (!listed.some((b) => b.id === arrow.id)) {
      host.boundElements = [...listed, { id: arrow.id, type: 'arrow' }]
      changed.push(host)
    }
  }
  return changed
}

/** Put a bound arrow's ends back on the edges of the shapes they are bound to
 *  (found in `byId`) — after a shape moved or changed size. An arrow bound at
 *  neither end is left alone. True if the arrow was changed. */
export function refitArrow(arrow: El, byId: ById, options: { gap?: number } = {}): boolean {
  const { gap = BIND_GAP } = options
  let route = routeOf(arrow)
  const sb = arrow.startBinding
  const eb = arrow.endBinding
  const s: El | undefined = sb && has(byId, sb.elementId) ? byId[sb.elementId] : undefined
  const e: El | undefined = eb && has(byId, eb.elementId) ? byId[eb.elementId] : undefined
  if (s === undefined && e === undefined) return false
  if (s !== undefined && e !== undefined && route.length === 2) {
    route = routeBetween(null, [s.type, boxOf(s)], [e.type, boxOf(e)], { gap })
  } else {
    if (s !== undefined) route[0] = boundaryPoint(s.type, boxOf(s), route[1], gap)
    if (e !== undefined) route[route.length - 1] = boundaryPoint(e.type, boxOf(e), route[route.length - 2], gap)
  }
  setRoute(arrow, route)
  return true
}

/** Take `element` out of the references around it, ready to be removed.
 *
 *  Its labels go with it; an arrow bound to it stays, let go at that end; a
 *  label leaves its box's list; an arrow leaves the lists of the shapes it was
 *  bound to. Returns `[ids to remove, other elements changed]`: the ids are
 *  the element and its labels, and nothing here removes them from `byId`. */
export function detach(element: El, byId: ById): [string[], El[]] {
  const gone: string[] = [element.id]
  const changed: El[] = []
  const note = (el: El): void => {
    if (!changed.some((c) => c === el)) changed.push(el)
  }

  if (element.containerId) {
    const box = has(byId, element.containerId) ? byId[element.containerId] : undefined
    if (box !== undefined && unlistBound(box, element.id)) note(box)
  }
  for (const b of (element.boundElements || []) as El[]) {
    const member = typeof b.id === 'string' && has(byId, b.id) ? byId[b.id] : undefined
    if (member === undefined) continue
    if (b.type === 'text') {
      gone.push(member.id)
    } else if (b.type === 'arrow') {
      for (const field of ['startBinding', 'endBinding']) {
        const bound = member[field]
        if (bound && bound.elementId === element.id) member[field] = null
      }
      note(member)
    }
  }
  if ((LINEAR as readonly string[]).includes(element.type)) {
    for (const field of ['startBinding', 'endBinding']) {
      const bound = element[field]
      if (bound && has(byId, bound.elementId)) {
        const host = byId[bound.elementId]
        if (unlistBound(host, element.id)) note(host)
      }
    }
  }
  return [gone, changed]
}
