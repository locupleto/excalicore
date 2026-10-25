/**
 * The elements module, against the corpus.
 *
 * Run:  npm test          (Node strips the types itself; no build step)
 *
 * Each `corpus/elements/*.json` file holds a `{doc, cases}` object; every case
 * names the function it exercises (`fn`) and carries its inputs and the `expect`
 * the Python implementation produced. Every case runs under a counting source
 * (ids `id-0001`..., nonces 1, 2, 3..., a fixed clock), so a whole built element
 * is compared, not just a few of its fields. Floats are compared with a 1e-6
 * tolerance, the fixtures being rounded to 6 decimals.
 *
 * Beside the corpus, the structural check: every element the module builds
 * carries every field Excalidraw's element types require.
 */
import test from 'node:test'
import assert from 'node:assert/strict'

import {
  FONT_HELVETICA,
  addLabel,
  baseElement,
  bindEnd,
  boundaryPoint,
  containerHeightFor,
  detach,
  fitLabel,
  frameElement,
  labelOf,
  lineHeight,
  linearElement,
  measureText,
  newId,
  nonce,
  nowMs,
  refitArrow,
  routeBetween,
  routeOf,
  setRoute,
  setSource,
  shapeElement,
  textElement,
  textRoom,
  textWidth,
  touch,
  unlistBound,
  wrapText,
  type El,
} from '../src/elements.ts'
import type { Box } from '../src/geometry.ts'
import { close, countingSource, elementsFixture, type Case } from './elementsCorpus.ts'

const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v))
const byIdOf = (elements: El[]): Record<string, El> => Object.fromEntries(elements.map((e) => [e.id, e]))
const idsOf = (elements: El[]): string[] => elements.map((e) => e.id)
const endOf = (v: { shape: string; box: Box } | null | undefined): [string, Box] | null =>
  v === null || v === undefined ? null : [v.shape, v.box]

/** Run one case against the TypeScript implementation. */
export function runCase(c: Case): unknown {
  countingSource()
  const o = clone(c) as Case
  const opt = <K extends string>(...keys: K[]): Record<string, unknown> =>
    Object.fromEntries(keys.filter((k) => o[k] !== undefined).map((k) => [k, o[k]]))
  try {
    switch (o.fn) {
      case 'lineHeight':
        return lineHeight(o.font)
      case 'textWidth':
        return textWidth(o.line, o.size, o.font, { charEm: o.charEm ?? null })
      case 'measureText':
        return measureText(o.text, o.size, o.font, { charEm: o.charEm ?? null })
      case 'wrapText':
        return wrapText(o.text, o.width, o.size, o.font, { charEm: o.charEm ?? null })
      case 'textRoom':
        return textRoom(o.container, o.padding)
      case 'containerHeightFor':
        return containerHeightFor(o.textHeight, o.kind, o.padding)
      case 'baseElement':
        return baseElement(o.kind, o.x, o.y, o.w, o.h, { roughness: o.roughness, ...o.over })
      case 'textElement':
        return textElement(o.text, o.x, o.y, {
          font: o.font, roughness: o.roughness, container: o.container ?? null, ...opt('size', 'padding'), ...o.over,
        })
      case 'shapeElement':
        return shapeElement(o.kind, o.x, o.y, o.w, o.h, { roughness: o.roughness, ...o.over })
      case 'frameElement':
        return frameElement(o.x, o.y, o.w, o.h, o.frameName ?? null, { ...opt('roughness'), ...o.over })
      case 'linearElement':
        return linearElement(o.kind, o.route, {
          roughness: o.roughness, startHead: o.startHead ?? null, endHead: o.endHead ?? null, ...o.over,
        })
      case 'touch': {
        const returns = touch(o.element)
        assert.equal(returns, o.element)
        return { returns, after: { element: o.element } }
      }
      case 'boundaryPoint':
        return boundaryPoint(o.shape, o.box, o.aim, o.gap)
      case 'routeBetween':
        return routeBetween(o.points ?? null, endOf(o.start), endOf(o.end), opt('gap'))
      case 'routeOf':
        return routeOf(o.linear)
      case 'setRoute':
        setRoute(o.linear, o.route)
        return { returns: null, after: { linear: o.linear } }
      case 'unlistBound': {
        const returns = unlistBound(o.host, o.memberId)
        return { returns, after: { host: o.host } }
      }
      case 'labelOf':
        return labelOf(o.container, byIdOf(o.elements))?.id ?? null
      case 'addLabel': {
        const returns = addLabel(o.container, o.text, {
          font: o.font, roughness: o.roughness, ...opt('size', 'padding'), ...o.over,
        })
        return { returns, after: { container: o.container } }
      }
      case 'fitLabel': {
        const changed = fitLabel(o.container, o.label, opt('text', 'size', 'padding'))
        return { returns: idsOf(changed), after: { container: o.container, label: o.label } }
      }
      case 'bindEnd': {
        const byId = byIdOf(o.elements)
        const changed = bindEnd(byId[o.arrow], o.which, o.host ? byId[o.host] : null, {
          byId: o.byId ? byId : null, ...opt('gap'),
        })
        return { returns: idsOf(changed), after: { elements: o.elements } }
      }
      case 'refitArrow': {
        const byId = byIdOf(o.elements)
        const returns = refitArrow(byId[o.arrow], byId, opt('gap'))
        return { returns, after: { elements: o.elements } }
      }
      case 'detach': {
        const byId = byIdOf(o.elements)
        const [gone, changed] = detach(byId[o.element], byId)
        return { returns: [gone, idsOf(changed)], after: { elements: o.elements } }
      }
      default:
        throw new Error(`unknown fn ${o.fn} in the corpus`)
    }
  } catch (err) {
    if (err instanceof Error && !err.message.startsWith('unknown fn')) return { throws: true }
    throw err
  }
}

function checkFile(name: string, only?: (c: Case) => boolean): void {
  const fx = elementsFixture(name)
  assert.ok(fx.doc, `${name}.json needs a doc string`)
  assert.ok(fx.cases.length > 0, `${name}.json has no cases`)
  for (const c of fx.cases) {
    if (only && !only(c)) continue
    close(runCase(c), c.expect, `${c.fn}: ${c.name}`)
  }
  setSource()
}

test('text.json', () => checkFile('text'))
test('builders.json', () => checkFile('builders'))
test('labels.json', () => checkFile('labels'))
test('arrows.json', () => checkFile('arrows'))

test('every function the corpus names is covered, and the corpus covers every public function', () => {
  const seen = new Set<string>()
  for (const name of ['text', 'fontmetrics', 'builders', 'labels', 'arrows']) {
    for (const c of elementsFixture(name).cases) seen.add(c.fn)
  }
  const public_ = [
    'lineHeight', 'textWidth', 'measureText', 'wrapText', 'textRoom', 'containerHeightFor', 'baseElement',
    'textElement', 'shapeElement', 'frameElement', 'linearElement', 'touch', 'boundaryPoint', 'routeBetween',
    'routeOf', 'setRoute', 'unlistBound', 'labelOf', 'addLabel', 'fitLabel', 'bindEnd', 'refitArrow', 'detach',
  ]
  for (const fn of public_) assert.ok(seen.has(fn), `no case exercises ${fn}`)
})

// --- the source ---------------------------------------------------------------------

test('setSource replaces ids, nonces and the clock, and undefined restores the defaults', () => {
  let n = 0
  setSource({ id: () => `x${++n}`, nonce: () => 7, now: () => 42 })
  assert.equal(newId(), 'x1')
  assert.equal(nonce(), 7)
  assert.equal(nowMs(), 42)
  const e = baseElement('rectangle', 0, 0, 1, 1, { roughness: 0 })
  assert.deepEqual([e.id, e.seed, e.versionNonce, e.updated], ['x2', 7, 7, 42])
  const t = touch({ version: 3 })
  assert.deepEqual([t.version, t.versionNonce, t.updated], [4, 7, 42])

  // One source left out gets its default back; setSource() restores all three.
  setSource({ id: () => 'only-ids' })
  assert.equal(newId(), 'only-ids')
  assert.notEqual(nowMs(), 42)
  assert.ok(nonce() >= 1)
  setSource()
  assert.notEqual(newId(), 'only-ids')
})

test('the default source makes 21-character ids of the nanoid alphabet, and nonces in 1..2^31-1', () => {
  setSource()
  const seen = new Set<string>()
  for (let i = 0; i < 200; i++) {
    const id = newId()
    assert.match(id, /^[A-Za-z0-9_-]{21}$/)
    seen.add(id)
    const n = nonce()
    assert.ok(Number.isInteger(n) && n >= 1 && n <= 2 ** 31 - 1, String(n))
  }
  assert.equal(seen.size, 200)
  assert.ok(Math.abs(nowMs() - Date.now()) < 5000)
})

test('a counting source makes a scene render identically every time', () => {
  const build = (): El[] => {
    countingSource()
    const box = shapeElement('rectangle', 0, 0, 160, 60, { roughness: 1 })
    const label = addLabel(box, 'Ingest', { font: 5, roughness: 1 })
    return [box, label]
  }
  assert.deepEqual(build(), build())
  setSource()
})

// --- structure ------------------------------------------------------------------------

const COMMON = [
  'id', 'type', 'x', 'y', 'width', 'height', 'angle', 'strokeColor', 'backgroundColor', 'fillStyle', 'strokeWidth',
  'strokeStyle', 'roughness', 'opacity', 'groupIds', 'frameId', 'index', 'roundness', 'seed', 'version',
  'versionNonce', 'isDeleted', 'boundElements', 'updated', 'link', 'locked',
]
const TEXT = ['text', 'originalText', 'fontSize', 'fontFamily', 'textAlign', 'verticalAlign', 'containerId', 'lineHeight', 'autoResize']
const LINEAR_FIELDS = ['points', 'lastCommittedPoint', 'startBinding', 'endBinding', 'startArrowhead', 'endArrowhead']
const REQUIRED: Record<string, string[]> = {
  rectangle: COMMON,
  ellipse: COMMON,
  diamond: COMMON,
  frame: [...COMMON, 'name'],
  text: [...COMMON, ...TEXT],
  line: [...COMMON, ...LINEAR_FIELDS],
  arrow: [...COMMON, ...LINEAR_FIELDS, 'elbowed'],
}

test('every kind carries every field Excalidraw requires', () => {
  setSource()
  const built: Record<string, El> = {
    rectangle: shapeElement('rectangle', 0, 0, 100, 50, { roughness: 1 }),
    ellipse: shapeElement('ellipse', 0, 0, 100, 50, { roughness: 1 }),
    diamond: shapeElement('diamond', 0, 0, 100, 50, { roughness: 1 }),
    frame: frameElement(0, 0, 300, 200, 'Frame'),
    text: textElement('Hello', 5, 6, { font: FONT_HELVETICA, roughness: 0 }),
    line: linearElement('line', [[0, 0], [50, 20]], { roughness: 0 }),
    arrow: linearElement('arrow', [[0, 0], [50, 20]], { roughness: 0, endHead: 'arrow' }),
  }
  for (const [kind, el] of Object.entries(built)) {
    const missing = REQUIRED[kind].filter((k) => !(k in el))
    assert.deepEqual(missing, [], kind)
    assert.equal(el.type, kind)
    // and nothing is undefined: JSON would drop it, and Excalidraw expects null
    for (const [k, v] of Object.entries(el)) assert.notEqual(v, undefined, `${kind}.${k}`)
  }
  const box = shapeElement('rectangle', 0, 0, 200, 80, { roughness: 0 })
  const label = addLabel(box, 'Ingest', { font: FONT_HELVETICA, roughness: 0 })
  assert.deepEqual(REQUIRED.text.filter((k) => !(k in label)), [])
})
