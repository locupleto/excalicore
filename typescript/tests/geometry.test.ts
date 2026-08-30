/**
 * The geometry module, against the corpus.
 *
 * Run:  npm test          (Node strips the types itself; no build step)
 *
 * Each `corpus/geometry/*.json` file holds a `{doc, cases}` object; every
 * case names the function it exercises (`fn`) so one loop per file can
 * dispatch to the right call. Floats are compared with a 1e-6 tolerance —
 * the fixtures themselves are rounded to 6 decimals, per the corpus's own
 * convention.
 */
import test from 'node:test'
import assert from 'node:assert/strict'

import {
  along,
  anchorUV,
  anchorXY,
  area,
  arrowElement,
  arrowFields,
  arrowKind,
  absoluteRoute,
  boxOf,
  centre,
  centreSegment,
  contains,
  ellipsise,
  exitT,
  facingSides,
  lineCount,
  normalizeBoundArrows,
  overlap,
  pointOnSide,
  relativeBends,
  terse,
  topAlignCrowdedLabels,
  union,
  wrap,
  type Box,
  type Point,
} from '../src/geometry.ts'
import * as corpus from './corpus.ts'

const EPS = 1e-6

/** Deep, tolerant equality: numbers within EPS, everything else exact.
 *  Used throughout because the corpus mixes floats (a trimmed segment) with
 *  exact values (an id, a side word, a boolean) in the same object. */
function close(actual: unknown, expected: unknown, what: string): void {
  if (expected === null) {
    assert.equal(actual, null, what)
    return
  }
  if (typeof expected === 'number') {
    assert.ok(
      typeof actual === 'number' && Math.abs(actual - expected) < EPS,
      `${what}: ${actual} != ${expected}`,
    )
    return
  }
  if (Array.isArray(expected)) {
    assert.ok(Array.isArray(actual), `${what}: expected an array, got ${JSON.stringify(actual)}`)
    assert.equal((actual as unknown[]).length, expected.length, `${what}: length`)
    expected.forEach((e, i) => close((actual as unknown[])[i], e, `${what}[${i}]`))
    return
  }
  if (typeof expected === 'object') {
    assert.ok(
      actual && typeof actual === 'object',
      `${what}: expected an object, got ${JSON.stringify(actual)}`,
    )
    for (const k of Object.keys(expected as Record<string, unknown>)) {
      close(
        (actual as Record<string, unknown>)[k],
        (expected as Record<string, unknown>)[k],
        `${what}.${k}`,
      )
    }
    return
  }
  assert.equal(actual, expected, what)
}

function cases(name: string): { doc: string; cases: Record<string, unknown>[] } {
  const fx = corpus.geometryFixture(name)
  assert.ok(fx.doc.length > 0, `${name}.json needs a doc string`)
  assert.ok(fx.cases.length > 0, `${name}.json has no cases`)
  return fx
}

// --- boxes -----------------------------------------------------------------

test('boxes.json: boxOf, union, contains, overlap, centre, area', () => {
  const { cases: cs } = cases('boxes')
  let seen = new Set<string>()
  for (const c of cs) {
    seen.add(c.fn as string)
    const what = `${c.fn}: ${c.name}`
    switch (c.fn) {
      case 'boxOf':
        close(boxOf(c.element as Record<string, unknown>), c.expect, what)
        break
      case 'union':
        close(union(c.boxes as Box[]), c.expect, what)
        break
      case 'contains':
        assert.equal(contains(c.box as Box, c.point as Point), c.expect, what)
        break
      case 'overlap':
        assert.equal(overlap(c.a as Box, c.b as Box), c.expect, what)
        break
      case 'centre':
        close(centre(c.box as Box), c.expect, what)
        break
      case 'area':
        close(area(c.box as Box), c.expect, what)
        break
      default:
        assert.fail(`unknown fn ${c.fn} in boxes.json`)
    }
  }
  assert.ok(seen.size === 6, `boxes.json should exercise all 6 functions, saw ${[...seen]}`)
})

// --- faces and anchors -------------------------------------------------------

test('faces.json: facingSides, pointOnSide, along, anchorUV, anchorXY, exitT, centreSegment', () => {
  const { cases: cs } = cases('faces')
  const seen = new Set<string>()
  for (const c of cs) {
    seen.add(c.fn as string)
    const what = `${c.fn}: ${c.name}`
    switch (c.fn) {
      case 'facingSides':
        assert.deepEqual(facingSides(c.a as Box, c.b as Box), c.expect, what)
        break
      case 'pointOnSide':
        close(pointOnSide(c.box as Box, c.side as never, c.t as number), c.expect, what)
        break
      case 'along':
        close(along(c.other as Box, c.side as never), c.expect, what)
        break
      case 'anchorUV':
        close(anchorUV(c.point as Point, c.box as Box), c.expect, what)
        break
      case 'anchorXY':
        close(anchorXY(c.uv as { u: number; v: number }, c.box as Box), c.expect, what)
        break
      case 'exitT':
        close(exitT(c.box as Box, c.dx as number, c.dy as number), c.expect, what)
        break
      case 'centreSegment':
        close(centreSegment(c.a as Box, c.b as Box, c.gap as number), c.expect, what)
        break
      default:
        assert.fail(`unknown fn ${c.fn} in faces.json`)
    }
  }
  assert.ok(seen.size === 7, `faces.json should exercise all 7 functions, saw ${[...seen]}`)
})

test('anchorUV/anchorXY round-trip on every anchor case in faces.json', () => {
  const { cases: cs } = cases('faces')
  for (const c of cs) {
    if (c.fn !== 'anchorUV') continue
    const uv = anchorUV(c.point as Point, c.box as Box)
    const back = anchorXY(uv, c.box as Box)
    close(back, c.point, `round trip: ${c.name}`)
  }
})

// --- shape memory ------------------------------------------------------------

test('bends.json: relativeBends, absoluteRoute', () => {
  const { cases: cs } = cases('bends')
  const seen = new Set<string>()
  for (const c of cs) {
    seen.add(c.fn as string)
    const what = `${c.fn}: ${c.name}`
    if (c.fn === 'relativeBends') {
      close(relativeBends(c.points as Point[]), c.expect, what)
    } else if (c.fn === 'absoluteRoute') {
      close(
        absoluteRoute(
          c.bends as { t: number; d: number }[],
          c.a as Point,
          c.b as Point,
        ),
        c.expect,
        what,
      )
    } else {
      assert.fail(`unknown fn ${c.fn} in bends.json`)
    }
  }
  assert.ok(seen.size === 2, `bends.json should exercise both functions, saw ${[...seen]}`)
})

test('a right angle survives relativeBends -> absoluteRoute at a NEW pair of anchors, translated', () => {
  // The property the corpus fixes numerically, stated directly: bending an
  // arrow, moving both its boxes by the same vector, and refitting produces
  // the same shape translated — not sheared.
  const a: Point = [100, 100]
  const b: Point = [400, 100]
  const elbow: Point[] = [a, [100, 300], b]
  const bends = relativeBends(elbow)
  const shift = [77, -33] as const
  const a2: Point = [a[0] + shift[0], a[1] + shift[1]]
  const b2: Point = [b[0] + shift[0], b[1] + shift[1]]
  const route = absoluteRoute(bends, a2, b2)
  assert.equal(route.length, 3)
  close(route[0], a2, 'start')
  close(route[2], b2, 'end')
  close(route[1], [elbow[1][0] + shift[0], elbow[1][1] + shift[1]], 'knee')
})

test('arrows.json: arrowKind, arrowFields, arrowElement', () => {
  const { cases: cs } = cases('arrows')
  const seen = new Set<string>()
  for (const c of cs) {
    seen.add(c.fn as string)
    const what = `${c.fn}: ${c.name}`
    if (c.fn === 'arrowKind') {
      assert.equal(arrowKind(c.element as Record<string, unknown>), c.expect, what)
    } else if (c.fn === 'arrowFields') {
      // Exact, not tolerant: arrowFields is a small discrete object, and the
      // whole point is whether the `elbowed` key is even PRESENT.
      assert.deepEqual(arrowFields(c.kind as never), c.expect, what)
    } else if (c.fn === 'arrowElement') {
      close(arrowElement(c.points as Point[]), c.expect, what)
    } else {
      assert.fail(`unknown fn ${c.fn} in arrows.json`)
    }
  }
  assert.ok(seen.size === 3, `arrows.json should exercise all 3 functions, saw ${[...seen]}`)
})

// --- labels ------------------------------------------------------------------

test('wrap.json: wrap, ellipsise, terse, lineCount', () => {
  const { cases: cs } = cases('wrap')
  const seen = new Set<string>()
  for (const c of cs) {
    seen.add(c.fn as string)
    const what = `${c.fn}: ${c.name}`
    if (c.fn === 'wrap') {
      assert.deepEqual(wrap(c.text as string, c.cols as number, c.maxLines as number), c.expect, what)
    } else if (c.fn === 'ellipsise') {
      assert.equal(ellipsise(c.line as string, c.cols as number), c.expect, what)
    } else if (c.fn === 'terse') {
      assert.equal(terse(c.text as string, c.maxWords as number), c.expect, what)
    } else if (c.fn === 'lineCount') {
      assert.equal(lineCount(c.text as string, c.cols as number), c.expect, what)
    } else {
      assert.fail(`unknown fn ${c.fn} in wrap.json`)
    }
  }
  assert.ok(seen.size === 4, `wrap.json should exercise all 4 functions, saw ${[...seen]}`)
})

test('lineCount is exactly wrap(text, cols, Infinity).length, by construction', () => {
  for (const [text, cols] of [
    ['a modest label', 22],
    ['', 10],
    ['supercalifragilisticexpialidocious', 12],
  ] as const) {
    assert.equal(lineCount(text, cols), wrap(text, cols, Number.MAX_SAFE_INTEGER).length, text)
  }
})

// --- the skeleton pipeline ---------------------------------------------------

test('routes.json: normalizeBoundArrows', () => {
  const { cases: cs } = cases('routes')
  for (const c of cs) {
    const got = normalizeBoundArrows(
      c.skeletons as unknown[],
      c.board as unknown[],
      c.options as never,
    )
    close(got, c.expect, `normalizeBoundArrows: ${c.name}`)
  }
})

test('normalizeBoundArrows does not mutate its skeletons or board arguments', () => {
  const board = [{ id: 'a', type: 'rectangle', x: 0, y: 0, width: 100, height: 100 }]
  const skeletons = [
    { id: 'b', type: 'rectangle', x: 300, y: 0, width: 100, height: 100 },
    { id: 'ar1', type: 'arrow', start: { id: 'a' }, end: { id: 'b' } },
  ]
  const boardCopy = structuredClone(board)
  const skeletonsCopy = structuredClone(skeletons)
  normalizeBoundArrows(skeletons, board)
  assert.deepEqual(board, boardCopy, 'board was mutated')
  assert.deepEqual(skeletons, skeletonsCopy, 'skeletons was mutated')
})

test('crowding.json: topAlignCrowdedLabels', () => {
  const { cases: cs } = cases('crowding')
  for (const c of cs) {
    const got = topAlignCrowdedLabels(c.skeletons as unknown[])
    close(got, c.expect, `topAlignCrowdedLabels: ${c.name}`)
  }
})

test('topAlignCrowdedLabels does not mutate its argument', () => {
  const skeletons = [
    {
      id: 'box1', type: 'rectangle', x: 0, y: 0, width: 200, height: 200,
      label: { text: 'Server' },
    },
    { id: 'txt1', type: 'text', x: 80, y: 80, width: 40, height: 20, text: 'note' },
  ]
  const before = structuredClone(skeletons)
  topAlignCrowdedLabels(skeletons)
  assert.deepEqual(skeletons, before, 'skeletons was mutated')
})
