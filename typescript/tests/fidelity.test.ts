/**
 * The fidelity module, against the corpus.
 *
 * Run:  npm test          (Node strips the types itself; no build step)
 *
 * Each `corpus/fidelity/*.json` file holds a `{doc, cases}` object, every case
 * naming the function it exercises (`fn`). The expectations were produced by
 * running the Python twin (`python/tools/gen_corpus_fidelity.py`). Rows are
 * written there with the column names a SQL cursor returns (`element_id`), so
 * the explode cases map this module's `elementId` back before comparing. The
 * remainder's JSON text (`json`) is compared as a string, exactly.
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import {
  BOOKKEEPING,
  COLUMNS,
  explode,
  fileIds,
  reassemble,
  unreferencedFiles,
  type ElementRow,
} from '../src/fidelity.ts'
import * as corpus from './corpus.ts'

type Case = Record<string, any>

const FIDELITY = join(corpus.SCENES, '..', 'fidelity')

function fixture(name: string): { doc: string; cases: Case[] } {
  const fx = JSON.parse(readFileSync(join(FIDELITY, `${name}.json`), 'utf8'))
  assert.ok(fx.doc.length > 0, `${name}.json needs a doc string`)
  assert.ok(fx.cases.length > 0, `${name}.json has no cases`)
  return fx
}

function sceneFile(name: string): { elements: unknown[]; files?: unknown } {
  return JSON.parse(readFileSync(join(corpus.SCENES, `${name}.json`), 'utf8'))
}

/** A row under the column names the fixtures use. */
function snake(row: ElementRow): Record<string, unknown> {
  const { elementId, ...rest } = row
  return { element_id: elementId, ...rest }
}

function covers(fx: { cases: Case[] }, fns: string[]): void {
  const seen = new Set(fx.cases.map((c) => c.fn))
  for (const fn of fns) assert.ok(seen.has(fn), `no case exercises ${fn}`)
}

test('constants', () => {
  assert.deepEqual([...BOOKKEEPING].sort(), ['boundElements', 'index', 'seed', 'updated', 'version', 'versionNonce'])
  assert.deepEqual(COLUMNS, ['id', 'type', 'x', 'y', 'width', 'height', 'angle'])
})

test('explode.json: explode', () => {
  const fx = fixture('explode')
  for (const c of fx.cases) {
    const what = `${c.fn}: ${c.name}`
    assert.equal(c.fn, 'explode')
    const elements = 'scene' in c ? sceneFile(c.scene).elements : c.elements
    const rows = explode(elements, c.options).map(snake)
    assert.equal(rows.length, c.expect.length, `${what}: row count`)
    rows.forEach((row, i) => {
      // key order is part of the fixture: it is the column order of the row
      assert.deepEqual(Object.keys(row), Object.keys(c.expect[i]), `${what}[${i}]: columns`)
      assert.deepEqual(row, c.expect[i], `${what}[${i}]`)
    })
  }
})

test('reassemble.json: reassemble, roundTrip', () => {
  const fx = fixture('reassemble')
  for (const c of fx.cases) {
    const what = `${c.fn}: ${c.name}`
    switch (c.fn) {
      case 'reassemble':
        assert.deepEqual(reassemble(c.rows, c.options), c.expect, what)
        break
      case 'roundTrip': {
        const elements = 'scene' in c ? sceneFile(c.scene).elements : c.elements
        const rows = explode(elements)
        const back = reassemble(c.reversed ? [...rows].reverse() : rows)
        assert.equal(c.expect, true, `${what}: the fixture says Python round-trips`)
        assert.deepEqual(back, elements, what)
        break
      }
      default:
        assert.fail(`unknown fn ${c.fn}`)
    }
  }
  covers(fx, ['reassemble', 'roundTrip'])
})

test('assets.json: fileIds, unreferencedFiles', () => {
  const fx = fixture('assets')
  for (const c of fx.cases) {
    const what = `${c.fn}: ${c.name}`
    const sc = 'scene' in c ? sceneFile(c.scene) : null
    const elements = sc ? sc.elements : c.elements
    switch (c.fn) {
      case 'fileIds':
        assert.deepEqual([...fileIds(elements)].sort(), c.expect, what)
        break
      case 'unreferencedFiles':
        assert.deepEqual([...unreferencedFiles(elements, sc ? sc.files : c.files)].sort(), c.expect, what)
        break
      default:
        assert.fail(`unknown fn ${c.fn}`)
    }
  }
  covers(fx, ['fileIds', 'unreferencedFiles'])
})

test('explode and reassemble accept rows as the SQL driver spells them', () => {
  const rows = explode([{ id: 'a', type: 'rectangle', x: 1 }, { type: 'line' }])
  const asDriver = rows.map(snake)
  assert.deepEqual(reassemble(asDriver), reassemble(rows))
  assert.deepEqual(reassemble(rows), [{ id: 'a', type: 'rectangle', x: 1 }, { type: 'line' }])
})
