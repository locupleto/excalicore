/**
 * The vocabulary contract, against the corpus.
 *
 * Run:  npm test          (Node strips the types itself; no build step)
 */
import test from 'node:test'
import assert from 'node:assert/strict'

import {
  checkGraph,
  kindOf,
  kindsOf,
  stencilFor,
  validateVocabulary,
  VocabularyError,
  type Graph,
  type Vocabulary,
} from '../src/vocabulary.ts'
import * as corpus from './corpus.ts'

/** Sentences are compared as sets: order carries no meaning. */
function assertSameSet(actual: string[], expected: string[], what: string) {
  assert.deepEqual([...actual].sort(), [...expected].sort(), what)
}

function vocabulary(name: string): Vocabulary {
  return corpus.vocabularyFixture(name) as unknown as Vocabulary
}

// --- validating a vocabulary ---------------------------------------------------

test('every corpus vocabulary validates clean', () => {
  const names = corpus.vocabularyNames()
  assert.ok(names.length >= 2)
  for (const name of names) {
    assertSameSet(validateVocabulary(vocabulary(name)), [], name)
  }
})

test('every rejected vocabulary yields exactly the expected sentences', () => {
  const { cases } = corpus.vocabularyFixture('rejected') as {
    cases: { reason: string; vocabulary: Vocabulary; expect: string[] }[]
  }
  assert.ok(cases.length >= 14)
  for (const c of cases) {
    const errors = validateVocabulary(c.vocabulary)
    assertSameSet(errors, c.expect, c.reason)
    for (const e of errors) assert.match(e, /\.$/, `not a sentence: ${e}`)
  }
})

// --- checking a graph ------------------------------------------------------------

test('every graph case yields exactly the expected sentences', () => {
  const { cases } = corpus.vocabularyFixture('graphs') as {
    cases: { name: string; vocabulary: string; graph: Graph; expect: string[] }[]
  }
  assert.ok(cases.length >= 15)
  for (const c of cases) {
    const errors = checkGraph(vocabulary(c.vocabulary), c.graph)
    assertSameSet(errors, c.expect, c.name)
  }
})

test('checkGraph throws VocabularyError when the vocabulary itself is not valid', () => {
  const bad: Vocabulary = { name: 'bad', kinds: [{ name: 'a' }] }
  assert.throws(() => checkGraph(bad, { subjects: [], connections: [] }), (err: unknown) => {
    assert.ok(err instanceof VocabularyError)
    assert.ok(err.errors.some((e) => e.includes('needs a role')))
    return true
  })
})

// --- lookups ------------------------------------------------------------------

test('kindsOf returns kinds in declared order, filtered by role', () => {
  const bastion = vocabulary('bastion')
  const nodes = kindsOf(bastion, 'node')
  assert.deepEqual(nodes.map((k) => k.name), ['actor', 'process', 'datastore', 'external_service'])
  const containers = kindsOf(bastion, 'container')
  assert.deepEqual(containers.map((k) => k.name), ['zone'])
  const connectors = kindsOf(bastion, 'connector')
  assert.deepEqual(connectors.map((k) => k.name), ['flow'])
  assert.equal(kindsOf(bastion).length, 6)
})

test('kindOf finds a kind by name', () => {
  const bastion = vocabulary('bastion')
  assert.equal(kindOf(bastion, 'datastore')?.name, 'datastore')
  assert.equal(kindOf(bastion, 'ghost'), undefined)
})

test('stencilFor resolves a kind to its default stencil', () => {
  const bastion = vocabulary('bastion')
  assert.equal(stencilFor(bastion, 'datastore'), 'bastion-datastore')
  assert.equal(stencilFor(bastion, 'zone'), undefined)
})
