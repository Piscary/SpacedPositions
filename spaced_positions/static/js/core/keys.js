// Key events → bindings (spec 02 §4–5): layout-aware matching, sequences without timeouts, the resolution order,
// the which-key panel, sticky submodes and the Insert layer.

import { command, enabled, keymap, prefixes, run } from "./commands.js"
import { ctx, displayKey, emit, isMac, keycaps, setLayer, status } from "./context.js"
import { tokenFromEvent as toToken } from "./keyname.js"

let pending = []
let overlayHandler = null // set by overlays: (event, token) => "pass" (browser) | "fallthrough" (keymap) | anything else (handled)
let dynamicPrefixes = [] // providers of extra which-key entries, e.g. sections for "g <letter>"
const perf = [] // handler latencies of the last key presses (spec 01 · P5), read by the journey tests

export const tokenFromEvent = (e) => toToken(e, isMac)

const isEditable = (el) =>
  el instanceof HTMLElement && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) &&
  !(el instanceof HTMLInputElement && /^(button|checkbox|radio|submit|reset)$/.test(el.type))

/** The contexts that are active now, in resolution order (spec 02 §5). */
export function activeContexts() {
  const chain = []
  if (!["normal", "insert", "pending", "command"].includes(ctx.layer)) chain.push(`layer.${ctx.layer}`)
  if (ctx.pane) {
    chain.push(`view.${ctx.pane.view}`)
    if (window.SPOS.views[ctx.pane.view]?.list) chain.push("view.list")
    chain.push("pane")
  }
  chain.push(`mode.${ctx.mode}`, "global")
  return chain
}

function hasPrefix(map, seq) {
  const start = seq + " "
  return Object.keys(map).some((k) => k.startsWith(start))
}

export function setOverlayHandler(fn) {
  overlayHandler = fn
}

/** Register extra which-key entries for a prefix: provider(prefixTokens) → [{key, label, action}] */
export function addDynamicPrefix(provider) {
  dynamicPrefixes.push(provider)
}

function dynamicEntries(seq) {
  return dynamicPrefixes.flatMap((provider) => provider(seq) || [])
}

function onKeyDown(e) {
  const token = tokenFromEvent(e)
  if (!token) return

  if (overlayHandler) {
    const result = overlayHandler(e, token)
    if (result === "pass") return // the browser handles it (typing in an overlay's field)
    if (result !== "fallthrough") {
      e.preventDefault()
      e.stopPropagation()
      return
    } // fallthrough: the overlay ignores the key, the keymap gets it
  }

  if (isEditable(e.target)) {
    if (ctx.layer !== "insert") setLayer("insert")
    const binding = keymap()["layer.insert"]?.[token]
    if (binding) {
      e.preventDefault()
      run(binding.command, binding.args)
    }
    return // everything else types
  }

  if (token === "esc" && pending.length) {
    e.preventDefault()
    cancelPending()
    return
  }

  const seq = [...pending, token]
  const text = seq.join(" ")
  let isPrefix = false
  for (const context of activeContexts()) {
    const map = keymap()[context]
    if (!map) continue
    const binding = map[text]
    if (binding) {
      e.preventDefault()
      const sticky = command(binding.command)?.sticky && seq.length > 1
      if (sticky) {
        pending = seq.slice(0, -1)
        showPending(true)
      } else {
        cancelPending()
      }
      const started = performance.now()
      run(binding.command, binding.args).finally(() => {
        perf.push({ keys: text, ms: performance.now() - started })
        if (perf.length > 50) perf.shift()
      })
      return
    }
    if (hasPrefix(map, text)) {
      isPrefix = true
      break // the first context that has this prefix owns it (design check forbids overlaps)
    }
  }

  const dynamic = dynamicEntries(pending).find((entry) => entry.key === token)
  if (pending.length && dynamic) {
    e.preventDefault()
    cancelPending()
    dynamic.action()
    return
  }

  if (isPrefix || dynamicEntries(seq).length) {
    e.preventDefault()
    pending = seq
    showPending()
    return
  }

  if (pending.length) {
    e.preventDefault()
    const shown = seq.map(displayKey).join(" ")
    cancelPending()
    status(`${shown} is not bound here`, { kind: "error", timeout: 3000 })
  }
  // A single unbound key falls through to the browser.
}

export function cancelPending() {
  pending = []
  whichKey.hidden = true
  document.getElementById("status-pending").replaceChildren()
  if (ctx.layer === "pending") setLayer(ctx.selection.visual ? "visual" : "normal")
}

/** Feed a key as if it had been typed (clicking a which-key entry). */
export function feed(token) {
  onKeyDown(new KeyboardEvent("keydown", { key: token === "space" ? " " : token, bubbles: true }))
}

// ── Which-key ──────────────────────────────────────────────────────────────────────────────────────────────────

const whichKey = document.createElement("div")
whichKey.className = "bottom-overlay whichkey"
whichKey.hidden = true

function nextEntries(seq) {
  const text = seq.join(" ")
  const entries = new Map()
  for (const context of activeContexts()) {
    const map = keymap()[context]
    if (!map) continue
    for (const [key, binding] of Object.entries(map)) {
      if (!key.startsWith(text + " ")) continue
      const rest = key.slice(text.length + 1).split(" ")
      if (entries.has(rest[0])) continue
      if (rest.length === 1) {
        const spec = command(binding.command)
        entries.set(rest[0], {
          key: rest[0],
          label: spec ? spec.title + (binding.args.length ? ` ${binding.args.join(" ")}` : "") : binding.command,
          disabled: !enabled(binding.command).ok,
        })
      } else {
        const group = prefixes()[`${text} ${rest[0]}`]
        entries.set(rest[0], { key: rest[0], label: `+${group || "more"}`, group: true })
      }
    }
  }
  for (const entry of dynamicEntries(seq)) if (!entries.has(entry.key)) entries.set(entry.key, entry)
  return [...entries.values()]
}

function showPending(sticky = false) {
  setLayer("pending")
  const shown = document.getElementById("status-pending")
  shown.replaceChildren(keycaps(pending), " …")
  const title = document.createElement("div")
  title.className = "whichkey__title"
  const name = prefixes()[pending.join(" ")]
  title.append(keycaps(pending), ` ${name || ""}${sticky ? " · sticky: keep pressing, Esc ends" : ""}`)
  const grid = document.createElement("div")
  grid.className = "whichkey__grid"
  for (const entry of nextEntries(pending)) {
    const item = document.createElement("div")
    item.className = `whichkey__item${entry.group ? " is-group" : ""}${entry.disabled ? " is-disabled" : ""}`
    const label = document.createElement("span")
    label.className = "whichkey__label"
    label.textContent = entry.label
    item.append(keycaps([entry.key]), label)
    item.addEventListener("click", () => feed(entry.key))
    grid.append(item)
  }
  whichKey.replaceChildren(title, grid)
  whichKey.hidden = false
}

export const keyPerf = () => perf

export function initKeys() {
  document.getElementById("statusline").append(whichKey)
  window.addEventListener("keydown", onKeyDown, true)
  document.addEventListener("focusin", (e) => {
    if (isEditable(e.target) && !overlayHandler) setLayer("insert")
  })
  document.addEventListener("focusout", (e) => {
    if (isEditable(e.target) && ctx.layer === "insert") setLayer(ctx.selection.visual ? "visual" : "normal")
  })
  emit("keys:ready")
}
