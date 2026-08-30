/**
 * The vocabulary contract.
 *
 * An application built on excalicore has a vocabulary: its kinds, which of
 * them are containers, which are connectors, what may sit inside what and
 * what may join what. This module holds the FORM of a vocabulary and the
 * checks a declared one implies; it never holds a particular vocabulary —
 * what a data store means, and that it is a node that sits in a zone, stays
 * with the application.
 *
 * Words: a VOCABULARY is one document per application, a name and its
 * kinds. A KIND has a ROLE — `node` (placed and may be joined), `container`
 * (holds nodes and other containers) or `connector` (joins two subjects). A
 * SUBJECT is a placed thing on the board, in the application's terms; a
 * CONNECTION is a connector between two subjects. A GRAPH is the subjects
 * and connections of one model, in the neutral shape the checker reads.
 *
 * `validateVocabulary()` checks a vocabulary document itself: every kind has
 * a name and a role, `within` and `ends` name real kinds of the right role,
 * `placed`, `directed`, `loops` and `parallel` hold their allowed values.
 * `checkGraph()` checks a graph against an already-valid vocabulary:
 * subjects and connections are declared once, of a known kind and the right
 * role, containment is honoured and free of cycles, and every connection's
 * ends are on the board, of an allowed pair of kinds, and — when the kind
 * forbids it — not a loop or a parallel of another.
 *
 * Both return sentences; an empty list means valid. Identifiers are quoted,
 * lists of identifiers sorted. Both halves are tested against
 * `corpus/vocabularies/`.
 *
 * Nothing in this file depends on Excalidraw or the DOM, and it never reads
 * an application's tables or tags — the graph is built and handed in.
 */

export type Role = 'node' | 'container' | 'connector'

// Loosely typed on purpose, like `stencils.ts`'s `Element`: a vocabulary or a
// graph is whatever JSON an application hands in, and pinning every field
// would turn a malformed fixture into a compile error instead of the
// sentence it should produce.
export type Kind = Record<string, unknown>
export type Vocabulary = Record<string, unknown>
export type Subject = Record<string, unknown>
export type Connection = Record<string, unknown>
export type Graph = Record<string, unknown>

export class VocabularyError extends Error {
  errors: string[]
  constructor(name: string, errors: string[]) {
    super(`Vocabulary "${name}" is not valid: ${errors.join(' ')}`)
    this.name = 'VocabularyError'
    this.errors = errors
  }
}

// --- small defensive readers --------------------------------------------------

function asObject(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null
}
function asArray(v: unknown): unknown[] | null {
  return Array.isArray(v) ? v : null
}
function asString(v: unknown): string | null {
  return typeof v === 'string' ? v : null
}
function nonEmptyString(v: unknown): string | null {
  const s = asString(v)
  return s && s.length ? s : null
}
function nameOf(vocabulary: unknown): string {
  return nonEmptyString(asObject(vocabulary)?.name) ?? '(unnamed)'
}

/** Sorted, quoted, joined with "and": `"a" and "b"`, `"a", "b" and "c"`. */
function quoteList(ids: string[]): string {
  const sorted = [...ids].sort()
  if (sorted.length === 1) return `"${sorted[0]}"`
  const head = sorted.slice(0, -1).map((id) => `"${id}"`)
  return `${head.join(', ')} and "${sorted[sorted.length - 1]}"`
}

// --- validating a vocabulary ---------------------------------------------------

/** The vocabulary document, checked. Returns violations as sentences; an
 *  empty list means the document is valid. Never throws on malformed input —
 *  a vocabulary with no name or no kinds is an error with a sentence, not a
 *  crash. */
export function validateVocabulary(vocabulary: Vocabulary): string[] {
  const errors: string[] = []
  const v = asObject(vocabulary)

  if (!nonEmptyString(v?.name)) errors.push('A vocabulary needs a name.')

  const rawKinds = v ? asArray(v.kinds) : null
  if (!rawKinds || !rawKinds.length) errors.push('A vocabulary needs at least one kind.')
  const entries = rawKinds ?? []

  const kindObjects: Record<string, unknown>[] = []
  entries.forEach((entry, i) => {
    const obj = asObject(entry)
    if (!obj) {
      errors.push(`Kind ${i + 1} is not an object.`)
      return
    }
    kindObjects.push(obj)
  })

  // Names known to this vocabulary — any kind object with a non-empty name,
  // regardless of whether the rest of it is valid.
  const known = new Map<string, Record<string, unknown>>()
  for (const kind of kindObjects) {
    const kn = nonEmptyString(kind.name)
    if (kn) known.set(kn, kind)
  }
  const roleOf = (kn: string): unknown => known.get(kn)?.role

  const counts = new Map<string, number>()
  for (const kind of kindObjects) {
    const kn = nonEmptyString(kind.name)
    if (kn) counts.set(kn, (counts.get(kn) ?? 0) + 1)
  }
  for (const [kn, count] of counts) {
    if (count > 1) errors.push(`Kind "${kn}" is declared twice.`)
  }

  for (const kind of kindObjects) {
    const kn = nonEmptyString(kind.name) ?? '(unnamed)'
    const roleRaw = kind.role
    let role: Role | undefined
    if (roleRaw === undefined) {
      errors.push(`Kind "${kn}" needs a role: node, container or connector.`)
    } else if (roleRaw !== 'node' && roleRaw !== 'container' && roleRaw !== 'connector') {
      errors.push(`Kind "${kn}" has an unknown role "${String(roleRaw)}"; a kind is a node, a container or a connector.`)
    } else {
      role = roleRaw
    }

    // within
    const hasWithin = kind.within !== undefined
    if (role === 'connector') {
      if (hasWithin) errors.push(`Kind "${kn}" is a connector and cannot sit within anything.`)
    } else if (hasWithin) {
      for (const w of asArray(kind.within) ?? []) {
        const wn = asString(w)
        if (wn === null) continue
        if (!known.has(wn)) {
          errors.push(`Kind "${kn}" may sit within "${wn}", which is not a kind of this vocabulary.`)
        } else if (roleOf(wn) !== 'container') {
          errors.push(`Kind "${kn}" may sit within "${wn}", which is not a container.`)
        }
      }
    }

    // placed
    let placed: 'always' | 'sometimes' = 'sometimes'
    if (kind.placed !== undefined) {
      if (kind.placed !== 'always' && kind.placed !== 'sometimes') {
        errors.push(`Kind "${kn}" is placed "${String(kind.placed)}"; a kind is placed always or sometimes.`)
      } else {
        placed = kind.placed
      }
    }
    if (placed === 'always' && !(asArray(kind.within) ?? []).length) {
      errors.push(`Kind "${kn}" is always placed but names nothing it may sit within.`)
    }

    // ends
    const hasEnds = kind.ends !== undefined
    if (role === 'connector') {
      const list = asArray(kind.ends)
      if (!list || !list.length) {
        errors.push(`Kind "${kn}" is a connector and needs ends.`)
      } else {
        for (const entry of list) {
          const pair = asArray(entry)
          if (!pair || pair.length !== 2 || typeof pair[0] !== 'string' || typeof pair[1] !== 'string') {
            errors.push(`Kind "${kn}" has an end that is not a pair of kinds.`)
            continue
          }
          const [from, to] = pair as [string, string]
          if (from !== '*' && !known.has(from)) {
            errors.push(`Kind "${kn}" may run from "${from}", which is not a kind of this vocabulary.`)
          }
          if (to !== '*' && !known.has(to)) {
            errors.push(`Kind "${kn}" may run to "${to}", which is not a kind of this vocabulary.`)
          }
        }
      }
    } else if (hasEnds) {
      errors.push(`Kind "${kn}" is not a connector and cannot have ends.`)
    }

    // directed, loops, parallel
    for (const field of ['directed', 'loops', 'parallel'] as const) {
      const val = kind[field]
      if (val !== undefined && typeof val !== 'boolean') {
        errors.push(`Kind "${kn}": ${field} must be true or false.`)
      }
    }

    // stencil, label
    if (kind.stencil !== undefined && (typeof kind.stencil !== 'string' || kind.stencil === '')) {
      errors.push(`Kind "${kn}" names an empty stencil.`)
    }
    if (kind.label !== undefined && (typeof kind.label !== 'string' || kind.label === '')) {
      errors.push(`Kind "${kn}" has an empty label.`)
    }
  }

  return errors
}

// --- containment cycles --------------------------------------------------------

/** Cycles in a functional graph (out-degree at most one per node): follow
 *  each chain, and when it revisits a node already on its own path, the tail
 *  from that node back to itself is a cycle. Every node is finalized once,
 *  so a chain that merges into an already-resolved tail or an
 *  already-reported cycle is not reported again. */
function findCycles(edges: Map<string, string>): string[][] {
  const cycles: string[][] = []
  const done = new Set<string>()
  for (const start of edges.keys()) {
    if (done.has(start)) continue
    const path: string[] = []
    const indexInPath = new Map<string, number>()
    let cur: string | undefined = start
    while (cur !== undefined && !done.has(cur)) {
      const seenAt = indexInPath.get(cur)
      if (seenAt !== undefined) {
        cycles.push(path.slice(seenAt))
        break
      }
      indexInPath.set(cur, path.length)
      path.push(cur)
      cur = edges.get(cur)
    }
    for (const id of path) done.add(id)
  }
  return cycles
}

// --- checking a connector's ends -----------------------------------------------

function endsAllow(kind: Record<string, unknown>, fromKind: string, toKind: string): boolean {
  const ends = asArray(kind.ends) ?? []
  const match = (pattern: unknown, actual: string) => pattern === '*' || pattern === actual
  const pairs = ends.map((e) => asArray(e)).filter((p): p is unknown[] => p !== null && p.length === 2)
  if (pairs.some((p) => match(p[0], fromKind) && match(p[1], toKind))) return true
  if (kind.directed === false) {
    return pairs.some((p) => match(p[0], toKind) && match(p[1], fromKind))
  }
  return false
}

// --- checking a graph -----------------------------------------------------------

/** A graph against a vocabulary. Throws `VocabularyError` when the
 *  vocabulary itself is not valid; otherwise returns violations of the
 *  graph as sentences, empty meaning the graph keeps the vocabulary. */
export function checkGraph(vocabulary: Vocabulary, graph: Graph): string[] {
  const vocabErrors = validateVocabulary(vocabulary)
  if (vocabErrors.length) throw new VocabularyError(nameOf(vocabulary), vocabErrors)

  const errors: string[] = []
  const v = asObject(vocabulary)!
  const kinds = new Map<string, Record<string, unknown>>()
  for (const entry of asArray(v.kinds) ?? []) {
    const obj = asObject(entry)
    const kn = obj ? nonEmptyString(obj.name) : null
    if (kn) kinds.set(kn, obj as Record<string, unknown>)
  }

  const g = asObject(graph)
  const rawSubjects = (g ? asArray(g.subjects) : null) ?? []
  const subjects = rawSubjects
    .map((s) => asObject(s))
    .filter((s): s is Record<string, unknown> => s !== null)
  const rawConnections = (g ? asArray(g.connections) : null) ?? []
  const connections = rawConnections
    .map((c) => asObject(c))
    .filter((c): c is Record<string, unknown> => c !== null)

  // Rule 9: declared once.
  const subjectCounts = new Map<string, number>()
  for (const s of subjects) {
    const id = asString(s.id)
    if (id !== null) subjectCounts.set(id, (subjectCounts.get(id) ?? 0) + 1)
  }
  for (const [id, count] of subjectCounts) {
    if (count > 1) errors.push(`Subject "${id}" is declared twice.`)
  }
  const connectionCounts = new Map<string, number>()
  for (const c of connections) {
    const id = asString(c.id)
    if (id !== null) connectionCounts.set(id, (connectionCounts.get(id) ?? 0) + 1)
  }
  for (const [id, count] of connectionCounts) {
    if (count > 1) errors.push(`Connection "${id}" is declared twice.`)
  }

  const subjectById = new Map<string, Record<string, unknown>>()
  for (const s of subjects) {
    const id = asString(s.id)
    if (id !== null) subjectById.set(id, s)
  }

  // Rules 10 + 11: subject kind/role, then containment.
  const containsEdge = new Map<string, string>()
  for (const s of subjects) {
    const id = asString(s.id) ?? '(no id)'
    const kindName = asString(s.kind)
    if (kindName === null || !kinds.has(kindName)) {
      errors.push(`Subject "${id}" has an unknown kind "${String(s.kind)}".`)
      continue
    }
    const kind = kinds.get(kindName)!
    if (kind.role === 'connector') {
      errors.push(`Subject "${id}" is of kind "${kindName}", which is a connector; a subject is a node or a container.`)
      continue
    }

    if (s.within !== undefined) {
      const target = asString(s.within)
      if (target !== null && target === id) {
        errors.push(`Subject "${id}" sits within itself.`)
      } else if (target !== null) {
        const targetSubject = subjectById.get(target)
        if (!targetSubject) {
          errors.push(`Subject "${id}" sits within "${target}", which is not on the board.`)
        } else {
          const targetKindName = asString(targetSubject.kind)
          const targetKind = targetKindName ? kinds.get(targetKindName) : undefined
          if (!targetKind || targetKind.role !== 'container') {
            errors.push(`Subject "${id}" sits within "${target}", which is not a container.`)
          } else if (!(asArray(kind.within) ?? []).includes(targetKindName)) {
            errors.push(`Subject "${id}" is a "${kindName}" and cannot sit within a "${targetKindName}".`)
          } else {
            containsEdge.set(id, target)
          }
        }
      }
    } else if (kind.placed === 'always') {
      errors.push(`Subject "${id}" is a "${kindName}", which must sit within a container.`)
    }
  }

  // Rule 12: containment cycles, only among edges rule 11 accepted.
  for (const cycle of findCycles(containsEdge)) {
    errors.push(`Subjects ${quoteList(cycle)} contain one another.`)
  }

  // Rules 10 + 13 + 14: connections.
  const parallelGroups = new Map<string, { id: string; from: string; to: string; kindName: string }[]>()
  for (const c of connections) {
    const id = asString(c.id) ?? '(no id)'
    const kindName = asString(c.kind)
    if (kindName === null || !kinds.has(kindName)) {
      errors.push(`Connection "${id}" has an unknown kind "${String(c.kind)}".`)
      continue
    }
    const kind = kinds.get(kindName)!
    if (kind.role !== 'connector') {
      errors.push(`Connection "${id}" is of kind "${kindName}", which is not a connector.`)
      continue
    }

    const from = asString(c.from)
    const to = asString(c.to)
    let missing = false
    if (from === null || !subjectById.has(from)) {
      errors.push(`Connection "${id}" runs from "${String(c.from)}", which is not on the board.`)
      missing = true
    }
    if (to === null || !subjectById.has(to)) {
      errors.push(`Connection "${id}" runs to "${String(c.to)}", which is not on the board.`)
      missing = true
    }
    if (missing) continue

    const fromSubject = subjectById.get(from as string)!
    const toSubject = subjectById.get(to as string)!
    const fromKind = asString(fromSubject.kind) ?? ''
    const toKind = asString(toSubject.kind) ?? ''

    if (!endsAllow(kind, fromKind, toKind)) {
      errors.push(`Connection "${id}" is a "${kindName}" and cannot run from a "${fromKind}" to a "${toKind}".`)
    }

    if (from === to && kind.loops !== true) {
      errors.push(`Connection "${id}" loops "${from}" onto itself.`)
    }

    if (kind.parallel === false) {
      const directed = kind.directed !== false
      const pairKey = directed ? `${from} ${to}` : [from, to].sort().join(' ')
      const key = `${kindName} ${pairKey}`
      const list = parallelGroups.get(key) ?? []
      list.push({ id, from: from as string, to: to as string, kindName })
      parallelGroups.set(key, list)
    }
  }

  for (const list of parallelGroups.values()) {
    if (list.length < 2) continue
    const first = list[0]
    for (const other of list.slice(1)) {
      errors.push(
        `Connections ${quoteList([first.id, other.id])} both run between "${first.from}" and "${first.to}"; a "${first.kindName}" allows one.`,
      )
    }
  }

  return errors
}

// --- lookups --------------------------------------------------------------------

/** Every kind of the vocabulary, in declared order; filtered to one role
 *  when given. Assumes a valid vocabulary — validate it first. */
export function kindsOf(vocabulary: Vocabulary, role?: Role): Kind[] {
  const v = asObject(vocabulary)
  const kinds: Kind[] = []
  for (const entry of (v ? asArray(v.kinds) : null) ?? []) {
    const obj = asObject(entry)
    if (!obj) continue
    if (role !== undefined && obj.role !== role) continue
    kinds.push(obj)
  }
  return kinds
}

/** The named kind, or undefined. */
export function kindOf(vocabulary: Vocabulary, name: string): Kind | undefined {
  return kindsOf(vocabulary).find((k) => k.name === name)
}

/** The kind's default stencil name, or undefined — the application resolves
 *  it against its own shelf; this module never does. */
export function stencilFor(vocabulary: Vocabulary, kind: string): string | undefined {
  const k = kindOf(vocabulary, kind)
  return k && typeof k.stencil === 'string' ? (k.stencil as string) : undefined
}
