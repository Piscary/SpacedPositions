// Hint layer `F` (spec 02 §2): a label on every clickable element; typing a label clicks it. This makes every
// mouse target reachable from the keyboard.

import { handle } from "./commands.js"
import { ctx, setLayer } from "./context.js"
import { setOverlayHandler } from "./keys.js"

const ALPHABET = "asdfjklghqwertyuiopzxcvbnm"
const TARGETS = "button, a[href], [data-cmd], [data-row], [data-section-toggle], input, textarea, select, [role=radio]"

let layer = null

function visible(el) {
  if (el.closest("[hidden]") || el.closest(".workspace[hidden]")) return false
  const r = el.getBoundingClientRect()
  if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.right < 0 || r.top > innerHeight || r.left > innerWidth) return false
  const hit = document.elementFromPoint(Math.min(innerWidth - 1, r.left + Math.min(6, r.width / 2)), Math.min(innerHeight - 1, r.top + r.height / 2))
  return Boolean(hit && (el === hit || el.contains(hit) || hit.contains(el)))
}

function labels(count) {
  if (count <= ALPHABET.length) return [...ALPHABET.slice(0, count)]
  const out = []
  for (const a of ALPHABET) for (const b of ALPHABET) { out.push(a + b); if (out.length === count) return out }
  return out
}

function open() {
  const seen = new Set()
  const targets = [...document.querySelectorAll(TARGETS)].filter((el) => {
    const top = el.closest("[data-cmd], [data-row], [data-section-toggle]") || el
    if (seen.has(top)) return false
    seen.add(top)
    return top === el && visible(el)
  })
  if (!targets.length) return false
  const names = labels(targets.length)
  layer = { el: document.createElement("div"), items: [], typed: "", previous: ctx.layer }
  layer.el.className = "hint-layer"
  targets.forEach((target, i) => {
    const r = target.getBoundingClientRect()
    const label = document.createElement("span")
    label.className = "hint-label"
    label.textContent = names[i]
    label.style.left = `${Math.max(2, r.left)}px`
    label.style.top = `${Math.max(2, r.top)}px`
    layer.el.append(label)
    layer.items.push({ name: names[i], target, label })
  })
  document.body.append(layer.el)
  ctx.overlay = "hint"
  setLayer("hint")
  setOverlayHandler(onKey)
}

function close() {
  layer?.el.remove()
  setLayer(layer?.previous === "pending" ? "normal" : layer?.previous || "normal")
  layer = null
  ctx.overlay = null
  setOverlayHandler(null)
}

function onKey(e, token) {
  if (token === "esc") return close()
  if (token === "backspace") layer.typed = layer.typed.slice(0, -1)
  else if (/^[a-z]$/.test(token)) layer.typed += token
  else return
  const matches = layer.items.filter((item) => item.name.startsWith(layer.typed))
  for (const item of layer.items) {
    const on = matches.includes(item)
    item.label.classList.toggle("is-out", !on)
    item.label.replaceChildren()
    if (on) item.label.append(Object.assign(document.createElement("b"), { textContent: layer.typed }), item.name.slice(layer.typed.length))
  }
  if (matches.length === 1 && matches[0].name === layer.typed) {
    const { target } = matches[0]
    close()
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) target.focus()
    else {
      ctx.viaHint = true // the click comes from the keyboard: commands count it as "hint", not "mouse"
      try { target.click() } finally { ctx.viaHint = false }
    }
  } else if (!matches.length) close()
}

handle("hint.open", () => open())
