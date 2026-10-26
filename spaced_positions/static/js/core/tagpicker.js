// The tag picker (spec 04 · Tags): one place to add and remove tags, by keyboard first. `t` (a move, the
// Library's selection, a training puzzle) and `T` (the position) open it at the bottom like the command line: the
// tags the target has are listed first (● on, ◐ some of a selection, ? suggested by the detection); typing searches
// every tag. ↵ switches the tag under the cursor on or off and closes, ⇥ does the same and stays open for the next
// one, ↑ ↓ move, Esc closes. A click works like ⇥.

import { pushUndo, run, serverRun } from "./commands.js"
import { ctx, keycaps, setLayer, status } from "./context.js"
import { setOverlayHandler } from "./keys.js"
import { tr } from "./i18n.js"

let el, input, results, hint
let state = null // {title, target, local, on: Map key → {n, suggested, label, note}, total, rows, cursor, ticket}
let previousLayer = "normal"

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""

function build() {
  el = document.createElement("div")
  el.className = "bottom-overlay cmdline tagpicker"
  el.hidden = true
  results = document.createElement("div")
  results.className = "cmdline__results"
  results.setAttribute("role", "listbox")
  const row = document.createElement("div")
  row.className = "cmdline__input-row"
  const prompt = document.createElement("span")
  prompt.className = "cmdline__prompt"
  prompt.textContent = "#"
  input = document.createElement("input")
  input.className = "cmdline__input"
  input.autocomplete = "off"
  input.spellcheck = false
  hint = document.createElement("span")
  hint.className = "cmdline__hint"
  row.append(prompt, input, hint)
  el.append(results, row)
  document.getElementById("statusline").append(el)
  input.addEventListener("input", () => { if (state) state.searching = search() })
}

/**
 * Open the picker. `target`: {c, ids} for the server (positions, games, nodes …), or `local`: {tags: [{key, label}],
 * (a function: the current ones), toggle(item)} for tags that live in the page (Collect's entry session).
 */
export async function openTagPicker({ title, target = null, local = null }) {
  if (!el) build()
  previousLayer = ctx.layer === "pending" ? "normal" : ctx.layer
  state = { title, target, local, on: new Map(), total: 1, rows: [], cursor: 0, ticket: 0 }
  ctx.overlay = "tagpicker"
  setLayer("command")
  el.hidden = false
  input.value = ""
  input.setAttribute("aria-label", title)
  setOverlayHandler(onKey)
  input.focus()
  await loadOn()
  state.searching = search()
}

function close() {
  if (!state) return
  el.hidden = true
  state = null
  ctx.overlay = null
  setOverlayHandler(null)
  input.blur()
  setLayer(previousLayer)
}

/** The tags the target has now. */
async function loadOn() {
  if (state.local) {
    state.on = new Map(state.local.tags().map((t) => [t.key, { n: 1, suggested: 0, label: t.label, note: t.note || "" }]))
    state.total = 1
    return
  }
  const data = await fetch("/lib/tags-of/", {
    method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(state.target),
  }).then((r) => r.json()).catch(() => ({ n: 0, tags: [] }))
  if (!state) return
  state.total = data.n || 1
  state.on = new Map(data.tags.map((t) => [t.value, { n: t.n, suggested: t.suggested, label: t.label, note: t.note }]))
}

async function search() {
  const ticket = ++state.ticket
  const text = input.value.trim()
  let items
  if (!text) {
    // nothing typed: what the target has, so taking a tag off is ↓ and ↵
    items = [...state.on].map(([value, t]) => ({ value, label: t.label, note: t.note }))
  } else {
    const data = await fetch(`/lib/complete/?kind=tag&q=${encodeURIComponent(text)}`).then((r) => r.json()).catch(() => ({ items: [] }))
    if (!state || ticket !== state.ticket) return
    items = data.items
  }
  state.rows = items
  state.cursor = Math.min(state.cursor, Math.max(0, items.length - 1))
  if (text) state.cursor = 0
  paint()
}

function mark(value) {
  const t = state.on.get(value)
  if (!t) return { glyph: "○", text: tr("↵ adds it") }
  if (t.n >= state.total) return { glyph: "●", text: tr("↵ takes it off") }
  if (t.n > 0) return { glyph: "◐", text: tr("{n} of {total} · ↵ adds it to all", { n: t.n, total: state.total }) }
  return { glyph: "?", text: tr("suggested · ↵ confirms it") }
}

function paint() {
  results.replaceChildren()
  state.rows.forEach((item, i) => {
    const row = document.createElement("div")
    row.className = `cmdline__row${i === state.cursor ? " is-cursor" : ""}`
    row.setAttribute("role", "option")
    const { glyph, text } = mark(item.value)
    const title = document.createElement("span")
    title.className = "cmdline__title"
    const check = Object.assign(document.createElement("span"), { className: "tagpicker__check", textContent: glyph })
    title.append(check, " ", item.label)
    const note = Object.assign(document.createElement("span"), { className: "cmdline__reason", textContent: item.note || "" })
    title.append(note)
    const action = Object.assign(document.createElement("span"), { className: "cmdline__group", textContent: text })
    row.append(title, document.createElement("span"), action)
    row.addEventListener("click", () => { state.cursor = i; toggle({ stay: true }) })
    results.append(row)
  })
  if (!state.rows.length) {
    const empty = Object.assign(document.createElement("div"), { className: "cmdline__row muted" })
    empty.textContent = input.value.trim() ? tr("No tag matches") : tr("No tags yet: type to find one")
    results.append(empty)
  }
  results.querySelector(".is-cursor")?.scrollIntoView({ block: "nearest" })
  hint.replaceChildren(state.title, " · ", keycaps(["enter"]), ` ${tr("on / off")} · `, keycaps(["tab"]), ` ${tr("and stay")} · `, keycaps(["esc"]))
}

async function toggle({ stay }) {
  // ↵ right after typing: the rows of what was typed. Wait for the newest search; another may start meanwhile
  let waited
  while (state && waited !== state.searching) {
    waited = state.searching
    await waited
  }
  if (!state) return
  const item = state.rows[state.cursor]
  if (!item) return
  if (state.local) {
    state.local.toggle(item)
  } else {
    const result = await serverRun("library.tagtoggle", [item.value], state.target)
    if (result) {
      status(result.message, { kind: "good", keys: { seq: ["u"], label: tr("undo") } })
      if (result.undo) {
        pushUndo({
          label: result.message,
          undo: () => run(result.undo.command, result.undo.args, { source: "undo" }),
          redo: () => run(result.redo.command, result.redo.args, { source: "undo" }),
        })
      }
    }
  }
  if (!state) return
  if (!stay) return close()
  await loadOn()
  if (state) paint()
}

function onKey(e, token) {
  if (token === "esc") return close()
  if (token === "enter") return toggle({ stay: false })
  if (token === "tab") return toggle({ stay: true })
  if (token === "down") {
    state.cursor = Math.min(state.rows.length - 1, state.cursor + 1)
    return paint()
  }
  if (token === "up") {
    state.cursor = Math.max(0, state.cursor - 1)
    return paint()
  }
  return "pass" // typing
}
