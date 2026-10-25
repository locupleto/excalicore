/**
 * The glyph tables, against the corpus.
 *
 * `corpus/elements/fontmetrics.json` was generated from the Python tables:
 * per font their size, average, sum and a position-weighted checksum, and
 * single glyphs at the edges of the tables and of every East Asian wide range.
 */
import test from 'node:test'
import assert from 'node:assert/strict'

import { ADVANCE, CODEPOINTS, METRICS, isWide } from '../src/fontmetrics.ts'
import { setSource, textWidth } from '../src/elements.ts'
import { close, elementsFixture } from './elementsCorpus.ts'

test('the tables hold what the Python tables hold', () => {
  const fx = elementsFixture('fontmetrics')
  let tables = 0
  for (const c of fx.cases) {
    if (c.fn !== 'tables') continue
    const [average, widths] = METRICS[c.font]
    assert.equal(widths.length, CODEPOINTS.length)
    close(
      {
        codepoints: CODEPOINTS.length,
        average,
        glyphs: ADVANCE[c.font].size,
        sum: widths.reduce((a, b) => a + b, 0),
        weighted: widths.reduce((a, w, i) => a + i * w, 0) % 1_000_003,
      },
      c.expect,
      `font ${c.font}`,
    )
    tables++
  }
  assert.equal(tables, 5)
})

test('single glyphs at the edges of the tables and of every wide range', () => {
  const fx = elementsFixture('fontmetrics')
  setSource()
  for (const c of fx.cases) {
    if (c.fn !== 'textWidth') continue
    close(textWidth(c.line, c.size, c.font), c.expect, c.name)
    // a glyph the tables lack is the font's average, or a full em when wide
    if (!ADVANCE[c.font].has(c.line)) assert.equal(isWide(c.line), c.expect === c.size, c.name)
  }
})

test('isWide reads the first codepoint of a string and a missing one as narrow', () => {
  assert.equal(isWide('中'), true)
  assert.equal(isWide('a'), false)
  assert.equal(isWide(''), false)
  assert.equal(isWide('\u{1f600}'), true)
})
