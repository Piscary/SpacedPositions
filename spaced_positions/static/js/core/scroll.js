// Moving through a pane with the keyboard (spec 03 §2): scrolling, and `i` to start editing its text field.

import { handle } from "./commands.js"
import { FIELDS, ctx, setLayer, status } from "./context.js"
import { tr } from "./i18n.js"

const lastField = new WeakMap() // pane element → the field edited last, so `i` returns to it

function scroller() {
  return ctx.pane?.el?.querySelector(".pane__body") || null
}

handle("pane.scroll", ([by]) => {
  const el = scroller()
  if (!el) return false
  const line = parseFloat(getComputedStyle(document.documentElement).fontSize) * 3
  const page = el.clientHeight
  const steps = {
    down: line, up: -line, halfdown: page / 2, halfup: -page / 2, pagedown: page * 0.9, pageup: -page * 0.9,
  }
  // Instant, like a terminal: the key's effect is visible in the same frame (spec 01 · P5).
  if (by === "top") el.scrollTop = 0
  else if (by === "bottom") el.scrollTop = el.scrollHeight
  else el.scrollTop += steps[by]
})

handle("pane.insert", () => {
  const pane = ctx.pane?.el
  if (!pane) return false
  const remembered = lastField.get(pane)
  const field = remembered?.isConnected ? remembered : [...pane.querySelectorAll(FIELDS)].find((f) => f.offsetParent)
  if (!field) return status(tr("This pane has no text field"), { kind: "error" }) || false
  field.focus()
  field.scrollIntoView({ block: "nearest" })
  setLayer("insert")
})

document.addEventListener("focusin", (e) => {
  const pane = e.target.closest?.("[data-pane]")
  if (pane && e.target.matches(FIELDS)) lastField.set(pane, e.target)
})
