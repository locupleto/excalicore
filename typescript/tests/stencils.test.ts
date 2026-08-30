/**
 * The stencil contract, against the corpus.
 *
 * Run:  npm test          (Node strips the types itself; no build step)
 *
 * The Bastion fixtures are checked against the formulas of its own renderer
 * (the-bastion/frontend/src/render.ts) at the geometry its layout produces,
 * so that step 2 of the stencil sequence — the Bastion drawing through this
 * module — is a substitution, not a redesign.
 */
import test from 'node:test'
import assert from 'node:assert/strict'

import {
  BINDABLE_TYPES,
  bindToBodies,
  defaultRoles,
  StencilError,
  bodyOf,
  frameOf,
  fromLibraryItem,
  instanceOf,
  instances,
  instantiate,
  restyle,
  sweep,
  tagOf,
  validateStencil,
  type Element,
  type LibraryItem,
  type RoleMap,
  type Stencil,
} from '../src/stencils.ts'
import * as corpus from './corpus.ts'

const EPS = 1e-9

function stencil(name: string): Stencil {
  return corpus.stencilFixture(name) as unknown as Stencil
}

function armory(name: string): Stencil {
  const fx = corpus.stencilFixture(name) as { item: LibraryItem; roles: RoleMap }
  return fromLibraryItem(fx.item, fx.roles)
}

function close(actual: unknown, expected: number, what: string) {
  assert.ok(typeof actual === 'number' && Math.abs(actual - expected) < EPS, `${what}: ${actual} != ${expected}`)
}

// --- validation ----------------------------------------------------------------

test('every corpus stencil is valid', () => {
  for (const name of corpus.stencilNames()) {
    if (name === 'rejected') continue
    const fx = corpus.stencilFixture(name)
    const s = 'item' in fx ? armory(name) : stencil(name)
    assert.deepEqual(validateStencil(s.elements), [], name)
  }
})

test('every rejected case is rejected with a sentence', () => {
  const { cases } = corpus.stencilFixture('rejected') as { cases: { reason: string; elements: Element[] }[] }
  assert.ok(cases.length >= 6)
  for (const c of cases) {
    const errors = validateStencil(c.elements)
    assert.ok(errors.length > 0, `"${c.reason}" was accepted`)
    for (const e of errors) assert.match(e, /\.$/, `not a sentence: ${e}`)
  }
})

test('the body must be a type an arrow can bind to', () => {
  assert.deepEqual([...BINDABLE_TYPES], ['rectangle', 'ellipse', 'diamond', 'image'])
  for (const type of ['line', 'arrow', 'freedraw', 'text']) {
    const errors = validateStencil([
      { type, id: 'a', x: 0, y: 0, width: 10, height: 10,
        customData: { stencil: { role: 'body', frame: { dx: 0, dy: 0, sw: 1, sh: 1 } } } },
    ])
    assert.ok(errors.some((e) => e.includes('cannot be bound to')), type)
  }
})

test('a frame with a zero ratio is rejected', () => {
  const errors = validateStencil([
    { type: 'rectangle', id: 'a', x: 0, y: 0, width: 10, height: 10,
      customData: { stencil: { role: 'body', frame: { dx: 0, dy: 0, sw: 0, sh: 1 } } } },
  ])
  assert.equal(errors.length, 1)
  assert.match(errors[0], /positive sw and sh/)
})

test('instantiate refuses an invalid stencil rather than drawing it', () => {
  const bad: Stencil = { name: 'bad', elements: [{ type: 'line', id: 'a', x: 0, y: 0, width: 1, height: 1 }] }
  assert.throws(() => instantiate(bad, { x: 0, y: 0 }), StencilError)
})

// --- the Bastion's glyphs, byte for byte -------------------------------------------

/** actorElements() in render.ts, for a box the layout produced. */
function bastionActor(box: { x: number; y: number; w: number; h: number }) {
  const cx = box.x + box.w / 2
  const head = box.w * 0.28
  const top = box.y + 6
  return {
    head: { x: cx - head / 2, y: top, width: head, height: head,
      frame: { dx: box.x - (cx - head / 2), dy: box.y - top, sw: box.w / head, sh: box.h / head } },
    spine: { x: cx, y: top + head, width: 0, height: box.h * 0.3, points: [[0, 0], [0, box.h * 0.3]] },
    arms: { x: cx - box.w * 0.22, y: top + head + box.h * 0.08, width: box.w * 0.44, height: 0,
      points: [[0, 0], [box.w * 0.44, 0]] },
    legs: { x: cx, y: top + head + box.h * 0.3, width: box.w * 0.34, height: box.h * 0.24,
      points: [[-box.w * 0.17, box.h * 0.24], [0, 0], [box.w * 0.17, box.h * 0.24]] },
    name: { x: cx, y: box.y + box.h - 18 },
  }
}

function byId(parts: Element[]): Record<string, Element> {
  return Object.fromEntries(parts.map((p) => [String(p.id), p]))
}

test('the actor lands where render.ts puts it, at the layout size', () => {
  const box = { x: 126, y: 141, w: 120, h: 128 }  // ITIL Users, as layout.py places it
  const want = bastionActor(box)
  const parts = instantiate(stencil('bastion-actor'), { x: box.x, y: box.y, width: box.w, height: box.h }, {
    instance: 'g-c-itil',
    label: 'ITIL Users',
    id: (src, role) => (role === 'body' ? 'c-itil' : `cp-itil-${src.id}`),
    tags: { bastion: { kind: 'component', key: 'itil' } },
  })
  assert.equal(parts.length, 5)
  const p = byId(parts)
  for (const [id, exp] of Object.entries(want)) {
    const el = p[id === 'head' ? 'c-itil' : `cp-itil-${id}`]
    assert.ok(el, id)
    for (const [k, v] of Object.entries(exp)) {
      if (k === 'frame') {
        const frame = tagOf(el)!.frame!
        for (const f of ['dx', 'dy', 'sw', 'sh'] as const) close(frame[f], (v as Record<string, number>)[f], `${id}.frame.${f}`)
      } else if (k === 'points') {
        const pts = el.points as number[][]
        ;(v as number[][]).forEach((pt, i) => { close(pts[i][0], pt[0], `${id}.points[${i}].x`); close(pts[i][1], pt[1], `${id}.points[${i}].y`) })
      } else close(el[k], v as number, `${id}.${k}`)
    }
  }
  assert.equal(p['cp-itil-name'].text, 'ITIL Users')
  assert.equal(p['cp-itil-name'].fontSize, 16, 'a fixed label keeps its pixels')
  for (const el of parts) {
    assert.deepEqual(el.groupIds, ['g-c-itil'])
    assert.deepEqual((el.customData as { bastion: unknown }).bastion, { kind: 'component', key: 'itil' })
    assert.equal(tagOf(el)!.instance, 'g-c-itil')
    assert.equal(tagOf(el)!.name, 'bastion-actor')
  }
  const back = frameOf(parts)!
  for (const [k, v] of Object.entries({ x: 126, y: 141, width: 120, height: 128 })) close(back[k as keyof typeof back], v, `frame.${k}`)
})

test('the actor keeps its proportions at another size, and the frame still comes back', () => {
  const box = { x: 40, y: 30, w: 150, h: 160 }
  const want = bastionActor(box)
  const parts = instantiate(stencil('bastion-actor'), { x: box.x, y: box.y, width: box.w, height: box.h })
  const head = bodyOf(parts)!
  close(head.x, want.head.x, 'head.x')
  close(head.width, want.head.width, 'head.width')
  close(head.height, want.head.height, 'head.height')
  const name = parts.find((el) => tagOf(el)!.role === 'label')!
  close(name.x, want.name.x, 'name.x')
  close(name.y, want.name.y, 'name.y')
  const back = frameOf(parts)!
  close(back.x, box.x, 'frame.x'); close(back.y, box.y, 'frame.y')
  close(back.width, box.w, 'frame.w'); close(back.height, box.h, 'frame.h')
})

test('a single-part instance is not put in a group of its own', () => {
  const one: Stencil = { name: 'one', elements: [
    { type: 'rectangle', id: 'b', x: 0, y: 0, width: 10, height: 10, label: { text: 'Box', fontSize: 16 },
      customData: { stencil: { role: 'body', frame: { dx: 0, dy: 0, sw: 1, sh: 1 } } } },
  ] }
  const parts = instantiate(one, { x: 1, y: 2 }, { label: 'Named', instance: 'i-1' })
  assert.equal(parts.length, 1)
  assert.equal('groupIds' in parts[0], false)
  assert.equal(tagOf(parts[0])!.instance, 'i-1')
  assert.deepEqual(parts[0].label, { text: 'Named', fontSize: 16 }, 'a label property on the body is a label slot')
  const tinted = restyle([{ ...parts[0], label: { text: 'Named', strokeColor: '#000' } }], { strokeColor: '#f00', backgroundColor: '#0f0' })
  assert.deepEqual(tinted[0].label, { text: 'Named', strokeColor: '#f00' }, 'the label property takes the tint, not the fill')
  assert.deepEqual([...instances(parts).keys()], ['i-1'])
})

test('a label element beside a body that already carries a label property is refused', () => {
  const errors = validateStencil([
    { type: 'rectangle', id: 'b', x: 0, y: 0, width: 10, height: 10, label: { text: 'Box' },
      customData: { stencil: { role: 'body', frame: { dx: 0, dy: 0, sw: 1, sh: 1 } } } },
    { type: 'text', id: 't', x: 0, y: 0, text: 'x', containerId: 'b', customData: { stencil: { role: 'label' } } },
  ])
  assert.equal(errors.length, 1)
  assert.match(errors[0], /one label too many/)
})

test('a plain box is the identity, its label bound, and no ghosts unless asked', () => {
  const parts = instantiate(stencil('bastion-process'), { x: 816, y: 202, width: 200, height: 88 }, {
    label: 'MID Server\nMID', id: (src, role) => (role === 'body' ? 'c-mid' : `cp-mid-${src.id}`),
  })
  assert.deepEqual(parts.map((p) => p.id), ['c-mid', 'cp-mid-label'])
  const body = parts[0]
  assert.deepEqual([body.x, body.y, body.width, body.height], [816, 202, 200, 88])
  assert.deepEqual(tagOf(body)!.frame, { dx: 0, dy: 0, sw: 1, sh: 1 })
  assert.equal(parts[1].containerId, 'c-mid', 'the bound label follows its container by its new id')
  assert.equal(parts[1].text, 'MID Server\nMID')
  assert.deepEqual(frameOf(parts), { x: 816, y: 202, width: 200, height: 88 })
})

test('multiplicity draws the ghost stack behind the body with a fixed pixel offset', () => {
  const parts = instantiate(stencil('bastion-datastore'), { x: 502, y: 382, width: 200, height: 76 }, {
    variants: ['multiplicity'], id: (src) => String(src.id),
  })
  assert.deepEqual(parts.map((p) => p.id), ['stack2', 'stack1', 'box', 'label', 'rule-top', 'rule-bottom'])
  const p = byId(parts)
  assert.deepEqual([p.stack2.x, p.stack2.y, p.stack2.width, p.stack2.height], [502 + 24, 382 - 24, 200, 76])
  assert.deepEqual([p.stack1.x, p.stack1.y], [502 + 12, 382 - 12])
  assert.deepEqual([p['rule-top'].x, p['rule-top'].y, p['rule-top'].width], [502, 382, 200])
  assert.deepEqual([p['rule-bottom'].x, p['rule-bottom'].y], [502, 382 + 76])
  assert.deepEqual(p['rule-bottom'].points, [[0, 0], [200, 0]])
  assert.equal(p.stack1.strokeWidth, 1)
  assert.equal(tagOf(p.stack1)!.variant, 'multiplicity')
})

test('a wider data store stretches its rules and its ghosts, and keeps the offset in pixels', () => {
  const parts = instantiate(stencil('bastion-datastore'), { x: 0, y: 0, width: 400, height: 76 }, {
    variants: ['multiplicity'], id: (src) => String(src.id),
  })
  const p = byId(parts)
  assert.deepEqual(p['rule-top'].points, [[0, 0], [400, 0]])
  assert.equal(p['rule-top'].width, 400)
  assert.deepEqual([p.stack1.x, p.stack1.y, p.stack1.width], [12, -12, 400])
})

test('the external service is dashed and the paint goes on the body only', () => {
  const parts = instantiate(stencil('bastion-external-service'), { x: 0, y: 0 }, {
    style: { strokeColor: '#b3aca0', backgroundColor: '#fff' }, variants: ['multiplicity'],
  })
  const body = bodyOf(parts)!
  assert.equal(body.strokeStyle, 'dashed')
  assert.equal(body.strokeColor, '#b3aca0')
  assert.equal(body.backgroundColor, '#fff')
  for (const el of parts) {
    if (el === body) continue
    assert.equal(el.strokeColor, '#b3aca0', `${el.id} follows the ink`)
    assert.notEqual(el.backgroundColor, '#fff', `${el.id} does not take the fill`)
  }
  assert.deepEqual(frameOf(parts), { x: 0, y: 0, width: 200, height: 88 }, 'natural size when none is given')
})

// --- the Armory's symbols, through fromLibraryItem ----------------------------------

test('a library item with a body named becomes a stencil, frame and anchors derived', () => {
  const s = armory('armory-stick-man')
  assert.equal(s.name, 'Stick man')
  assert.equal(s.elements.length, 6)
  const head = bodyOf(s.elements)!
  assert.equal(head.type, 'ellipse')
  const natural = frameOf(s.elements)!
  // The subject is the whole figure: it starts at the head's left/top and
  // runs to the feet.
  close(natural.x, Math.min(...s.elements.map((e) => e.x as number)), 'subject.x')
  close(natural.y, head.y as number, 'subject.y')
  assert.ok(natural.height > (head.height as number) * 2, 'the figure is taller than its head')
  for (const el of s.elements) {
    const tag = tagOf(el)!
    if (tag.role === 'body') continue
    assert.equal(tag.role, 'decoration')
    assert.equal(tag.size, 'fit')
    assert.ok(tag.anchor && Number.isFinite(tag.anchor.u) && Number.isFinite(tag.anchor.v))
    assert.deepEqual(tag.offset, { dx: 0, dy: 0 })
  }
})

test('a library item placed at a point keeps its drawn size and its internal layout', () => {
  const s = armory('armory-server')
  const parts = instantiate(s, { x: 300, y: 200 }, { instance: 'i-1' })
  const natural = frameOf(s.elements)!
  const placed = frameOf(parts)!
  assert.deepEqual([placed.x, placed.y], [300, 200])
  close(placed.width, natural.width, 'width kept')
  close(placed.height, natural.height, 'height kept')
  // Every part moved by the same vector.
  const dx = 300 - natural.x
  const dy = 200 - natural.y
  s.elements.forEach((src, i) => {
    close(parts[i].x, (src.x as number) + dx, `${src.id}.x`)
    close(parts[i].y, (src.y as number) + dy, `${src.id}.y`)
    assert.notEqual(parts[i].id, src.id, 'fresh ids')
    assert.deepEqual(parts[i].groupIds, ['i-1'])
    assert.equal(parts[i].version, src.version, 'everything else is verbatim')
  })
})

test('a symbol scaled to a box scales its lines with it', () => {
  const s = armory('armory-server')
  const natural = frameOf(s.elements)!
  const parts = instantiate(s, { x: 0, y: 0, width: natural.width * 2, height: natural.height * 2 })
  const placed = frameOf(parts)!
  close(placed.width, natural.width * 2, 'width doubled')
  const srcLine = s.elements.find((e) => e.type === 'line')!
  const line = parts[s.elements.indexOf(srcLine)]
  close(line.width, (srcLine.width as number) * 2, 'line width doubled')
  const [, last] = srcLine.points as number[][]
  const [, placedLast] = line.points as number[][]
  close(placedLast[0], last[0] * 2, 'points scaled')
})

test('a library item without a body is refused with a sentence', () => {
  const fx = corpus.stencilFixture('armory-server') as { item: LibraryItem }
  assert.throws(() => fromLibraryItem(fx.item, {}), (err: unknown) => {
    assert.ok(err instanceof StencilError)
    assert.ok(err.errors.some((e) => e.includes('exactly one element with role "body"')))
    return true
  })
})

// --- finding and sweeping -------------------------------------------------------------

test('instances() finds both instances on the fixture board and nothing else', () => {
  const found = instances(corpus.elements('stencil-instances'))
  assert.deepEqual([...found.keys()].sort(), ['g-c-cmdb', 'g-c-itil'])
  assert.equal(found.get('g-c-itil')!.length, 5)
  assert.equal(found.get('g-c-cmdb')!.length, 4)
})

test('frameOf() recovers the layout boxes from the fixture board', () => {
  const found = instances(corpus.elements('stencil-instances'))
  const actor = frameOf(found.get('g-c-itil')!)!
  for (const [k, v] of Object.entries({ x: 126, y: 141, width: 120, height: 128 })) close(actor[k as keyof typeof actor], v, `actor.${k}`)
  assert.deepEqual(frameOf(found.get('g-c-cmdb')!), { x: 502, y: 202, width: 200, height: 76 })
})

test('sweep() removes every part and unbinds the arrow that pointed at it', () => {
  const board = corpus.elements('stencil-instances')
  const arrow = board.find((e) => e.type === 'arrow')!
  assert.equal((arrow.endBinding as { elementId: string }).elementId, 'c-cmdb')

  const withoutActor = sweep(board, ['g-c-itil'])
  assert.equal(withoutActor.length, board.length - 5)
  assert.deepEqual(withoutActor.find((e) => e.type === 'arrow')!.endBinding, arrow.endBinding, 'untouched')

  const withoutStore = sweep(board, ['g-c-cmdb'])
  assert.equal(withoutStore.length, board.length - 4)
  const after = withoutStore.find((e) => e.type === 'arrow')!
  assert.equal(after.endBinding, null, 'the binding to a swept body goes')
  assert.ok((after.startBinding as { elementId: string }).elementId, 'the other end stays')
  assert.ok(withoutStore.some((e) => e.id === 'neighbour'), 'the neighbour is untouched')
})

test('an instance without a frame falls back to its footprint', () => {
  const board = corpus.elements('instance-group')
  const found = instances(board)
  assert.deepEqual([...found.keys()], ['sg-77'])
  assert.equal(found.get('sg-77')!.length, 3)
  const swept = sweep(board, ['sg-77'])
  assert.deepEqual(swept.map((e) => e.id), ['box-next-to-instance'])
})

test('the old stamp tags are no longer read as an instance', () => {
  const el = {
    id: 'e1', type: 'ellipse', x: 0, y: 0, width: 10, height: 10,
    customData: { stamp: 'Operator', stampGroup: 'sg-77' },
  } as unknown as Element
  assert.equal(instanceOf(el), null)
  assert.deepEqual(instances([el]), new Map())
})

test('restyle() on an instance: paint on the body, tint elsewhere', () => {
  const parts = instantiate(stencil('bastion-datastore'), { x: 0, y: 0 })
  const styled = restyle(parts, { strokeColor: '#ff0000', backgroundColor: '#00ff00', opacity: 50 })
  for (const el of styled) {
    assert.equal(el.strokeColor, '#ff0000')
    assert.equal(el.opacity, 50)
    if (tagOf(el)!.role === 'body') assert.equal(el.backgroundColor, '#00ff00')
    else assert.notEqual(el.backgroundColor, '#00ff00')
  }
})

test('an arrow the model bound to an instance id is bound to its body', () => {
  const board = corpus.elements('stencil-instances')
  const patch = [
    { type: 'arrow', id: 'a1', x: 0, y: 0, points: [[0, 0], [10, 10]], start: { id: 'g-c-itil' }, end: { id: 'g-c-cmdb' } },
    { type: 'arrow', id: 'a2', x: 0, y: 0, points: [[0, 0], [10, 10]], start: { id: 'neighbour' }, end: { id: 'nowhere' } },
    { type: 'rectangle', id: 'r', x: 0, y: 0, width: 1, height: 1 },
  ]
  const out = bindToBodies(patch, board)
  assert.deepEqual(out[0].start, { id: 'c-itil' })
  assert.deepEqual(out[0].end, { id: 'c-cmdb' })
  assert.deepEqual(out[1], patch[1], 'refs to real elements or to nothing are untouched')
  assert.equal(out[2], patch[2])
})

test('defaultRoles picks the largest bindable shape as the body', () => {
  const server = corpus.stencilFixture('armory-server') as { item: LibraryItem; roles: RoleMap }
  assert.deepEqual(defaultRoles(server.item), server.roles, 'the chassis, as the fixture says')
  const man = corpus.stencilFixture('armory-stick-man') as { item: LibraryItem; roles: RoleMap }
  assert.deepEqual(defaultRoles(man.item), man.roles, 'the head')
  assert.deepEqual(defaultRoles({ name: 'lines', elements: [{ id: 'a', type: 'line', x: 0, y: 0, width: 9, height: 0 }] }), {})
  assert.throws(() => fromLibraryItem({ name: 'lines', elements: [{ id: 'a', type: 'line', x: 0, y: 0, width: 9, height: 0 }] }, {}), StencilError)
})

test('a role already marked on an element wins over the heuristic', () => {
  const item: LibraryItem = { name: 'two', elements: [
    { id: 'big', type: 'rectangle', x: 0, y: 0, width: 100, height: 100 },
    { id: 'small', type: 'ellipse', x: 0, y: 0, width: 10, height: 10, customData: { stencil: { role: 'body' } } },
  ] }
  assert.deepEqual(defaultRoles(item), { small: { role: 'body' } })
})

test('a caption is drawn beneath a stencil that has no label slot', () => {
  const s = armory('armory-server')
  const parts = instantiate(s, { x: 100, y: 50 }, { label: 'Web tier', instance: 'i-9', caption: { strokeColor: '#000000', fontFamily: 5 } })
  const caption = parts.at(-1)!
  assert.equal(caption.type, 'text')
  assert.equal(caption.text, 'Web tier')
  assert.equal(caption.fontFamily, 5)
  assert.equal(tagOf(caption)!.role, 'label')
  assert.equal(tagOf(caption)!.instance, 'i-9')
  assert.deepEqual(caption.groupIds, ['i-9'])
  const box = frameOf(parts)!
  close(caption.y, box.y + box.height + 8, 'beneath the subject')
  close(caption.x, box.x + box.width / 2 - 'Web tier'.length * 16 * 0.3, 'centred by the usual guess')
  assert.equal(instantiate(s, { x: 0, y: 0 }, { label: 'x' }).length, s.elements.length, 'no caption template, no caption')
  assert.equal(instantiate(stencil('bastion-actor'), { x: 0, y: 0 }, { label: 'x', caption: {} }).length, 5, 'a stencil with a label slot gets no caption')
})

test('a stroke drawn right-to-left does not push the frame off by its own width', () => {
  // Excalidraw keeps a line's origin at its first point; drawn from the right
  // its points run negative. The symbol's box must start where the ink
  // starts, and the derived frame must lead back to that box.
  const item: LibraryItem = { name: 'lid', elements: [
    { id: 'box', type: 'rectangle', x: 0, y: 10, width: 80, height: 50 },
    { id: 'lid', type: 'line', x: 80, y: 10, width: 80, height: 0, points: [[0, 0], [-80, 0]] },
    { id: 'tail', type: 'line', x: 40, y: 60, width: 0, height: 20, points: [[0, 0], [0, 20]] },
  ] }
  const s = fromLibraryItem(item, defaultRoles(item))
  assert.deepEqual(frameOf(s.elements), { x: 0, y: 10, width: 80, height: 70 }, 'the lid does not widen the box')
  const parts = instantiate(s, { x: 100, y: 100 }, { id: (src) => String(src.id) })
  const lid = parts.find((p) => p.id === 'lid')!
  assert.deepEqual([lid.x, lid.y], [180, 100], 'the lid keeps its origin at its right end')
  assert.deepEqual(frameOf(parts), { x: 100, y: 100, width: 80, height: 70 })
})
