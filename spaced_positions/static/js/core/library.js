// The Library (spec 04 · Library, 11 §3): the QueryBar with completions, the results of a query in one of six
// collections and three displays, bulk commands on the selection, and the filter pane that writes into the query.
// The query string is the single source of truth; each library pane keeps {q, c, display} per link group.

import { handle, pushUndo, serverRun } from "./commands.js"
import { ctx, emit, on, setLayer, status } from "./context.js"
import { offer } from "./confirm.js"
import { focusPane, nodeOf, switchMode } from "./layout.js"
import { cursorIndex, resetList, targetRows } from "./lists.js"
import { openCmdline } from "./cmdline.js"

const DISPLAYS = ["table", "list", "grid"]
const state = new WeakMap() // library element → {q, c, display, ticket}
const saved = {} // group → {q, c, display}, from the UI state

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""

function groupOf(el) {
  const node = nodeOf(el.closest("[data-pane]"))
  return node?.group && !node.pinned ? node.group : node?.id || "A"
}

function stateOf(el) {
  if (!state.has(el)) state.set(el, { q: "", c: "positions", display: "table", ticket: 0, ...(saved[groupOf(el)] || {}) })
  return state.get(el)
}

const libraries = () => [...document.querySelectorAll(".workspace [data-island='library']")]
const focusedLibrary = () => ctx.pane?.el?.querySelector("[data-island='library']") || null
/** The library a command means: the focused one, else the one on screen. */
const currentLibrary = () => focusedLibrary() || document.querySelector(".workspace:not([hidden]) [data-island='library']")

// ── Results ───────────────────────────────────────────────────────────────────────────────────────────────────

async function refresh(el, { keep = false, clear = false } = {}) {
  const st = stateOf(el)
  const list = el.querySelector("[data-library-results]")
  const ticket = ++st.ticket
  const index = keep ? Math.max(0, cursorIndex(list)) : 0
  const params = new URLSearchParams({ q: st.q, c: st.c, display: st.display })
  const html = await fetch(`/lib/results/?${params}`).then((r) => r.text()).catch(() => null)
  if (html === null || ticket !== st.ticket) return // a newer query is on its way
  list.innerHTML = html
  list.dataset.display = st.display
  el.dataset.collection = st.c
  el.dataset.display = st.display
  const info = JSON.parse(list.querySelector("#query-info")?.textContent || "{}")
  paintInfo(el, info)
  resetList(list, { index, clear })
  for (const tab of el.querySelectorAll(".library__tabs [role=radio]")) tab.setAttribute("aria-checked", String(tab.dataset.args === st.c))
  emit("library:query", { group: groupOf(el), q: st.q, c: st.c })
  save(el)
}

function paintInfo(el, info) {
  const count = el.querySelector("[data-query-count]")
  count.textContent = info.count === undefined ? "" : `${info.count.toLocaleString()} ${stateOf(el).c}`
  const box = el.querySelector("[data-query-problems]")
  box.replaceChildren()
  const text = stateOf(el).q
  for (const p of info.problems || []) {
    const chip = document.createElement("span")
    chip.className = "chip chip--bad querybar__problem"
    chip.textContent = `${text.slice(p.start, p.end) || "?"} · ${p.message}`
    box.append(chip)
  }
}

let saveTimer
function save() {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    const library = {}
    for (const el of libraries()) {
      const { q, c, display } = stateOf(el)
      library[groupOf(el)] = { q, c, display }
    }
    fetch(`/state/library/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ subject: { library } }),
      keepalive: true,
    }).catch(() => {})
  }, 500)
}

on("workspace", ({ mode, el }) => {
  if (mode !== "library") return
  const script = el.querySelector(":scope > script#subject-library")
  Object.assign(saved, JSON.parse(script?.textContent || "{}").library || {})
})

// ── The QueryBar ──────────────────────────────────────────────────────────────────────────────────────────────

const typingTimers = new WeakMap()

function mountQueryBar(el) {
  const input = el.querySelector("[data-querybar]")
  const menu = el.querySelector("[data-query-complete]")
  input.value = stateOf(el).q
  input.addEventListener("input", () => {
    stateOf(el).q = input.value
    clearTimeout(typingTimers.get(el))
    typingTimers.set(el, setTimeout(() => refresh(el), 140))
    complete(el)
  })
  input.addEventListener("keydown", (e) => {
    const open = !menu.hidden && menu.children.length
    if (e.key === "Tab" && !e.shiftKey) {
      e.preventDefault()
      if (open) return accept(el)
      return complete(el, { accept: true })
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault()
      if (open) return moveCompletion(el, e.key === "ArrowDown" ? 1 : -1)
      if (e.key === "ArrowDown") return toResults(el)
    }
    if (e.key === "Enter" && !e.metaKey && !e.ctrlKey) {
      e.preventDefault()
      if (open && menu.dataset.moved) return accept(el)
      clearTimeout(typingTimers.get(el))
      refresh(el).then(() => toResults(el))
    }
  })
  input.addEventListener("blur", () => setTimeout(() => closeCompletion(el), 150))
  menu.addEventListener("mousedown", (e) => {
    const row = e.target.closest("[data-value]")
    if (!row) return
    e.preventDefault()
    menu.querySelectorAll("[data-value]").forEach((r) => r.classList.toggle("is-cursor", r === row))
    accept(el)
  })
}

function toResults(el) {
  closeCompletion(el)
  el.querySelector("[data-querybar]").blur()
  setLayer("normal")
  const pane = el.closest("[data-pane]")
  if (pane) focusPane(pane.dataset.pane)
}

let completeTicket = 0
async function complete(el, { accept: acceptOne = false } = {}) {
  const input = el.querySelector("[data-querybar]")
  const ticket = ++completeTicket
  const params = new URLSearchParams({ q: input.value, at: input.selectionStart ?? input.value.length, c: stateOf(el).c })
  const data = await fetch(`/lib/complete/?${params}`).then((r) => r.json()).catch(() => null)
  if (!data || ticket !== completeTicket) return
  const menu = el.querySelector("[data-query-complete]")
  menu.replaceChildren()
  menu.dataset.start = data.start
  menu.dataset.end = data.end
  delete menu.dataset.moved
  const word = input.value.slice(data.start, data.end)
  const items = (data.items || []).filter((i) => i.value !== word)
  if (!items.length || (!word && !acceptOne)) return closeCompletion(el)
  items.forEach((item, i) => {
    const row = document.createElement("div")
    row.className = `querybar__option${i === 0 ? " is-cursor" : ""}`
    row.setAttribute("role", "option")
    row.dataset.value = item.value
    const value = Object.assign(document.createElement("span"), { className: "mono", textContent: item.value })
    const label = Object.assign(document.createElement("span"), { className: "querybar__label", textContent: item.label === item.value ? "" : item.label })
    const note = Object.assign(document.createElement("span"), { className: "muted", textContent: item.note || "" })
    row.append(value, label, note)
    menu.append(row)
  })
  menu.hidden = false
  if (acceptOne) accept(el)
}

function moveCompletion(el, step) {
  const menu = el.querySelector("[data-query-complete]")
  const rows = [...menu.querySelectorAll("[data-value]")]
  const i = rows.findIndex((r) => r.classList.contains("is-cursor"))
  const next = (i + step + rows.length) % rows.length
  rows.forEach((r, j) => r.classList.toggle("is-cursor", j === next))
  rows[next].scrollIntoView({ block: "nearest" })
  menu.dataset.moved = "1"
}

function accept(el) {
  const menu = el.querySelector("[data-query-complete]")
  const row = menu.querySelector(".is-cursor[data-value]") || menu.querySelector("[data-value]")
  if (!row) return closeCompletion(el)
  const input = el.querySelector("[data-querybar]")
  const start = Number(menu.dataset.start)
  const end = Number(menu.dataset.end)
  const value = row.dataset.value
  const tail = value.endsWith(":") ? "" : " "
  input.value = input.value.slice(0, start) + value + tail + input.value.slice(end).replace(/^\s+/, "")
  const caret = start + value.length + tail.length
  input.setSelectionRange(caret, caret)
  closeCompletion(el)
  input.dispatchEvent(new Event("input"))
}

function closeCompletion(el) {
  const menu = el.querySelector("[data-query-complete]")
  menu.hidden = true
  menu.replaceChildren()
}

// ── Mounting ──────────────────────────────────────────────────────────────────────────────────────────────────

export function mountLibrary(el) {
  mountQueryBar(el)
  refresh(el)
}

on("selection", ({ list }) => {
  const el = list.closest("[data-island='library']")
  if (!el) return
  const bar = el.querySelector("[data-bulk]")
  const n = targetRows(list).selected ? targetRows(list).ids.length : 0
  bar.hidden = n === 0
  bar.querySelector("[data-bulk-count]").textContent = `${n} selected`
})

on("effects", (effects) => {
  if (effects.library !== "changed") return
  for (const el of libraries()) refresh(el, { keep: true })
  emit("library:changed", {})
})

// ── The filter pane ───────────────────────────────────────────────────────────────────────────────────────────

const facetTimers = new WeakMap()

export function mountFilters(el) {
  const group = groupOf(el)
  const library = libraries().find((l) => groupOf(l) === group && l.closest(".workspace") === el.closest(".workspace"))
  if (library) loadFacets(el, stateOf(library))
}

async function loadFacets(el, { q, c }) {
  const list = el.querySelector("[data-filters]")
  if (c !== "positions") {
    list.innerHTML = '<p class="muted filters__empty">Facets are shown for positions (collection 1).</p>'
    return resetList(list)
  }
  const html = await fetch(`/lib/facets/?${new URLSearchParams({ q })}`).then((r) => r.text()).catch(() => null)
  if (html === null) return
  const index = Math.max(0, cursorIndex(list))
  list.innerHTML = html
  resetList(list, { index })
}

on("library:query", ({ group, q, c }) => {
  for (const el of document.querySelectorAll(".workspace [data-island='filters']")) {
    if (groupOf(el) !== group) continue
    clearTimeout(facetTimers.get(el))
    facetTimers.set(el, setTimeout(() => loadFacets(el, { q, c }), 250))
  }
})

/** A facet adds its term to the query of its group's library, or takes it out. */
function toggleTerm(term, row) {
  const el = row ? libraries().find((l) => groupOf(l) === groupOf(row) && l.closest(".workspace") === row.closest(".workspace")) : currentLibrary()
  if (!el) return false
  const st = stateOf(el)
  const words = st.q.split(/\s+/).filter(Boolean)
  st.q = words.includes(term) ? words.filter((w) => w !== term).join(" ") : [...words, term].join(" ")
  el.querySelector("[data-querybar]").value = st.q
  return refresh(el)
}

handle("library.exclude", () => {
  const list = ctx.pane?.el?.querySelector("[data-filters]")
  const [term] = list ? targetRows(list).ids : []
  if (!term) return false
  const row = list.querySelector(`[data-term="${CSS.escape(term)}"]`)
  return toggleTerm(term.startsWith("-") ? term.slice(1) : `-${term}`, row)
})

/** Show a query (a player's games, a source's positions …), in this library or the Library mode's. */
async function setQuery(text, collection) {
  let el = currentLibrary()
  if (!el) {
    await switchMode("library")
    el = currentLibrary()
  }
  if (!el) return status("The Library has no results pane: ␣ w v, then l", { kind: "error" }) || false
  const st = stateOf(el)
  st.q = text
  if (collection) st.c = collection
  el.querySelector("[data-querybar]").value = st.q
  return refresh(el, { clear: Boolean(collection) })
}

// ── Commands ──────────────────────────────────────────────────────────────────────────────────────────────────

const withLibrary = (fn) => (args) => {
  const el = currentLibrary()
  if (!el) return false
  return fn(el, stateOf(el), args)
}

handle("library.collection", withLibrary((el, st, [c]) => {
  if (st.c === c) return false
  st.c = c
  return refresh(el, { clear: true })
}))

handle("library.display", withLibrary((el, st, [display]) => {
  st.display = display || DISPLAYS[(DISPLAYS.indexOf(st.display) + 1) % DISPLAYS.length]
  status(`Results as ${st.display}`, { timeout: 1500 })
  return refresh(el, { keep: true })
}))

handle("library.query", async ([text]) => {
  if (ctx.mode !== "library") await switchMode("library")
  const el = currentLibrary()
  if (!el) return false
  if (text) return setQuery(text)
  focusPane(el.closest("[data-pane]").dataset.pane)
  el.querySelector("[data-querybar]").focus()
  setLayer("insert")
})

/** What a bulk command acts on: in the Library the selection (or cursor row), in Analyse the open position (or,
 *  for move tags, the move), in Train the puzzle's position. */
function target({ moves = false } = {}) {
  const el = focusedLibrary()
  if (el) {
    const { ids } = targetRows(el.querySelector("[data-library-results]"))
    return { c: stateOf(el).c, ids, el }
  }
  if (ctx.mode === "analyse") {
    const t = window.SPOS.analysis?.current()
    if (!t) return null
    if (moves) return t.cursor === t.root ? null : { c: "nodes", ids: [`n${t.cursor}`] }
    return { c: "positions", ids: [t.position.id] }
  }
  if (ctx.mode === "train") {
    const p = window.SPOS.train?.puzzle()
    return p ? { c: "positions", ids: [p.position] } : null
  }
  return null
}

async function bulk(id, args, t) {
  const result = await serverRun(id, args, { c: t.c, ids: t.ids })
  if (!result) return false
  status(result.message, { kind: "good", keys: result.undo ? { seq: ["u"], label: "undo" } : null })
  if (result.undo) pushUndo(inverse(result))
  return true
}

/** An undo step that replays the stored inverse on the server (not the command's client side, which would act on
 *  whatever is selected now). */
export function inverse(result) {
  return {
    label: result.message,
    undo: () => serverRun(result.undo.command, result.undo.args),
    redo: () => serverRun(result.redo.command, result.redo.args),
  }
}

handle("library.tag", ([tag]) => {
  if (!tag) return openCmdline("tag ")
  const t = target({ moves: window.SPOS.library.pendingMoveTags }) // `t` in Analyse: the move, not the position
  window.SPOS.library.pendingMoveTags = false
  if (!t?.ids.length) return status("Nothing to tag here", { kind: "error" }) || false
  return bulk("library.tag", [tag], t)
})

handle("library.untag", ([tag]) => {
  if (!tag) return openCmdline("untag ")
  const t = target({ moves: window.SPOS.library.pendingMoveTags })
  window.SPOS.library.pendingMoveTags = false
  if (!t?.ids.length) return status("Nothing selected", { kind: "error" }) || false
  return bulk("library.untag", [tag], t)
})

const libraryTarget = (fn) => () => {
  const t = target()
  if (!t?.el) return false
  if (!t.ids.length) return status("Nothing here", { kind: "error" }) || false
  return fn(t, stateOf(t.el))
}

handle("library.trash", libraryTarget((t) => bulk("library.trash", [], t)))
handle("library.restore", libraryTarget((t) => bulk("library.restore", [], t)))

handle("library.emptytrash", () => {
  offer("Empty the trash? Its positions and games are deleted for good (trained ones stay). y / n", {
    y: () => serverRun("library.emptytrash", []).then((r) => r && status(r.message, { kind: "good" })),
  })
})

handle("library.savequery", withLibrary(async (el, st, args) => {
  const name = args.join(" ")
  const result = await serverRun("library.savequery", [name], { q: st.q, c: st.c })
  if (result) status(result.message, { kind: "good", timeout: 5000 })
}))

const params = (t, st) => new URLSearchParams({ c: st.c, ids: t.ids.join(","), q: st.q })

handle("library.train", libraryTarget(async (t, st) => {
  const all = !targetRows(t.el.querySelector("[data-library-results]")).selected
  const body = { c: st.c, ids: all ? [] : t.ids, q: st.q } // nothing selected: everything the query found
  const data = await fetch("/lib/cards/", {
    method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(body),
  }).then((r) => r.json()).catch(() => null)
  if (!data?.cards?.length) return status("No puzzles in training among these (p r in Analyse puts one into training)", { kind: "error" }) || false
  return window.SPOS.train.start({ mode: "review", cards: data.cards, look: "normal", side: "move" })
}))

handle("library.analyse", libraryTarget(async (t, st) => {
  const all = !targetRows(t.el.querySelector("[data-library-results]")).selected
  const data = await fetch(`/lib/subject/?${params(all ? { ids: [] } : t, st)}`).then((r) => r.json()).catch(() => null)
  if (!data?.ids?.length) return status("Nothing to analyse here", { kind: "error" }) || false
  if (st.c === "games") return window.SPOS.analysis.openGame?.(data.ids[0], { list: { ids: data.ids, index: 0, kind: "game" } })
  return window.SPOS.analysis.open(data.ids[0], { list: { ids: data.ids, index: 0 } })
}))

handle("library.copyfen", libraryTarget(async (t, st) => {
  const data = await fetch(`/lib/fens/?${params(t, st)}`).then((r) => r.json()).catch(() => null)
  if (!data?.fens?.length) return false
  try {
    await navigator.clipboard.writeText(data.fens.join("\n"))
    status(data.fens.length === 1 ? "Copied FEN" : `Copied ${data.fens.length} FENs`, { kind: "good", timeout: 2500 })
  } catch {
    status("The browser didn't allow copying", { kind: "error" })
  }
}))

handle("library.export", libraryTarget((t, st) => {
  if (!["positions", "games"].includes(st.c)) return status("Positions and games export as PGN", { kind: "error" }) || false
  const all = !targetRows(t.el.querySelector("[data-library-results]")).selected
  const link = document.createElement("a")
  link.href = `/lib/export/?${params(all ? { ids: [] } : t, st)}`
  link.download = ""
  document.body.append(link)
  link.click()
  link.remove()
  status(all ? "Exporting everything the query found" : `Exporting ${t.ids.length}`, { timeout: 2500 })
}))

// Analyse: `t` tags the move, `T` the position (through :tag, with the tag's completion).
handle("analysis.tags", () => {
  if (!target({ moves: true })) return status("Go to a move first (T tags the position)", { kind: "error" }) || false
  window.SPOS.library.pendingMoveTags = true
  return openCmdline("tag ")
})
handle("analysis.untag", ([tag]) => {
  const t = target({ moves: true })
  if (!t) return false
  if (!tag) {
    window.SPOS.library.pendingMoveTags = true
    return openCmdline("untag ")
  }
  return bulk("library.untag", [tag], t)
})
handle("analysis.positiontags", () => {
  window.SPOS.library.pendingMoveTags = false
  return openCmdline("tag ")
})
handle("train.tag", () => {
  if (!target()) return false
  window.SPOS.library.pendingMoveTags = false
  return openCmdline("tag ")
})

Object.assign((window.SPOS ||= {}), {
  library: {
    toggleTerm,
    setQuery,
    pendingMoveTags: false,
    hasTarget: () => Boolean(target()),
    state: () => {
      const el = currentLibrary()
      return el ? { ...stateOf(el) } : null
    },
  },
})
