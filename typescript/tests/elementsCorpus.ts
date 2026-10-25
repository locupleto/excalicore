/**
 * Shared helpers for the tests that read `corpus/elements/`.
 *
 * Not a test file itself, so that the files importing it do not run each
 * other's tests.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { setSource, type El } from '../src/elements.ts'

const EPS = 1e-6
export const CLOCK = 1_700_000_000_000
const ELEMENTS = new URL('../../corpus/elements/', import.meta.url).pathname

export interface Case extends El {
  fn: string
  name: string
  expect: unknown
}

export function elementsFixture(name: string): { doc: string; cases: Case[] } {
  return JSON.parse(readFileSync(join(ELEMENTS, `${name}.json`), 'utf8'))
}

/** The same counting source the generator ran under. */
export function countingSource(): void {
  let ids = 0
  let nonces = 0
  setSource({
    id: () => `id-${String(++ids).padStart(4, '0')}`,
    nonce: () => ++nonces,
    now: () => CLOCK,
  })
}

/** Deep equality, numbers within EPS. */
export function close(actual: unknown, expected: unknown, where: string): void {
  if (typeof expected === 'number') {
    assert.equal(typeof actual, 'number', `${where}: expected a number, got ${JSON.stringify(actual)}`)
    assert.ok(Math.abs((actual as number) - expected) < EPS, `${where}: ${actual} vs ${expected}`)
  } else if (Array.isArray(expected)) {
    assert.ok(Array.isArray(actual), `${where}: expected an array, got ${JSON.stringify(actual)}`)
    assert.equal((actual as unknown[]).length, expected.length, `${where}: length`)
    expected.forEach((x, i) => close((actual as unknown[])[i], x, `${where}[${i}]`))
  } else if (expected !== null && typeof expected === 'object') {
    assert.ok(actual !== null && typeof actual === 'object', `${where}: expected an object, got ${JSON.stringify(actual)}`)
    const a = actual as Record<string, unknown>
    assert.deepEqual(Object.keys(a).sort(), Object.keys(expected).sort(), `${where}: keys`)
    for (const [k, x] of Object.entries(expected)) close(a[k], x, `${where}.${k}`)
  } else {
    assert.equal(actual, expected, where)
  }
}

