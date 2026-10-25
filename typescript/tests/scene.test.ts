/**
 * The scene module, against the corpus.
 *
 * Run:  npm test          (Node strips the types itself; no build step)
 *
 * Each `corpus/scene/*.json` file holds a `{doc, cases}` object, every case
 * naming the function it exercises (`fn`). The expectations were produced by
 * running the Python twin (`python/tools/gen_corpus_scene.py`). A case names its
 * input either inline or as a corpus scene / reply by name. Floats are compared
 * with a 1e-6 tolerance; everything else, including the order of an object's
 * keys (the order a prompt shows its fields in), exactly.
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

import {
  KEEP,
  MAX_COORD,
  MAX_STROKE_POINTS,
  OPAQUE_TYPES,
  bbox,
  compact,
  extractPatch,
  instanceOf,
  rdp,
  saneGeometry,
  strokeSummary,
  stencilSummary,
  validPatch,
} from '../src/scene.ts'
import * as corpus from './corpus.ts'

const EPS = 1e-6
const SCENE = join(corpus.SCENES, '..', 'scene')
const REPLIES = join(corpus.SCENES, '..', 'replies')

type Case = Record<string, any>

/** Deep equality: numbers within EPS, key order and every other value exact. */
function same(actual: unknown, expected: unknown, what: string): void {
  if (typeof expected === 'number') {
    assert.ok(
      typeof actual === 'number' && Math.abs(actual - expected) < EPS,
      `${what}: ${actual} != ${expected}`,
    )
  } else if (Array.isArray(expected)) {
    assert.ok(Array.isArray(actual), `${what}: expected an array, got ${JSON.stringify(actual)}`)
    assert.equal(actual.length, expected.length, `${what}: length`)
    expected.forEach((e, i) => same(actual[i], e, `${what}[${i}]`))
  } else if (expected !== null && typeof expected === 'object') {
    assert.ok(
      actual !== null && typeof actual === 'object' && !Array.isArray(actual),
      `${what}: expected an object, got ${JSON.stringify(actual)}`,
    )
    assert.deepEqual(Object.keys(actual as object), Object.keys(expected), `${what}: keys`)
    for (const k of Object.keys(expected)) {
      same((actual as Record<string, unknown>)[k], (expected as Record<string, unknown>)[k], `${what}.${k}`)
    }
  } else {
    assert.equal(actual, expected, what)
  }
}

function fixture(name: string): { doc: string; cases: Case[] } {
  const fx = JSON.parse(readFileSync(join(SCENE, `${name}.json`), 'utf8'))
  assert.ok(fx.doc.length > 0, `${name}.json needs a doc string`)
  assert.ok(fx.cases.length > 0, `${name}.json has no cases`)
  return fx
}

/** The raw elements a case names: `elements` inline, or a corpus `scene`. */
function elementsOf(c: Case): any {
  return 'scene' in c ? corpus.elements(c.scene) : c.elements
}

function messageOf(c: Case): string {
  return 'reply' in c ? readFileSync(join(REPLIES, `${c.reply}.txt`), 'utf8') : c.message
}

/** A case's `options`, as the module spells them (lists become sets). */
function optionsOf(c: Case): Record<string, any> {
  const out: Record<string, any> = { ...(c.options ?? {}) }
  if (out.opaque) out.opaque = new Set(out.opaque)
  return out
}

function covers(fx: { cases: Case[] }, fns: string[]): void {
  const seen = new Set(fx.cases.map((c) => c.fn))
  for (const fn of fns) assert.ok(seen.has(fn), `no case exercises ${fn}`)
}

test('constants', () => {
  assert.equal(MAX_STROKE_POINTS, 32)
  assert.equal(MAX_COORD, 1_000_000)
  assert.ok(KEEP.includes('id') && KEEP.includes('arrowhead') && KEEP.length === 16)
  assert.deepEqual([...OPAQUE_TYPES].sort(), ['freedraw', 'image', 'stencil'])
})

test('compact.json: compact', () => {
  const fx = fixture('compact')
  for (const c of fx.cases) {
    assert.equal(c.fn, 'compact')
    same(compact(elementsOf(c), optionsOf(c)), c.expect, `${c.fn}: ${c.name}`)
  }
})

test('strokes.json: rdp, strokeSummary', () => {
  const fx = fixture('strokes')
  for (const c of fx.cases) {
    const what = `${c.fn}: ${c.name}`
    const element = 'scene' in c ? corpus.elements(c.scene)[c.index] : c.element
    switch (c.fn) {
      case 'rdp':
        same(rdp('scene' in c ? (element.points as number[][]) : c.points, c.eps), c.expect, what)
        break
      case 'strokeSummary':
        if (c.expect?.throws === true) assert.throws(() => strokeSummary(element, optionsOf(c)), what)
        else same(strokeSummary(element, optionsOf(c)), c.expect, what)
        break
      default:
        assert.fail(`unknown fn ${c.fn}`)
    }
  }
  covers(fx, ['rdp', 'strokeSummary'])
})

test('stencils.json: instanceOf, stencilSummary, bbox', () => {
  const fx = fixture('stencils')
  for (const c of fx.cases) {
    const what = `${c.fn}: ${c.name}`
    switch (c.fn) {
      case 'instanceOf':
        same(instanceOf(c.element), c.expect, what)
        break
      case 'stencilSummary': {
        const members = 'scene' in c
          ? corpus.elements(c.scene).filter((e) => instanceOf(e) === c.instance)
          : c.members
        same(stencilSummary(c.instance, members), c.expect, what)
        break
      }
      case 'bbox':
        same(bbox(elementsOf(c)), c.expect, what)
        break
      default:
        assert.fail(`unknown fn ${c.fn}`)
    }
  }
  covers(fx, ['instanceOf', 'stencilSummary', 'bbox'])
})

test('patch.json: saneGeometry, validPatch, extractPatch', () => {
  const fx = fixture('patch')
  for (const c of fx.cases) {
    const what = `${c.fn}: ${c.name}`
    switch (c.fn) {
      case 'saneGeometry':
        same(saneGeometry(c.element, optionsOf(c)), c.expect, what)
        break
      case 'validPatch':
        same(validPatch(c.obj, optionsOf(c)), c.expect, what)
        break
      case 'extractPatch': {
        const [prose, patch] = extractPatch(messageOf(c), optionsOf(c))
        same({ prose, patch }, c.expect, what)
        break
      }
      default:
        assert.fail(`unknown fn ${c.fn}`)
    }
  }
  covers(fx, ['saneGeometry', 'validPatch', 'extractPatch'])
})

test('every corpus reply and scene is exercised', () => {
  const replies = fixture('patch').cases.filter((c) => c.fn === 'extractPatch' && 'reply' in c).map((c) => c.reply)
  const scenes = fixture('compact').cases.filter((c) => 'scene' in c).map((c) => c.scene)
  const stems = (dir: string, ext: string) =>
    readdirSync(dir).filter((f) => f.endsWith(ext)).map((f) => f.slice(0, -ext.length))
  for (const name of stems(corpus.SCENES, '.json')) assert.ok(scenes.includes(name), `scene ${name} has no compact case`)
  for (const name of stems(REPLIES, '.txt')) assert.ok(replies.includes(name), `reply ${name} has no case`)
})
