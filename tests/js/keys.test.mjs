// node --test tests/js   (pure modules only: no DOM)
import assert from "node:assert/strict"
import { test } from "node:test"

import { tokenFromEvent } from "../../spaced_positions/static/js/core/keyname.js"
import { evaluate } from "../../spaced_positions/static/js/core/when.js"

const ev = (key, extra = {}) => ({ key, code: "", shiftKey: false, altKey: false, ctrlKey: false, metaKey: false, ...extra })

test("printable keys match the produced character", () => {
  assert.equal(tokenFromEvent(ev("j"), true), "j")
  assert.equal(tokenFromEvent(ev("G", { shiftKey: true }), true), "G")
  assert.equal(tokenFromEvent(ev("?", { shiftKey: true }), true), "?")
  assert.equal(tokenFromEvent(ev(":", { shiftKey: true }), false), ":")
})

test("named keys and shift", () => {
  assert.equal(tokenFromEvent(ev(" "), true), "space")
  assert.equal(tokenFromEvent(ev("Tab", { shiftKey: true }), true), "shift+tab")
  assert.equal(tokenFromEvent(ev("ArrowUp"), true), "up")
  assert.equal(tokenFromEvent(ev("F5"), true), "f5")
})

test("mod is ⌘ on macOS and Ctrl elsewhere", () => {
  assert.equal(tokenFromEvent(ev("Enter", { metaKey: true }), true), "mod+enter")
  assert.equal(tokenFromEvent(ev("Enter", { ctrlKey: true }), false), "mod+enter")
  assert.equal(tokenFromEvent(ev("Z", { metaKey: true, shiftKey: true }), true), "mod+shift+z")
  assert.equal(tokenFromEvent(ev("k", { ctrlKey: true }), true), "ctrl+k")
})

test("alt chords use the physical key (⌥k gives ˚ on macOS)", () => {
  assert.equal(tokenFromEvent(ev("˚", { altKey: true, code: "KeyK" }), true), "alt+k")
})

test("modifiers alone and dead keys give no token", () => {
  assert.equal(tokenFromEvent(ev("Shift", { shiftKey: true }), true), null)
  assert.equal(tokenFromEvent(ev("Dead"), true), null)
})

test("when expressions", () => {
  const values = { panes: 2, "view.list": true, "pane.pinned": false, mode: "train", count: 0 }
  const look = (name) => values[name]
  assert.equal(evaluate("", look), true)
  assert.equal(evaluate("panes > 1", look), true)
  assert.equal(evaluate("view.list && !pane.pinned", look), true)
  assert.equal(evaluate("mode == 'train' && (count > 0 || panes >= 2)", look), true)
  assert.equal(evaluate("count != 0", look), false)
  assert.throws(() => evaluate("panes >", look))
})
