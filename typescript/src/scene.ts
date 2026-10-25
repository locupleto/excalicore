/**
 * The bridge between an Excalidraw canvas and a language model.
 *
 * Two directions, both lossy on purpose:
 *
 * **Canvas → model** (`compact`). The raw scene is far too wide to put in a
 * prompt, and most of its width is bookkeeping a model must never invent. So
 * the canvas is projected onto a *skeleton dialect*: a handful of meaningful
 * fields per element, the binding graph folded into skeleton form, and the
 * element types a model cannot faithfully re-emit reduced to read-only
 * geometry.
 *
 * **Model → canvas** (`extractPatch`). A reply is prose that may end in one
 * JSON object. That object is a MERGE PATCH — added or changed elements plus a
 * list of ids to delete — never a whole board. The inversion matters: a lazy
 * partial reply is then correct behaviour, and destruction requires explicit
 * intent. Validation is strict all-or-nothing, so a half-garbled reply can
 * never half-apply.
 *
 * Everything here is pure: no I/O, no framework, no DOM. The constants are
 * options rather than hard-coded, so an application tunes the dialect instead
 * of forking the module. This is the twin of `excalicore.scene` and is fixed
 * against the same corpus (`corpus/scene`, `corpus/scenes`, `corpus/replies`).
 *
 * Where Python's behaviour has no JavaScript spelling, the twin matches what
 * Python would print: `round` is banker's rounding (`pyRound`), `str.strip` and
 * the regexes' `\s` are Python's whitespace set, and a reply's JSON is read by
 * a small decoder with `json.JSONDecoder.raw_decode`'s grammar (which accepts
 * `NaN` and `Infinity`, as `JSON.parse` does not) rather than by `JSON.parse`.
 */

import { boxOf, union, type Element } from './geometry.ts'

/** Fields worth showing a model — enough to reason about the board and to
 *  preserve ids, without the versionNonce/seed/roundness noise that only burns
 *  tokens and invites the model to echo values it should never author. */
export const KEEP: readonly string[] = [
  'id', 'type', 'x', 'y', 'width', 'height', 'text', 'label',
  'strokeColor', 'backgroundColor', 'fontSize', 'points', 'start', 'end',
  'angle', 'arrowhead',
]

/** Read-only to the model: hand strokes, images, and placed stencils. It
 *  cannot re-draw a stroke (raw payloads are huge point clouds), an echoed
 *  image would lose its fileId and break skeleton conversion, and a stencil
 *  instance is a group of primitives it should address as one symbol. Patch
 *  elements of these types are dropped and the client preserves the real ones.
 *  The model still SEES them: `compact` emits each as id + bbox (+ a
 *  simplified polyline for strokes), which is enough to align new shapes to the
 *  ink and to delete by id. */
export const OPAQUE_TYPES: ReadonlySet<string> = new Set(['freedraw', 'image', 'stencil'])

/** The customData key a stencil instance is recognised by. */
const STENCIL_KEYS: ReadonlySet<string> = new Set(['stencil'])

/** Polyline budget per stroke; tolerance coarsens to fit. */
export const MAX_STROKE_POINTS = 32
/** Beyond this it is a hallucination, not a layout. */
export const MAX_COORD = 1_000_000

// Python's whitespace (`str.isspace`, and `\s` in a str pattern), which is not
// JavaScript's: it has the four file/group/record/unit separators and NEL, and
// no byte-order mark.
const WS = '\\t-\\r\\x1c-\\x20\\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000'
const LABEL_TAIL = new RegExp(
  `[${WS}]*\`{0,3}[${WS}]*(?:excalidraw|json)[${WS}]*\`{0,3}[${WS}]*$`, 'iu',
)
const FENCE_HEAD = new RegExp(`^[${WS}]*\`{3}[ \\t]*\\r?\\n?`, 'u')
const WS_LEAD = new RegExp(`^[${WS}]+`, 'u')
const WS_TRAIL = new RegExp(`[${WS}]+$`, 'u')
const NOT_WS = new RegExp(`[^${WS}]`, 'u')

// --- Python's spellings ----------------------------------------------------------

function isDict(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

/** Python's truthiness: null, false, 0, NaN, "", [] and {} are falsy. */
function truthy(v: unknown): boolean {
  if (v === null || v === undefined || v === false || v === 0 || v === '') return false
  if (typeof v === 'number' && Number.isNaN(v)) return false
  if (Array.isArray(v)) return v.length > 0
  if (isDict(v)) return Object.keys(v).length > 0
  return true
}

/** `v or 0`. */
function orZero(v: unknown): number {
  return truthy(v) ? (v as number) : 0
}

/** Python's `round(x)`: half to even, never negative zero. */
function pyRound(x: number): number {
  if (!Number.isFinite(x)) return x
  const f = Math.floor(x)
  const d = x - f
  let r: number
  if (d < 0.5) r = f
  else if (d > 0.5) r = f + 1
  else r = f % 2 === 0 ? f : f + 1
  return r + 0
}

/** `math.hypot` for two terms. `Math.hypot` and C's `hypot` may disagree in the
 *  last bit; the root of an exactly-summed pair is identical in both, which is
 *  every case where the arguments are integers. */
function hypot(a: number, b: number): number {
  return Math.sqrt(a * a + b * b)
}

/** `isinstance(v, (int, float))` — a bool counts in Python. */
function isPyNumber(v: unknown): boolean {
  return typeof v === 'number' || typeof v === 'boolean'
}

/** `float(v)` for what JSON can hold; throws where Python raises. */
function toFloat(v: unknown): number {
  if (typeof v === 'number') return v
  if (typeof v === 'boolean') return v ? 1 : 0
  if (typeof v === 'string') {
    const t = v.replace(new RegExp(`^[${WS}]+|[${WS}]+$`, 'gu'), '')
    if (/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(t)) return Number(t)
    if (/^[+-]?(inf|infinity)$/i.test(t)) return t.startsWith('-') ? -Infinity : Infinity
    if (/^[+-]?nan$/i.test(t)) return NaN
  }
  throw new TypeError(`cannot convert ${JSON.stringify(v)} to float`)
}

/** `str(v)` for the values an instance id can sensibly be. */
function pyStr(v: unknown): string {
  if (typeof v === 'string') return v
  if (typeof v === 'boolean') return v ? 'True' : 'False'
  return String(v)
}

// --- strokes ---------------------------------------------------------------------

/** Ramer-Douglas-Peucker polyline simplification (iterative). */
export function rdp(points: number[][], eps: number): number[][] {
  if (points.length < 3) return points
  const keep: boolean[] = new Array(points.length).fill(false)
  keep[0] = keep[points.length - 1] = true
  const stack: [number, number][] = [[0, points.length - 1]]
  while (stack.length) {
    const [a, b] = stack.pop()!
    const [ax, ay] = points[a]
    const [bx, by] = points[b]
    const dx = bx - ax
    const dy = by - ay
    const norm = hypot(dx, dy)
    let worst = -1
    let worstD = eps
    for (let i = a + 1; i < b; i++) {
      const [px, py] = points[i]
      const d = norm ? Math.abs(dx * (ay - py) - dy * (ax - px)) / norm : hypot(px - ax, py - ay)
      if (d > worstD) {
        worst = i
        worstD = d
      }
    }
    if (worst !== -1) {
      keep[worst] = true
      stack.push([a, worst])
      stack.push([worst, b])
    }
  }
  return points.filter((_, i) => keep[i])
}

export interface StrokeOptions {
  /** Polyline budget; default `MAX_STROKE_POINTS`. Below 2 it never ends,
   *  as in the Python twin. */
  maxPoints?: number
}

/** A freedraw stroke as read-only geometry a model can align to and delete.
 *
 *  Returns id + bbox + a simplified polyline in absolute integer board
 *  coordinates, plus a `closed` hint when the ends nearly meet (a hand-drawn
 *  circle). The RDP tolerance coarsens until the polyline fits `maxPoints`,
 *  so a 900-point scribble costs the same as a 40-point one. */
export function strokeSummary(element: Element, options: StrokeOptions = {}): Element {
  const maxPoints = options.maxPoints ?? MAX_STROKE_POINTS
  const x0 = orZero(element.x)
  const y0 = orZero(element.y)
  const slim: Element = {
    id: element.id ?? null, type: 'freedraw',
    x: pyRound(x0), y: pyRound(y0),
    width: pyRound(orZero(element.width)),
    height: pyRound(orZero(element.height)),
  }
  if (truthy(element.strokeColor)) slim.strokeColor = element.strokeColor
  const raw = Array.isArray(element.points) ? (element.points as unknown[]) : []
  const pts: number[][] = []
  for (const p of raw) {
    if (Array.isArray(p) && p.length >= 2
      && [p[0], p[1]].every((c) => typeof c === 'number' && Number.isFinite(c))) {
      pts.push([p[0] as number, p[1] as number])
    }
  }
  if (pts.length >= 2) {
    const diag = hypot(slim.width as number, slim.height as number) || 1.0
    let eps = diag * 0.02
    let simple = rdp(pts, eps)
    while (simple.length > maxPoints) {
      eps *= 2
      simple = rdp(pts, eps)
    }
    slim.points = simple.map(([px, py]) => [pyRound(x0 + px), pyRound(y0 + py)])
    const first = pts[0]
    const last = pts[pts.length - 1]
    if (hypot(last[0] - first[0], last[1] - first[1]) < diag * 0.12) slim.closed = true
  }
  return slim
}

// --- stencils --------------------------------------------------------------------

/** The stencil instance an element belongs to, or null.
 *
 *  `customData.stencil.instance` is where excalicore writes it. */
export function instanceOf(element: Element): string | null {
  const cd = element.customData
  if (!isDict(cd)) return null
  const tag = cd.stencil
  if (isDict(tag) && truthy(tag.instance)) return pyStr(tag.instance)
  return null
}

/** One placed stencil as the read-only entry the model sees.
 *
 *  `{id, type: "stencil", name, x, y, width, height}` plus a `label` when a
 *  part carries one (the part with role `label`, else the first text in the
 *  group) and a `subject` when the application tagged the parts with
 *  namespaces of its own beside `stencil` — those are passed through
 *  untouched, so a prompt can say what the symbol stands for without the
 *  application re-deriving it from a rectangle and two lines. */
export function stencilSummary(instance: string, members: readonly Element[]): Element {
  const tagOf = (m: Element): Record<string, unknown> => {
    const cd = m.customData
    const tag = isDict(cd) ? cd.stencil : null
    return isDict(tag) ? tag : {}
  }

  const first = members[0]
  const cd0 = truthy(first.customData) ? (first.customData as Record<string, unknown>) : {}
  const tag0 = tagOf(first)
  const entry: Element = {
    id: instance, type: 'stencil',
    name: tag0.name ?? null,
  }
  // The box the model sees is the SUBJECT's — read off the body and its
  // frame, the only way back — so a stick figure is reported as the box it
  // stands for, not as the union of its limbs and a centred caption with no
  // width. Only an instance without a frame falls back to the footprint of
  // its parts.
  const body = members.find((m) => tagOf(m).role === 'body') ?? null
  const frame = body !== null ? tagOf(body).frame : undefined
  let box: [number, number, number, number] | null = null
  if (isDict(frame)) {
    try {
      box = [
        toFloat(orZero(body!.x)) + toFloat(frame.dx),
        toFloat(orZero(body!.y)) + toFloat(frame.dy),
        toFloat(orZero(body!.width)) * toFloat(frame.sw),
        toFloat(orZero(body!.height)) * toFloat(frame.sh),
      ]
    } catch {
      box = null
    }
  }
  if (box === null) {
    const xs = members.map((m) => orZero(m.x))
    const ys = members.map((m) => orZero(m.y))
    const x2 = members.map((m) => orZero(m.x) + orZero(m.width))
    const y2 = members.map((m) => orZero(m.y) + orZero(m.height))
    const minX = Math.min(...xs)
    const minY = Math.min(...ys)
    box = [minX, minY, Math.max(...x2) - minX, Math.max(...y2) - minY]
  }
  entry.x = pyRound(box[0])
  entry.y = pyRound(box[1])
  entry.width = pyRound(box[2])
  entry.height = pyRound(box[3])
  let label: Element | null = null
  for (const m of members) {
    if (tagOf(m).role === 'label') {
      label = m
      break
    }
    if (m.type === 'text' && label === null) label = m
  }
  let text: unknown = label !== null ? (truthy(label.originalText) ? label.originalText : label.text) : null
  if (!truthy(text) && body !== null && isDict(body.label)) {
    text = body.label.text  // a label carried as a property on the body
  }
  if (truthy(text)) entry.label = text
  const subject: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(cd0)) if (!STENCIL_KEYS.has(k)) subject[k] = v
  if (Object.keys(subject).length) entry.subject = subject
  return entry
}

/** `[width, height]` of a group of elements — an instance's natural
 *  footprint. A thin wrapper over `union`; the linear-origin rule (a box may
 *  start before an element's own `x`/`y`) lives there now, in `boxOf`. */
export function bbox(elements: readonly unknown[] | null | undefined): [number, number] {
  const boxes = (elements ?? [])
    .filter((e): e is Element => isDict(e) && isPyNumber(e.x) && isPyNumber(e.y))
    .map(boxOf)
  const u = union(boxes)
  return u !== null ? [u.width, u.height] : [0, 0]
}

// --- compact ---------------------------------------------------------------------

export interface CompactOptions {
  /** The fields to show; default `KEEP`. */
  keep?: readonly string[]
  /** The read-only types; default `OPAQUE_TYPES`. */
  opaque?: ReadonlySet<string>
  /** Polyline budget per stroke; default `MAX_STROKE_POINTS`. */
  maxPoints?: number
}

/** Project the raw canvas onto the skeleton dialect the model speaks.
 *
 *  Beyond field-stripping, this translates Excalidraw's binding graph into
 *  skeleton forms so a hand-drawn board survives the echo round-trip:
 *
 *  - text bound to a container (`containerId`) folds into the container's
 *    `label:{text}` and drops as a standalone element — otherwise an echoed
 *    label detaches from its shape, or worse, duplicates;
 *  - arrow `startBinding`/`endBinding` become skeleton `start`/`end` id refs,
 *    and raw `points` are dropped there, because conversion re-routes bound
 *    arrows anyway;
 *  - elements placed from a stencil carry `customData.stencil {name,
 *    instance, role, ...}`; each instance folds into ONE read-only
 *    `{type: "stencil"}` entry — its id the instance id, its `label` the label
 *    part's text, its `subject` whatever other namespaces the application
 *    tagged the parts with — so the model sees a symbol rather than the dozen
 *    primitives it is made of, and can bind an arrow to it by that one id (the
 *    client resolves the id to the stencil's body);
 *  - the remaining opaque types appear as read-only geometry. */
export function compact(
  elements: readonly unknown[] | null | undefined,
  options: CompactOptions = {},
): Element[] {
  const keep = options.keep ?? KEEP
  const opaque = options.opaque ?? OPAQUE_TYPES
  const maxPoints = options.maxPoints ?? MAX_STROKE_POINTS

  const els = (elements ?? []).filter((e): e is Element => isDict(e) && !truthy(e.isDeleted))
  // Maps, not objects: an id like "10" must not jump the queue in a JS object.
  const byId = new Map<unknown, Element>()
  for (const e of els) if (truthy(e.id)) byId.set(e.id, e)
  const boundText = new Map<unknown, Element>()
  for (const e of els) if (e.type === 'text' && byId.has(e.containerId)) boundText.set(e.containerId, e)
  const instances = new Map<string, Element[]>()
  for (const e of els) {
    const gid = instanceOf(e)
    if (gid) {
      const group = instances.get(gid)
      if (group) group.push(e)
      else instances.set(gid, [e])
    }
  }
  const placedIds = new Set<unknown>()
  for (const g of instances.values()) for (const e of g) placedIds.add(e.id ?? null)

  const out: Element[] = []
  for (const [gid, members] of instances) out.push(stencilSummary(gid, members))
  for (const el of els) {
    if (placedIds.has(el.id ?? null)) continue  // summarized as its instance's stencil entry above
    const kind = el.type
    if (kind === 'freedraw') {
      out.push(strokeSummary(el, { maxPoints }))
      continue
    }
    if (typeof kind === 'string' && opaque.has(kind)) {
      out.push({
        id: el.id ?? null, type: kind,
        x: pyRound(orZero(el.x)), y: pyRound(orZero(el.y)),
        width: pyRound(orZero(el.width)),
        height: pyRound(orZero(el.height)),
      })
      continue
    }
    if (kind === 'text' && byId.has(el.containerId)) continue  // folded into its container's label below
    const slim: Element = {}
    for (const k of keep) if (Object.hasOwn(el, k)) slim[k] = el[k]
    const lbl = boundText.get(el.id)
    const lblText = lbl === undefined ? undefined : (truthy(lbl.originalText) ? lbl.originalText : lbl.text)
    if (lbl !== undefined && truthy(lblText) && !Object.hasOwn(slim, 'label')) {
      slim.label = truthy(lbl.fontSize) ? { text: lblText, fontSize: lbl.fontSize } : { text: lblText }
    }
    for (const [bindKey, refKey] of [['startBinding', 'start'], ['endBinding', 'end']] as const) {
      const bind = el[bindKey]
      if (isDict(bind) && byId.has(bind.elementId)) {
        slim[refKey] = { id: bind.elementId }
        delete slim.points
      }
    }
    out.push(slim)
  }
  return out
}

// --- patches ---------------------------------------------------------------------

export interface PatchOptions {
  /** The read-only types a patch may not author; default `OPAQUE_TYPES`. */
  opaque?: ReadonlySet<string>
  /** The largest coordinate that is still a layout; default `MAX_COORD`. */
  maxCoord?: number
}

/** A validated merge patch: the elements to add or change, the ids to delete. */
export interface Patch {
  elements: Element[]
  delete: string[]
}

/** True when every present coordinate is a finite number within bounds. */
export function saneGeometry(element: Element, options: { maxCoord?: number } = {}): boolean {
  const maxCoord = options.maxCoord ?? MAX_COORD
  for (const key of ['x', 'y', 'width', 'height']) {
    const v = element[key]
    if (v === null || v === undefined) continue
    if (typeof v !== 'number') return false
    if (!Number.isFinite(v) || Math.abs(v) > maxCoord) return false
  }
  return true
}

/** Validate a parsed block as a merge patch, or return null.
 *
 *  A patch is `{elements: [{type, ...}, ...]}` and/or `{delete: [id, ...]}`.
 *  An element may instead be a stencil placement, `{"stencil": name, x, y}`.
 *  Strict all-or-nothing: one malformed element, or one insane coordinate,
 *  rejects the WHOLE patch, so a half-garbled reply can never half-apply.
 *
 *  Opaque-typed elements are then dropped silently — an echoed stroke would
 *  replace real ink with its own simplified caricature — while the rest of the
 *  patch stands. A patch that says nothing after that is not a patch. */
export function validPatch(obj: unknown, options: PatchOptions = {}): Patch | null {
  const opaque = options.opaque ?? OPAQUE_TYPES
  const maxCoord = options.maxCoord ?? MAX_COORD
  if (!isDict(obj)) return null
  let els: unknown[] = Array.isArray(obj.elements) ? obj.elements : []
  const delete_ = Array.isArray(obj.delete)
    ? (obj.delete.filter((d) => typeof d === 'string') as string[])
    : []

  const num = (v: unknown): boolean => typeof v === 'number'

  const ok = (e: unknown): boolean => {
    if (!(isDict(e) && saneGeometry(e, { maxCoord }))) return false
    const name = e.stencil
    if (typeof name === 'string' && NOT_WS.test(name)) {
      // A placement: {"stencil": name, "x", "y"[, "label"][, "subject"]}.
      // It carries no "type" — the client supplies the real elements from its
      // shelf, so the position is the whole payload. Which stencils exist is
      // the application's business, not this module's.
      return num(e.x) && num(e.y)
    }
    return truthy(e.type)
  }

  if (!els.every(ok)) return null
  els = els.filter((e) => !(typeof (e as Element).type === 'string' && opaque.has((e as Element).type as string)))
  if (!els.length && !delete_.length) return null
  return { elements: els as Element[], delete: delete_ }
}

// --- reading a reply -------------------------------------------------------------

/** What the decoder throws for text that is not JSON; private, because a reply
 *  that does not parse is ordinary input, not an error. */
class NotJson extends Error {}

const JSON_WS = ' \t\n\r'
const NUMBER = /(-?(?:0|[1-9][0-9]*))(\.[0-9]+)?([eE][-+]?[0-9]+)?/y

function skipWs(s: string, i: number): number {
  while (i < s.length && JSON_WS.includes(s[i])) i++
  return i
}

function decodeString(s: string, start: number): [string, number] {
  let i = start + 1
  let out = ''
  for (;;) {
    if (i >= s.length) throw new NotJson('unterminated string')
    const c = s[i]
    if (c === '"') return [out, i + 1]
    if (c.charCodeAt(0) < 0x20) throw new NotJson('control character in string')
    if (c !== '\\') {
      out += c
      i++
      continue
    }
    const e = s[i + 1]
    const simple: Record<string, string> = {
      '"': '"', '\\': '\\', '/': '/', b: '\b', f: '\f', n: '\n', r: '\r', t: '\t',
    }
    if (e !== undefined && Object.hasOwn(simple, e)) {
      out += simple[e]
      i += 2
    } else if (e === 'u' && /^[0-9a-fA-F]{4}$/.test(s.slice(i + 2, i + 6))) {
      out += String.fromCharCode(parseInt(s.slice(i + 2, i + 6), 16))
      i += 6
    } else {
      throw new NotJson('bad escape')
    }
  }
}

function decodeValue(s: string, i: number): [unknown, number] {
  const c = s[i]
  if (c === '"') return decodeString(s, i)
  if (c === '{') {
    const obj: Record<string, unknown> = {}
    i = skipWs(s, i + 1)
    if (s[i] === '}') return [obj, i + 1]
    for (;;) {
      if (s[i] !== '"') throw new NotJson('expected a key')
      const [key, afterKey] = decodeString(s, i)
      i = skipWs(s, afterKey)
      if (s[i] !== ':') throw new NotJson('expected a colon')
      const [value, afterValue] = decodeValue(s, skipWs(s, i + 1))
      Object.defineProperty(obj, key, { value, writable: true, enumerable: true, configurable: true })
      i = skipWs(s, afterValue)
      if (s[i] === '}') return [obj, i + 1]
      if (s[i] !== ',') throw new NotJson('expected a comma')
      i = skipWs(s, i + 1)
    }
  }
  if (c === '[') {
    const arr: unknown[] = []
    i = skipWs(s, i + 1)
    if (s[i] === ']') return [arr, i + 1]
    for (;;) {
      const [value, afterValue] = decodeValue(s, i)
      arr.push(value)
      i = skipWs(s, afterValue)
      if (s[i] === ']') return [arr, i + 1]
      if (s[i] !== ',') throw new NotJson('expected a comma')
      i = skipWs(s, i + 1)
    }
  }
  if (s.startsWith('null', i)) return [null, i + 4]
  if (s.startsWith('true', i)) return [true, i + 4]
  if (s.startsWith('false', i)) return [false, i + 5]
  NUMBER.lastIndex = i
  const m = NUMBER.exec(s)
  if (m) {
    const n = Number(m[0])
    return [m[2] === undefined && m[3] === undefined ? n + 0 : n, i + m[0].length]
  }
  if (s.startsWith('NaN', i)) return [NaN, i + 3]
  if (s.startsWith('Infinity', i)) return [Infinity, i + 8]
  if (s.startsWith('-Infinity', i)) return [-Infinity, i + 9]
  throw new NotJson('not a value')
}

function stripLeft(s: string): string {
  return s.replace(WS_LEAD, '')
}

function stripRight(s: string): string {
  return s.replace(WS_TRAIL, '')
}

/** Split a model reply into `[prose, patch]`.
 *
 *  The patch is the LAST balanced JSON object in the message that validates;
 *  it and any surrounding `excalidraw` label or code fence are stripped from
 *  the prose. If nothing parses, the whole message is prose and the patch is
 *  null — invalid drawing is dropped, never forced onto the canvas.
 *
 *  `options` are passed through to `validPatch`. */
export function extractPatch(message: string, options: PatchOptions = {}): [string, Patch | null] {
  let best: { start: number, end: number, patch: Patch } | null = null
  let i = 0
  const n = message.length
  while (i < n) {
    if (message[i] === '{') {
      let obj: unknown
      let end: number
      try {
        [obj, end] = decodeValue(message, i)
      } catch (err) {
        if (!(err instanceof NotJson)) throw err
        i += 1
        continue
      }
      const got = validPatch(obj, options)
      if (got !== null) best = { start: i, end, patch: got }  // keep the last valid patch
      i = end
    } else {
      i += 1
    }
  }
  if (best === null) return [stripRight(stripLeft(message)), null]
  const head = message.slice(0, best.start).replace(LABEL_TAIL, '')
  const tail = message.slice(best.end).replace(FENCE_HEAD, '')
  const prose = `${stripRight(head)}\n${stripLeft(tail)}`
  return [stripRight(stripLeft(prose)), best.patch]
}
