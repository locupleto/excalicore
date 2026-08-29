/**
 * The stencil contract.
 *
 * An application has a graphical vocabulary — a data store, a person, a
 * server. What such an element MEANS belongs to the application. What it
 * looks like belongs to whoever drew it. What it must PROVIDE so that arrows
 * can bind to it, the application can find it again, and a language model can
 * talk about it, is the contract this module holds:
 *
 *   1. Exactly one element carries role `body`, and it is a bindable type.
 *   2. The body carries the `frame` — the subject's box relative to the body —
 *      and `frameOf()` is the only way back to it.
 *   3. At most one element carries role `label`; it is a text.
 *   4. Everything else is a `decoration`, hung on the body by an anchor: a
 *      point on the body's box in unit coordinates, a pixel offset that never
 *      scales, and a size mode — `fit` (ratios of the body) or `fixed` (pixels).
 *   5. All parts of an instance share one `groupIds` entry, the instance id
 *      (an instance of one part is left ungrouped: a group of one buys nothing).
 *   6. Tags live in `customData.stencil`, beside the application's own
 *      namespace, which this module never reads.
 *
 * Words: a STENCIL is a named set of elements that satisfies the contract; an
 * INSTANCE is a stencil placed on a canvas; a KIND is the application's word
 * for what it stands for, and never appears here.
 *
 * Nothing in this file depends on Excalidraw or the DOM. Elements are plain
 * objects in whatever shape the application feeds its canvas — skeletons for
 * `convertToExcalidrawElements`, or full elements for `restoreElements` — and
 * come back in the same shape with ids, geometry, groups and tags rewritten.
 */

export type Role = 'body' | 'label' | 'decoration'
export type SizeMode = 'fit' | 'fixed'

export interface Anchor { u: number; v: number }
export interface Offset { dx: number; dy: number }
/** The subject's box relative to the body: origin offset and size ratio. */
export interface Frame { dx: number; dy: number; sw: number; sh: number }
export interface Box { x: number; y: number; width: number; height: number }

/** `customData.stencil` — the namespace this module owns. */
export interface StencilTag {
  role: Role
  /** The stencil's name; written on every part of an instance. */
  name?: string
  /** The instance id; written on every part of an instance. */
  instance?: string
  /** Body only. */
  frame?: Frame
  /** Decorations and free labels: where on the body's box the part hangs. */
  anchor?: Anchor
  /** A pixel offset from the anchor, never scaled. */
  offset?: Offset
  /** `fit` scales with the body; `fixed` keeps its pixels. */
  size?: SizeMode
  /** Decorations only: drawn only when the instantiation asks for the variant. */
  variant?: string
}

// Loosely typed on purpose: the element shape is Excalidraw's, and pinning it
// to their internal types would make every package bump a compile error.
export type Element = Record<string, unknown>

export interface Stencil {
  name: string
  elements: Element[]
  /** Provenance of an imported stencil, e.g. `armory/cylinder@3f9c1a2e`. */
  source?: string
  /** ISO date the import happened. */
  imported?: string
}

/** A role, or a role with the anchoring fields an element should carry. */
export type RoleSpec = Role | (Partial<Omit<StencilTag, 'role'>> & { role: Role })
export type RoleMap = Record<string, RoleSpec>

export interface LibraryItem {
  name?: string
  elements?: unknown[]
}

/** A style override at instantiation. The body takes all of it (the paint);
 *  labels and decorations take only the ink and the opacity (the tint). */
export type Style = Record<string, string | number>

/** The fields a body accepts from a style override. */
export const PAINT_FIELDS: readonly string[] = [
  'strokeColor', 'backgroundColor', 'fillStyle', 'strokeStyle',
  'strokeWidth', 'opacity', 'roughness',
]
/** The fields every other part accepts: a background on an open line means
 *  nothing, and only the body is ever read back. */
export const TINT_FIELDS: readonly string[] = ['strokeColor', 'opacity']

/** Types an arrow can bind to. `line`, `arrow`, `freedraw` and `text` are
 *  not among them: Excalidraw's converter throws on a binding to those and
 *  loses the whole batch. */
export const BINDABLE_TYPES: readonly string[] = ['rectangle', 'ellipse', 'diamond', 'image']

export interface Placement {
  x: number
  y: number
  /** The subject's box. Omitted: the stencil's natural size. */
  width?: number
  height?: number
}

export interface InstantiateOptions {
  /** Fills the label slot. Omitted: the stencil's placeholder text stays. */
  label?: string
  /** Application namespaces written beside `stencil` in `customData` of every
   *  part — `{ bastion: { kind: 'component', key: 'web-app' } }`. */
  tags?: Record<string, unknown>
  style?: Style
  /** Which optional decorations to draw. */
  variants?: Iterable<string>
  /** The instance id. Omitted: a fresh one. */
  instance?: string
  /** Element ids. Omitted: fresh ones. Called once per part, with the
   *  stencil's own element and its role, so an application can derive stable
   *  ids from the stencil's. A caption made by `caption` is called with a
   *  source whose id is `caption`. */
  id?: (source: Element, role: Role) => string
  /** When the stencil has no label part and `label` is given, a caption is
   *  drawn beneath the subject: a text element with these fields on top of
   *  the defaults (`fontSize` 16), centred under the box. Omitted: no
   *  caption, and the label goes nowhere. */
  caption?: Element
}

export class StencilError extends Error {
  errors: string[]
  constructor(name: string, errors: string[]) {
    super(`Stencil "${name}" is not valid: ${errors.join(' ')}`)
    this.name = 'StencilError'
    this.errors = errors
  }
}

// --- reading tags ------------------------------------------------------------

/** The stencil tag on an element, or null. */
export function tagOf(el: Element): StencilTag | null {
  const cd = el.customData
  if (!cd || typeof cd !== 'object') return null
  const tag = (cd as { stencil?: unknown }).stencil
  if (!tag || typeof tag !== 'object') return null
  const role = (tag as { role?: unknown }).role
  return typeof role === 'string' ? (tag as StencilTag) : null
}

/** The instance an element belongs to, or null.
 *
 *  Reads the `stamp` / `stampGroup` tags the Armory and the Academy wrote
 *  before this contract existed as an alias, so a board placed under the old
 *  scheme is still one object to `instances()` and `sweep()`. The alias is
 *  kept for one release. */
export function instanceOf(el: Element): string | null {
  const tag = tagOf(el)
  if (tag?.instance) return String(tag.instance)
  const cd = el.customData
  if (cd && typeof cd === 'object') {
    const legacy = (cd as { stampGroup?: unknown }).stampGroup
    if (typeof legacy === 'string' && legacy) return legacy
  }
  return null
}

function num(v: unknown, fallback = 0): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback
}

function boxOf(el: Element): Box {
  return { x: num(el.x), y: num(el.y), width: num(el.width), height: num(el.height) }
}

function bbox(els: Element[]): Box | null {
  if (!els.length) return null
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity
  for (const el of els) {
    const b = boxOf(el)
    x1 = Math.min(x1, b.x)
    y1 = Math.min(y1, b.y)
    x2 = Math.max(x2, b.x + b.width)
    y2 = Math.max(y2, b.y + b.height)
  }
  return { x: x1, y: y1, width: x2 - x1, height: y2 - y1 }
}

function finite(...values: unknown[]): boolean {
  return values.every((v) => typeof v === 'number' && Number.isFinite(v))
}

function idOf(el: Element): string {
  return typeof el.id === 'string' ? el.id : '(no id)'
}

// --- validation --------------------------------------------------------------

/** The contract, checked. Returns the violations as sentences; an empty list
 *  means the elements are a valid stencil. Validate at load time, never at
 *  draw time: a stencil with no body is an error with a sentence, not a
 *  component that silently cannot be connected to. */
export function validateStencil(elements: Element[]): string[] {
  const errors: string[] = []
  const live = elements.filter((el) => el && typeof el === 'object' && !el.isDeleted)
  if (!live.length) return ['A stencil needs at least one element.']

  const bodies: Element[] = []
  const labels: Element[] = []
  for (const el of live) {
    const tag = tagOf(el)
    if (!tag) {
      errors.push(`Element "${idOf(el)}" has no role; every part is a body, a label or a decoration.`)
      continue
    }
    if (tag.role === 'body') bodies.push(el)
    else if (tag.role === 'label') labels.push(el)
    else if (tag.role !== 'decoration') {
      errors.push(`Element "${idOf(el)}" has an unknown role "${String(tag.role)}".`)
    }
  }

  if (bodies.length !== 1) {
    const which = bodies.length ? ` (${bodies.map(idOf).join(', ')})` : ''
    errors.push(
      `A stencil needs exactly one element with role "body"; this one has ${bodies.length}${which}.`,
    )
  }
  const body = bodies.length === 1 ? bodies[0] : null
  if (body) {
    if (!BINDABLE_TYPES.includes(String(body.type))) {
      errors.push(
        `The body must be a rectangle, ellipse, diamond or image so arrows can bind to it; "${String(body.type)}" cannot be bound to.`,
      )
    }
    const frame = tagOf(body)?.frame
    if (!frame || typeof frame !== 'object') {
      errors.push('The body must carry a frame {dx, dy, sw, sh}: the subject\'s box relative to the body.')
    } else if (!finite(frame.dx, frame.dy, frame.sw, frame.sh) || frame.sw <= 0 || frame.sh <= 0) {
      errors.push('The body\'s frame needs finite dx and dy and positive sw and sh.')
    }
  }

  if (labels.length > 1) {
    errors.push(`At most one element may carry role "label"; found ${labels.length} (${labels.map(idOf).join(', ')}).`)
  }
  if (labels.length && body && body.label && typeof body.label === 'object') {
    errors.push(`The body "${idOf(body)}" already carries a label property; a label element on top of it is one label too many.`)
  }
  for (const label of labels) {
    if (label.type !== 'text') {
      errors.push(`The label must be a text element; "${idOf(label)}" is a ${String(label.type)}.`)
    }
    const container = label.containerId
    if (container != null && body && container !== body.id) {
      errors.push(`A bound label's containerId must be the body "${idOf(body)}"; "${idOf(label)}" is bound to "${String(container)}".`)
    }
  }

  for (const el of live) {
    const tag = tagOf(el)
    if (!tag || tag.role === 'body') continue
    if (tag.anchor !== undefined && !finite(tag.anchor?.u, tag.anchor?.v)) {
      errors.push(`Part "${idOf(el)}": anchor needs finite u and v.`)
    }
    if (tag.offset !== undefined && !finite(tag.offset?.dx, tag.offset?.dy)) {
      errors.push(`Part "${idOf(el)}": offset needs finite dx and dy.`)
    }
    if (tag.size !== undefined && tag.size !== 'fit' && tag.size !== 'fixed') {
      errors.push(`Part "${idOf(el)}": size must be "fit" or "fixed", not "${String(tag.size)}".`)
    }
    if (tag.variant !== undefined && (typeof tag.variant !== 'string' || !tag.variant)) {
      errors.push(`Part "${idOf(el)}": variant must be a non-empty string.`)
    }
    if (tag.variant !== undefined && tag.role === 'label') {
      errors.push(`Part "${idOf(el)}": a label cannot be a variant; only decorations are optional.`)
    }
  }
  return errors
}

/** The body of a stencil or an instance, or null. */
export function bodyOf(elements: Element[]): Element | null {
  return elements.find((el) => !el.isDeleted && tagOf(el)?.role === 'body') ?? null
}

/** The subject's box, read off the body and its frame. Null when there is no
 *  body or no frame. This is the ONLY way back from an instance to what it
 *  stands for; reading the geometry off a caption or a rule is the bug the
 *  frame exists to prevent. */
export function frameOf(elements: Element[]): Box | null {
  const body = bodyOf(elements)
  const frame = body ? tagOf(body)?.frame : undefined
  if (!body || !frame || !finite(frame.dx, frame.dy, frame.sw, frame.sh)) return null
  const b = boxOf(body)
  return { x: b.x + frame.dx, y: b.y + frame.dy, width: b.width * frame.sw, height: b.height * frame.sh }
}

// --- from a library item -----------------------------------------------------

function area(el: Element): number {
  return Math.abs(num(el.width)) * Math.abs(num(el.height))
}

/** The role map a library item implies on its own: whatever roles its
 *  elements already carry in `customData.stencil.role`, and — when none of
 *  them is a body — the largest element of a bindable type as the body. A
 *  symbol drawn by hand has one obvious thing to attach an arrow to (the
 *  head of a figure, the chassis of a machine) and that is usually its
 *  biggest closed shape; the map is a default a user can override by marking
 *  a role, never a decision the library insists on. Returns an empty map for
 *  an item with nothing bindable, which `fromLibraryItem` then refuses. */
export function defaultRoles(item: LibraryItem): RoleMap {
  const roles: RoleMap = {}
  const live = (item.elements ?? []).filter(
    (e): e is Element => Boolean(e) && typeof e === 'object' && !(e as Element).isDeleted,
  )
  let hasBody = false
  for (const el of live) {
    const tag = tagOf(el)
    if (tag && typeof el.id === 'string') {
      roles[el.id] = tag
      if (tag.role === 'body') hasBody = true
    }
  }
  if (!hasBody) {
    let best: Element | null = null
    for (const el of live) {
      if (!BINDABLE_TYPES.includes(String(el.type)) || typeof el.id !== 'string') continue
      if (!best || area(el) > area(best)) best = el
    }
    if (best) roles[best.id as string] = 'body'
  }
  return roles
}

/** A stencil from an Excalidraw library item and a role map, so a symbol
 *  drawn on any canvas can become one. The map names the body (and the label,
 *  if any) by element id; anything not named is a decoration. Fields the map
 *  does not give are derived from the drawing: a missing frame is the box of
 *  everything but the label, relative to the body; a missing anchor is where
 *  the part's origin sits on the body's box; size defaults to `fit` for
 *  shapes and `fixed` for text. Throws `StencilError` when the result does
 *  not satisfy the contract. */
export function fromLibraryItem(item: LibraryItem, roles: RoleMap): Stencil {
  const name = typeof item.name === 'string' ? item.name.trim() : ''
  const source = (item.elements ?? []).filter(
    (e): e is Element => Boolean(e) && typeof e === 'object' && !(e as Element).isDeleted,
  )
  if (!name) throw new StencilError('(unnamed)', ['A stencil needs a name.'])

  const specOf = (el: Element): Partial<StencilTag> & { role: Role } => {
    const spec = typeof el.id === 'string' ? roles[el.id] : undefined
    if (spec === undefined) return { role: 'decoration' }
    return typeof spec === 'string' ? { role: spec } : spec
  }

  const tagged = source.map((el) => ({ el, spec: specOf(el) }))
  const bodies = tagged.filter((t) => t.spec.role === 'body')
  const body = bodies.length === 1 ? bodies[0].el : null
  const bodyBox = body ? boxOf(body) : null
  const subject = bbox(tagged.filter((t) => t.spec.role !== 'label').map((t) => t.el))

  const elements = tagged.map(({ el, spec }) => {
    const tag: StencilTag = { ...spec }
    if (spec.role === 'body') {
      if (!tag.frame && bodyBox && subject) {
        tag.frame = {
          dx: subject.x - bodyBox.x,
          dy: subject.y - bodyBox.y,
          sw: bodyBox.width ? subject.width / bodyBox.width : 1,
          sh: bodyBox.height ? subject.height / bodyBox.height : 1,
        }
      }
    } else {
      const bound = spec.role === 'label' && typeof el.containerId === 'string'
      if (!bound && !tag.anchor && bodyBox) {
        const b = boxOf(el)
        tag.anchor = {
          u: bodyBox.width ? (b.x - bodyBox.x) / bodyBox.width : 0,
          v: bodyBox.height ? (b.y - bodyBox.y) / bodyBox.height : 0,
        }
      }
      if (!bound && !tag.offset) tag.offset = { dx: 0, dy: 0 }
      if (!tag.size) tag.size = el.type === 'text' ? 'fixed' : 'fit'
    }
    const cd = el.customData && typeof el.customData === 'object' ? (el.customData as object) : {}
    return { ...el, customData: { ...cd, stencil: tag } }
  })

  const errors = validateStencil(elements)
  if (errors.length) throw new StencilError(name, errors)
  return { name, elements }
}

// --- instantiation -----------------------------------------------------------

let seq = 0
function freshId(prefix: string): string {
  seq += 1
  return `${prefix}${Date.now().toString(36)}${seq.toString(36)}${Math.random().toString(36).slice(2, 7)}`
}

function scalePoints(points: unknown, sx: number, sy: number): unknown {
  if (!Array.isArray(points)) return points
  return points.map((p) =>
    Array.isArray(p) && p.length >= 2 ? [num(p[0]) * sx, num(p[1]) * sy, ...p.slice(2)] : p,
  )
}

/** Place a stencil on a canvas.
 *
 *  `at` is the SUBJECT's box — what the instance stands for — not the body's;
 *  the body lands wherever the frame says it must so that `frameOf()` gives
 *  `at` back exactly. With `width`/`height` omitted the instance is drawn at
 *  the stencil's natural size. Scaling is per axis: `fit` parts and the body
 *  stretch with the subject, `fixed` parts keep their pixels and follow their
 *  anchor.
 *
 *  Every part gets a fresh id (internal bindings remapped), the instance id
 *  as its one group, and a `customData.stencil` tag beside the application's
 *  `tags`. Element order is preserved: whatever the stencil drew behind its
 *  body stays behind it. */
export function instantiate(
  stencil: Stencil,
  at: Placement,
  options: InstantiateOptions = {},
): Element[] {
  const errors = validateStencil(stencil.elements)
  if (errors.length) throw new StencilError(stencil.name, errors)

  const source = stencil.elements.filter((el) => !el.isDeleted)
  const body = bodyOf(source) as Element
  const frame = tagOf(body)!.frame as Frame
  const natural = frameOf(source) as Box
  const sx = at.width !== undefined && natural.width ? at.width / natural.width : 1
  const sy = at.height !== undefined && natural.height ? at.height / natural.height : 1
  const b = boxOf(body)
  // The frame says subject = body + offset, so body = subject - offset; the
  // round trip through frameOf() is then exact to floating-point precision.
  const bodyAt: Box = {
    x: at.x - frame.dx * sx,
    y: at.y - frame.dy * sy,
    width: b.width * sx,
    height: b.height * sy,
  }

  const wanted = new Set(options.variants ?? [])
  const instance = options.instance ?? freshId('i-')
  const ids = new Map<string, string>()
  const parts = source.filter((el) => {
    const variant = tagOf(el)?.variant
    return variant === undefined || wanted.has(variant)
  })
  for (const el of parts) {
    const role = tagOf(el)!.role
    const id = options.id ? options.id(el, role) : freshId('e-')
    ids.set(typeof el.id === 'string' ? el.id : `#${ids.size}`, id)
  }
  const remap = (id: unknown): string | null =>
    typeof id === 'string' ? (ids.get(id) ?? null) : null
  const remapBinding = (binding: unknown): unknown => {
    if (!binding || typeof binding !== 'object') return binding
    const to = remap((binding as { elementId?: unknown }).elementId)
    return to ? { ...(binding as object), elementId: to } : null
  }

  // A group of one buys nothing and makes a plain box select as a group, so
  // a single-part instance is left ungrouped; the tag still names its
  // instance, which is what instances() and sweep() read.
  const group = parts.length > 1 ? [instance] : undefined
  const placed = parts.map((el, index) => {
    const tag = tagOf(el)!
    const out: Element = { ...el }
    out.id = ids.get(typeof el.id === 'string' ? el.id : `#${index}`) ?? freshId('e-')
    if (group) out.groupIds = group
    else delete out.groupIds

    if (tag.role === 'body') {
      out.x = bodyAt.x
      out.y = bodyAt.y
      out.width = bodyAt.width
      out.height = bodyAt.height
      out.points = scalePoints(el.points, sx, sy)
    } else if (tag.role === 'label' && typeof el.containerId === 'string') {
      // A bound label follows its container; Excalidraw lays it out on
      // render, so centring it is a courtesy for anything that reads the
      // scene before Excalidraw does.
      const lb = boxOf(el)
      out.x = bodyAt.x + (bodyAt.width - lb.width) / 2
      out.y = bodyAt.y + (bodyAt.height - lb.height) / 2
    } else {
      const anchor = tag.anchor ?? { u: 0, v: 0 }
      const offset = tag.offset ?? { dx: 0, dy: 0 }
      const fit = (tag.size ?? (el.type === 'text' ? 'fixed' : 'fit')) === 'fit'
      out.x = bodyAt.x + anchor.u * bodyAt.width + offset.dx
      out.y = bodyAt.y + anchor.v * bodyAt.height + offset.dy
      if (fit) {
        out.width = num(el.width) * sx
        out.height = num(el.height) * sy
        out.points = scalePoints(el.points, sx, sy)
        if (el.type === 'text' && typeof el.fontSize === 'number') {
          out.fontSize = el.fontSize * Math.min(sx, sy)
        }
      }
    }
    if (out.points === undefined) delete out.points

    if (tag.role === 'label' && options.label !== undefined) {
      out.text = options.label
      if ('originalText' in out) out.originalText = options.label
    }
    // A skeleton for Excalidraw's converter may carry its bound label as a
    // `label: {text}` property on the container instead of a text element;
    // that is a label slot too.
    if (tag.role === 'body' && options.label !== undefined && el.label && typeof el.label === 'object') {
      out.label = { ...(el.label as object), text: options.label }
    }

    if (typeof el.containerId === 'string') out.containerId = remap(el.containerId)
    if (typeof el.frameId === 'string') out.frameId = remap(el.frameId)
    if (Array.isArray(el.boundElements)) {
      out.boundElements = (el.boundElements as { id?: unknown }[])
        .map((ref) => ({ ...ref, id: remap(ref.id) }))
        .filter((ref) => ref.id)
    }
    if ('startBinding' in el) out.startBinding = remapBinding(el.startBinding)
    if ('endBinding' in el) out.endBinding = remapBinding(el.endBinding)

    const stencilTag: StencilTag = { name: stencil.name, instance, role: tag.role }
    if (tag.role === 'body') {
      stencilTag.frame = { dx: frame.dx * sx, dy: frame.dy * sy, sw: frame.sw, sh: frame.sh }
    } else {
      if (tag.anchor) stencilTag.anchor = tag.anchor
      if (tag.offset) stencilTag.offset = tag.offset
      if (tag.size) stencilTag.size = tag.size
      if (tag.variant) stencilTag.variant = tag.variant
    }
    out.customData = { ...(options.tags ?? {}), stencil: stencilTag }
    return out
  })

  if (options.label !== undefined && options.caption && !parts.some((el) => tagOf(el)!.role === 'label')) {
    const text = options.label
    const fontSize = typeof options.caption.fontSize === 'number' ? options.caption.fontSize : 16
    const subject: Box = { x: at.x, y: at.y, width: natural.width * sx, height: natural.height * sy }
    const cx = subject.x + subject.width / 2
    const dx = -text.length * fontSize * 0.3  // the usual guess at half a string's width
    const dy = 8
    const source: Element = { id: 'caption', type: 'text' }
    const caption: Element = {
      type: 'text',
      fontSize,
      ...options.caption,
      id: options.id ? options.id(source, 'label') : freshId('e-'),
      text,
      originalText: text,
      x: cx + dx,
      y: subject.y + subject.height + dy,
      customData: {
        ...(options.tags ?? {}),
        stencil: {
          name: stencil.name, instance, role: 'label',
          anchor: {
            u: bodyAt.width ? (cx - bodyAt.x) / bodyAt.width : 0.5,
            v: bodyAt.height ? (subject.y + subject.height - bodyAt.y) / bodyAt.height : 1,
          },
          offset: { dx, dy },
          size: 'fixed',
        } satisfies StencilTag,
      },
    }
    placed.push(caption)
    if (placed.length > 1) for (const el of placed) el.groupIds = [instance]
  }

  return placed.map((el) => (options.style ? restyleOne(el, options.style) : el))
}

// --- style -------------------------------------------------------------------

function restyleOne(el: Element, style: Style): Element {
  const tag = tagOf(el)
  if (!tag) return el
  const fields = tag.role === 'body' ? PAINT_FIELDS : TINT_FIELDS
  const out = { ...el }
  for (const field of fields) {
    if (style[field] !== undefined) out[field] = style[field]
  }
  // A label carried as a property on the body is a label all the same, and
  // takes the tint.
  if (tag.role === 'body' && el.label && typeof el.label === 'object') {
    const label: Element = { ...(el.label as Element) }
    for (const field of TINT_FIELDS) {
      if (style[field] !== undefined && field in label) label[field] = style[field]
    }
    out.label = label
  }
  return out
}

/** Paint on the body, tint on everything else. Parts without a stencil tag
 *  are returned untouched. */
export function restyle(parts: Element[], style: Style): Element[] {
  return parts.map((el) => restyleOne(el, style))
}

// --- finding and removing ----------------------------------------------------

/** Every instance on a board, keyed by instance id, parts in board order. */
export function instances(elements: Element[]): Map<string, Element[]> {
  const out = new Map<string, Element[]>()
  for (const el of elements) {
    if (!el || typeof el !== 'object' || el.isDeleted) continue
    const id = instanceOf(el)
    if (!id) continue
    const parts = out.get(id)
    if (parts) parts.push(el)
    else out.set(id, [el])
  }
  return out
}

/** The board without the named instances: every part goes, and an arrow that
 *  was bound to one of them loses that binding rather than pointing at an
 *  element that is no longer there. Elements are removed from the array;
 *  an application that wants Excalidraw's undo to see the deletion marks
 *  `isDeleted` on what this returns as gone instead. */
export function sweep(elements: Element[], instanceIds: Iterable<string>): Element[] {
  const gone = new Set(instanceIds)
  const removed = new Set<string>()
  const kept: Element[] = []
  for (const el of elements) {
    const id = el && typeof el === 'object' ? instanceOf(el) : null
    if (id && gone.has(id)) {
      if (typeof el.id === 'string') removed.add(el.id)
    } else kept.push(el)
  }
  if (!removed.size) return kept
  return kept.map((el) => {
    let out = el
    for (const side of ['startBinding', 'endBinding'] as const) {
      const binding = el[side] as { elementId?: unknown } | null | undefined
      if (binding && typeof binding === 'object' && typeof binding.elementId === 'string' && removed.has(binding.elementId)) {
        out = { ...out, [side]: null }
      }
    }
    if (Array.isArray(el.boundElements)) {
      const refs = el.boundElements as { id?: unknown }[]
      if (refs.some((ref) => typeof ref.id === 'string' && removed.has(ref.id))) {
        out = { ...out, boundElements: refs.filter((ref) => !(typeof ref.id === 'string' && removed.has(ref.id))) }
      }
    }
    if (typeof el.containerId === 'string' && removed.has(el.containerId)) {
      out = { ...out, containerId: null }
    }
    return out
  })
}

// --- binding to an instance ------------------------------------------------------

/** Skeleton arrows with `start`/`end` refs that name an INSTANCE re-pointed
 *  at that instance's body, so a language model can bind to the one id the
 *  skeleton dialect shows it for a placed stencil. Refs that already name an
 *  element, or nothing on the board, are left as they are. */
export function bindToBodies(skeletons: Element[], board: Element[]): Element[] {
  const bodies = new Map<string, string>()
  for (const [id, parts] of instances(board)) {
    const body = bodyOf(parts)
    if (body && typeof body.id === 'string') bodies.set(id, body.id)
  }
  if (!bodies.size) return skeletons
  return skeletons.map((el) => {
    let out = el
    for (const side of ['start', 'end'] as const) {
      const ref = el[side] as { id?: unknown } | undefined
      if (ref && typeof ref === 'object' && typeof ref.id === 'string' && bodies.has(ref.id)) {
        out = { ...out, [side]: { ...ref, id: bodies.get(ref.id) } }
      }
    }
    return out
  })
}
