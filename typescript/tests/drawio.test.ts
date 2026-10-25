/**
 * The draw.io builder, against the corpus.
 *
 * Run:  npm test          (Node strips the types itself; no build step)
 *
 * `corpus/drawio/cases.json` holds a `{doc, cases}` object; every expected
 * string in it is what the Python half wrote for the same diagram, so a case
 * passes only when the two halves write the same bytes. Strings are compared
 * exactly — no tolerance, no whitespace folding.
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { Diagram, ValueError, type BoxTuple, type Point, type Shape, type Style } from '../src/drawio.ts'

const CASES = new URL('../../corpus/drawio/cases.json', import.meta.url).pathname

interface Failure { type: string; message: string }
type Result = { output: string } | { error: Failure }

type Cell =
  | { op: 'container'; id: string; label: string; box: BoxTuple; parent?: string; style?: Style }
  | { op: 'vertex'; id: string; lines: string[]; box: BoxTuple; shape?: Shape; parent?: string; style?: Style }
  | {
    op: 'edge'; id: string; source: string; target: string; points: Point[]
    lines?: string[]; labelAt?: Point; style?: Style
  }

interface Case {
  name: string
  diagram: { name: string; fontFamily?: string; cells: Cell[] }
  svgOptions?: { margin?: number; background?: string }
  expect:
    | { buildError: Failure }
    | { drawio: Result; svg: Result; bounds: [number, number, number, number] }
}

const fixture = JSON.parse(readFileSync(CASES, 'utf8')) as { doc: string; cases: Case[] }

function apply(d: Diagram, cell: Cell): void {
  if (cell.op === 'container') {
    d.container(cell.id, cell.label, cell.box, { parent: cell.parent, style: cell.style })
  } else if (cell.op === 'vertex') {
    d.vertex(cell.id, cell.lines, cell.box, { shape: cell.shape, parent: cell.parent, style: cell.style })
  } else {
    d.edge(cell.id, cell.source, cell.target, cell.points, cell.lines ?? [],
      { labelAt: cell.labelAt, style: cell.style })
  }
}

/** The call's outcome in the corpus's own shape: its text, or the error. */
function outcome(fn: () => string): Result {
  try {
    return { output: fn() }
  } catch (e) {
    assert.ok(e instanceof ValueError, `unexpected ${String(e)}`)
    return { error: { type: e.name, message: e.message } }
  }
}

test('the corpus is present and says what its cases are', () => {
  assert.ok(fixture.doc.length > 0)
  assert.ok(fixture.cases.length >= 40)
})

for (const c of fixture.cases) {
  test(`drawio: ${c.name}`, () => {
    const d = new Diagram(c.diagram.name, c.diagram.fontFamily === undefined
      ? {} : { fontFamily: c.diagram.fontFamily })

    if ('buildError' in c.expect) {
      const last = c.diagram.cells.length - 1
      c.diagram.cells.slice(0, last).forEach((cell) => apply(d, cell))
      assert.throws(
        () => apply(d, c.diagram.cells[last]),
        (e: unknown) => e instanceof ValueError
          && e.name === (c.expect as { buildError: Failure }).buildError.type
          && e.message === (c.expect as { buildError: Failure }).buildError.message,
      )
      return
    }

    c.diagram.cells.forEach((cell) => apply(d, cell))
    assert.deepEqual(outcome(() => d.toDrawio()), c.expect.drawio, '.drawio')
    assert.deepEqual(outcome(() => d.toSvg(c.svgOptions)), c.expect.svg, '.drawio.svg')
    assert.deepEqual(d.bounds(), c.expect.bounds, 'bounds')
  })
}

test('toSvg carries the same mxfile in content that toMxfile writes', () => {
  const d = new Diagram('Board & <co>')
  d.container('c', 'C', [0, 0, 100, 100])
  d.vertex('a', ['A'], [10, 10, 40, 20], { parent: 'c' })
  const svg = d.toSvg()
  const content = svg.match(/ content="([^"]*)"/)?.[1] ?? ''
  const decoded = content.replaceAll('&quot;', '"').replaceAll('&gt;', '>')
    .replaceAll('&lt;', '<').replaceAll('&amp;', '&')
  assert.equal(decoded, d.toMxfile())
})

test('a diagram can be drawn twice and gives the same text', () => {
  const d = new Diagram('x')
  d.vertex('a', ['A'], [0, 0, 10, 10])
  assert.equal(d.toDrawio(), d.toDrawio())
  assert.equal(d.toSvg(), d.toSvg())
})
