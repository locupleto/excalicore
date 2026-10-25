/**
 * Storing Excalidraw elements without breaking them.
 *
 * An Excalidraw element carries fields no application should author and none
 * may discard: `seed` and `versionNonce` feed the rough-renderer and the
 * conflict resolver, `version` and `updated` order concurrent edits, `index`
 * fixes z-order, `boundElements` holds the back-references that keep labels
 * attached to their shapes. Normalize any of them away and the canvas does not
 * raise — it fails SILENTLY: a label detaches, a shape re-renders with a
 * different hand, an edit is quietly dropped on the next merge.
 *
 * So the storage rule is: extract the few columns worth querying, and keep
 * EVERYTHING else verbatim. The remainder is the arbiter, because it holds
 * whatever the element actually said, including keys this module has never
 * heard of. That makes the round trip exact by construction rather than by an
 * ever-growing list of known fields.
 *
 * These functions are pure. They return and accept plain rows; the application
 * owns its table, its SQL, and its transaction. This is the twin of
 * `excalicore.fidelity`, fixed against the same corpus (`corpus/fidelity`).
 *
 * The one place the twin cannot be byte-for-byte is the remainder's JSON text.
 * It is written the way Python's `json.dumps` writes it (`", "` and `": "`
 * separators, non-ASCII escaped, floats as Python prints them), but JavaScript
 * has one number type where Python has two, so an integer-valued number is
 * always written as an integer: Python would write `2.0` for a float that was
 * `2.0` in its source, and this writes `2` (an integer-valued number of 1e16
 * or more is taken for a float, and written with an exponent as Python does).
 * Read back, the two are the same element.
 */

/** Fields an application must never author, normalize, or drop. Named here so a
 *  reader knows why the remainder is stored verbatim; nothing enforces the list
 *  at runtime, because the point is precisely NOT to enumerate what to keep. */
export const BOOKKEEPING: ReadonlySet<string> = new Set([
  'seed', 'version', 'versionNonce', 'index', 'updated', 'boundElements',
])

/** The columns worth extracting: enough to query, order, and bound-box a scene
 *  without parsing every remainder. Deliberately excludes style — style is not
 *  queried, and every extracted column is a fidelity risk. */
export const COLUMNS: readonly string[] = ['id', 'type', 'x', 'y', 'width', 'height', 'angle']

/** One element, ready to insert: typed columns plus the verbatim remainder.
 *
 *  `anonymous` marks an element that arrived with no id of its own. The
 *  generated key keeps it addressable in storage, and `reassemble` knows not to
 *  hand a fabricated id back to the canvas. */
export interface ElementRow {
  readonly elementId: string
  readonly z: number
  readonly type: string
  readonly x: number | null
  readonly y: number | null
  readonly width: number | null
  readonly height: number | null
  readonly angle: number | null
  readonly json: string
  readonly anonymous: boolean
}

/** Anything row-like: an `ElementRow`, or a plain object keyed by column name.
 *  The key column may be spelt `elementId` or, as a SQL cursor returns it,
 *  `element_id`. */
export type RowLike = ElementRow | Record<string, unknown>

export interface RowOptions {
  /** The prefix of the key generated for an element with no id; default `anon-`. */
  anonPrefix?: string
}

type Element = Record<string, unknown>

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

/** `str(v)` for the values a type or an id can sensibly be. */
function pyStr(v: unknown): string {
  if (typeof v === 'string') return v
  if (typeof v === 'boolean') return v ? 'True' : 'False'
  return String(v)
}

// --- json.dumps ------------------------------------------------------------------

function dumpNumber(n: number): string {
  if (Number.isNaN(n)) return 'NaN'
  if (n === Infinity) return 'Infinity'
  if (n === -Infinity) return '-Infinity'
  if (Object.is(n, -0)) return '-0.0'
  // Beyond 1e16 an integer-valued number is read as a float: no id, timestamp
  // or seed is that large, and Python would print a float of that size with an
  // exponent.
  if (Number.isInteger(n) && Math.abs(n) < 1e16) return String(n)
  // A float. Python writes the shortest round-trip digits, as JavaScript does,
  // but switches to an exponent below 1e-4 where JavaScript waits for 1e-6, and
  // pads the exponent to two digits.
  const [mantissa, exponent] = n.toExponential().split('e')
  const exp = Number(exponent)
  if (exp < -4 || exp >= 16) {
    return `${mantissa}e${exp < 0 ? '-' : '+'}${String(Math.abs(exp)).padStart(2, '0')}`
  }
  return String(n)
}

const ESCAPES: Record<string, string> = {
  '"': '\\"', '\\': '\\\\', '\n': '\\n', '\r': '\\r', '\t': '\\t', '\b': '\\b', '\f': '\\f',
}

function dumpString(s: string): string {
  // ensure_ascii: everything outside space..~ is escaped, by UTF-16 unit.
  return `"${s.replace(/["\\]|[^ -~]/g, (c) =>
    ESCAPES[c] ?? `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`)}"`
}

/** `json.dumps(value)` with Python's defaults. */
function dumps(value: unknown): string {
  if (value === null || value === undefined) return 'null'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return dumpNumber(value)
  if (typeof value === 'string') return dumpString(value)
  if (Array.isArray(value)) return `[${value.map(dumps).join(', ')}]`
  const parts: string[] = []
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    if (v !== undefined) parts.push(`${dumpString(k)}: ${dumps(v)}`)
  }
  return `{${parts.join(', ')}}`
}

// --- explode / reassemble ------------------------------------------------------------

/** Elements to storage rows, in array order.
 *
 *  `z` is the array index: Excalidraw's element order IS its paint order, so
 *  it must be stored explicitly and read back with ORDER BY. */
export function explode(
  elements: readonly unknown[] | null | undefined,
  options: RowOptions = {},
): ElementRow[] {
  const anonPrefix = options.anonPrefix ?? 'anon-'
  const rows: ElementRow[] = []
  let z = 0
  for (const element of elements ?? []) {
    if (!isDict(element)) continue
    const rawId = element.id
    const anonymous = !(typeof rawId === 'string' && rawId !== '')
    // A column carries a value only when there IS one. A key whose value is
    // null stays in the remainder, because a NULL column cannot distinguish
    // "the element said null" from "the element never said it" — and losing
    // that difference is exactly the silent damage this module exists to
    // prevent.
    const rest: Element = {}
    for (const [k, v] of Object.entries(element)) {
      if (!COLUMNS.includes(k) || v === null || v === undefined) rest[k] = v
    }
    const column = (key: string): number | null => (element[key] ?? null) as number | null
    rows.push({
      elementId: anonymous ? `${anonPrefix}${z}` : String(rawId),
      z,
      type: truthy(element.type) ? pyStr(element.type) : '',
      x: column('x'), y: column('y'),
      width: column('width'), height: column('height'),
      angle: column('angle'),
      json: dumps(rest),
      anonymous,
    })
    z += 1
  }
  return rows
}

function getter(row: RowLike): (key: string) => unknown {
  const cells = row as Record<string, unknown>
  return (key) => {
    const v = key === 'elementId' ? (cells.elementId ?? cells.element_id) : cells[key]
    return v === undefined ? null : v
  }
}

/** `_truthy`: a stored flag may come back as 0, 1, "0" or "1". */
function flag(value: unknown): boolean {
  return truthy(value) && value !== 0 && value !== '0' && value !== ''
}

/** Storage rows back to elements, exactly, in z order.
 *
 *  Accepts anything row-like keyed by column name — an `ElementRow`, a plain
 *  object, a row object from a SQL driver — so an application can pass its
 *  cursor straight through.
 *
 *  Typed columns are re-inserted ONLY when the column holds a value. Anything
 *  the element said as null was left in the remainder by `explode`, so the
 *  remainder is the arbiter: an element that never had an `angle` must not gain
 *  one on the way back, and one that said `"angle": null` must not lose it. */
export function reassemble(
  rows: Iterable<RowLike> | null | undefined,
  options: RowOptions = {},
): Element[] {
  const anonPrefix = options.anonPrefix ?? 'anon-'
  const ordered = [...(rows ?? [])]
    .map((row) => ({ row, get: getter(row) }))
    .sort((a, b) => ((a.get('z') as number) || 0) - ((b.get('z') as number) || 0))
  const out: Element[] = []
  for (const { get } of ordered) {
    let element: unknown
    try {
      element = JSON.parse((truthy(get('json')) ? get('json') : '{}') as string)
    } catch {
      element = {}
    }
    if (!isDict(element)) element = {}
    const target = element as Element
    const elementId = get('elementId')
    const anonymous = flag(get('anonymous')) || (typeof elementId === 'string' && elementId.startsWith(anonPrefix))
    if (!anonymous && elementId !== null) target.id = elementId
    if (truthy(get('type'))) target.type = get('type')
    for (const column of ['x', 'y', 'width', 'height', 'angle']) {
      if (get(column) !== null) target[column] = get(column)
    }
    out.push(target)
  }
  return out
}

/** Every asset id the elements reference — the roots for asset collection.
 *
 *  Deleted elements count: Excalidraw keeps `isDeleted` elements in the array
 *  so an undo can bring them back, and an undo that restores an image whose
 *  file was collected restores a broken image. */
export function fileIds(elements: readonly unknown[] | null | undefined): Set<string> {
  const found = new Set<string>()
  for (const element of elements ?? []) {
    if (!isDict(element)) continue
    const value = element.fileId
    if (truthy(value)) found.add(pyStr(value))
  }
  return found
}

/** Asset ids present in `files` that no element references. */
export function unreferencedFiles(
  elements: readonly unknown[] | null | undefined,
  files: unknown,
): Set<string> {
  if (!isDict(files)) return new Set()
  const referenced = fileIds(elements)
  return new Set(Object.keys(files).filter((k) => !referenced.has(k)))
}
