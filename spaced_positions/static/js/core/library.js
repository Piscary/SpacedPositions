// The Library (spec 04 · Library, 11 §3): the QueryBar with completions, the results of a query in one of six
// collections and three displays, bulk commands on the selection, and the filter pane that writes into the query.
// The query string is the single source of truth; each library pane keeps {q, c, display} per link group.

import { handle, pushUndo, run, serverRun } from "./commands.js"
import { ctx, emit, on, setLayer, status } from "./context.js"
import { offer } from "./confirm.js"
import { focusPane, nodeOf, openBeside, switchMode } from "./layout.js"
import { cursorIndex, resetList, targetRows } from "./lists.js"
import { openCmdline } from "./cmdline.js"
import { openMenu } from "./menu.js"
import { openTagPicker } from "./tagpicker.js"
import { locale, tr, trn } from "./i18n.js"

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
  const keptRow = keep ? list.querySelector(".list__row.is-cursor")?.dataset.row : null
  const params = new URLSearchParams({ q: st.q, c: st.c, display: st.display })
  const html = await fetch(`/lib/results/?${params}`).then((r) => r.text()).catch(() => null)
  if (html === null || ticket !== st.ticket) return // a newer query is on its way
  list.innerHTML = html
  const rows = Boolean(list.querySelector("[data-row]")) // "nothing yet" is a message, not a list
  list.setAttribute("role", rows ? "listbox" : "status")
  list.toggleAttribute("aria-multiselectable", rows)
  if (rows) list.setAttribute("aria-multiselectable", "true")
  list.dataset.display = st.display
  el.dataset.collection = st.c
  el.dataset.display = st.display
  el.toggleAttribute("data-has-query", Boolean(st.q.trim()))
  const info = JSON.parse(list.querySelector("#query-info")?.textContent || "{}")
  paintInfo(el, info)
  paintFolds(el)
  st.count = info.count
  // the cursor stays on its row; when the row left the results (solved, retagged), on the one that took its place
  const kept = keptRow ? [...list.querySelectorAll("[data-row]")].findIndex((r) => r.dataset.row === keptRow) : -1
  resetList(list, { index: kept >= 0 ? kept : index, clear })
  for (const tab of el.querySelectorAll(".library__tabs [role=radio]")) tab.setAttribute("aria-checked", String(tab.dataset.args === st.c))
  emit("library:query", { group: groupOf(el), q: st.q, c: st.c })
  save(el)
}

function paintInfo(el, info) {
  const count = el.querySelector("[data-query-count]")
  count.textContent = info.count === undefined ? "" : countText(stateOf(el).c, info.count)
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
  bar.querySelector("[data-bulk-count]").textContent = tr("{n} selected", { n })
})

on("effects", (effects) => {
  if (effects.library !== "changed") return
  for (const el of libraries()) refresh(el, { keep: true })
  emit("library:changed", {})
})

// ── Work lists: the Library and the analysis of its link group work together ─────────────────────────────────

// An analysis changed (a move, a comment, a puzzle put into training): the Library's results follow, so a query
// like `no:solution src:"…" sort:source` is a work list that loses each position once it is done.
let changedTimer = null
on("analysis:changed", ({ position }) => {
  clearTimeout(changedTimer)
  changedTimer = setTimeout(async () => {
    for (const el of libraries()) {
      const list = el.querySelector("[data-library-results]")
      const had = Boolean(list.querySelector(`[data-position="${CSS.escape(position)}"]`))
      await refresh(el, { keep: true })
      const gone = had && !list.querySelector(`[data-position="${CSS.escape(position)}"]`)
      if (gone && !el.closest(".workspace[hidden]")) {
        status(tr("Done: it left the list ({n} to go) · n opens the next", { n: stateOf(el).count ?? 0 }), { kind: "good", timeout: 5000 })
      }
    }
  }, 300)
})

// Browsing the results previews the cursor's position or game in the move trees of the link group (a Moves pane
// beside the list shows its moves); nothing is opened until ↵ or a. Leaving the list ends the preview.
const previewTimers = new Map()
on("list:cursor", ({ list, row }) => {
  const el = list.closest("[data-island='library']")
  const id = row?.dataset.position || row?.dataset.game
  if (!el || !id || !list.matches("[data-library-results]")) return
  const key = `${ctx.mode}:${groupOf(el)}`
  if (!window.SPOS.analysis?.shownIn(key)) return
  clearTimeout(previewTimers.get(key))
  previewTimers.set(key, setTimeout(() => window.SPOS.analysis.preview(key, id, { title: row.dataset.title }), 120))
})

/** Open a result row for analysis: right here when this mode shows the analysis of the list's link group,
 *  else in Analyse. A list from a search goes along live (n opens the next one still to do). */
export function openRow(el, row, { list } = {}) {
  const id = row.dataset.game || row.dataset.position
  if (!id) return false
  const key = `${ctx.mode}:${groupOf(el)}`
  const here = window.SPOS.analysis?.shownIn(key) && ctx.mode !== "train"
  clearTimeout(previewTimers.get(key))
  return window.SPOS.analysis.open(id, { node: Number(row.dataset.node) || null, list, ...(here ? { key, stay: true } : {}) })
}

function liveList(el, row) {
  const st = stateOf(el)
  const rows = [...el.querySelectorAll("[data-library-results] [data-row]")]
  return { ids: [], q: st.q, c: st.c, index: Math.max(0, rows.indexOf(row)), count: st.count }
}

// `n` / `N` in the analysis moved on: the Library of that link group puts its cursor on the same row (no reopening).
on("analysis:subject", ({ key, position }) => {
  const [mode, group] = key.split(":")
  for (const el of libraries()) {
    if (!el.closest(`#ws-${mode}`) || groupOf(el) !== group) continue
    const list = el.querySelector("[data-library-results]")
    const rows = [...list.querySelectorAll("[data-row]")]
    const index = rows.findIndex((r) => (r.dataset.position || r.dataset.game) === position)
    if (index >= 0) {
      resetList(list, { index })
      rows[index].scrollIntoView({ block: "nearest" })
    }
  }
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
    list.innerHTML = `<p class="muted filters__empty">${tr("Facets are shown for positions (collection 1).")}</p>`
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
/** The terms of a query, a quoted value kept whole: `src:"Endgame Manual" diff:3` → two terms. */
const termsOf = (q) => q.match(/(?:[^\s"]+|"[^"]*"?)+/g) || []

/** The library a filter pane row (or the focused pane) works on: the one of the same link group. */
function libraryFor(row) {
  if (!row) return currentLibrary()
  return libraries().find((l) => groupOf(l) === groupOf(row) && l.closest(".workspace") === row.closest(".workspace")) || null
}

/** A new query for a library, undoable with `u` (the filter pane and the clear keys change it without typing). */
function changeQuery(el, text, label) {
  const st = stateOf(el)
  const before = st.q
  const put = (value) => {
    st.q = value
    el.querySelector("[data-querybar]").value = value
    return refresh(el)
  }
  if (text === before) return false
  pushUndo({ label, undo: () => put(before), redo: () => put(text) })
  return put(text)
}

function toggleTerm(term, row) {
  const el = libraryFor(row)
  if (!el) return false
  const words = termsOf(stateOf(el).q)
  const opposite = term.startsWith("-") ? term.slice(1) : `-${term}`
  if (words.includes(term)) return changeQuery(el, words.filter((w) => w !== term).join(" "), tr("Filter removed"))
  // a facet that is excluded comes back in (and the other way round): one term, never both
  return changeQuery(el, [...words.filter((w) => w !== opposite), term].join(" "), tr("Filter added"))
}

/** Take a part of the query out (a row of “In the search”): its span in the text. */
function removeSpan(span, row) {
  const el = libraryFor(row)
  if (!el) return false
  const [start, end] = span.split(":").map(Number)
  const text = stateOf(el).q
  const next = `${text.slice(0, start)} ${text.slice(end)}`.replace(/\s+/g, " ").trim()
  return changeQuery(el, next, tr("Filter removed"))
}

const filterTarget = () => {
  const pane = ctx.pane?.el
  const row = pane?.querySelector("[data-island='filters']")
  return row ? libraryFor(row) : currentLibrary()
}

handle("library.clear", () => {
  const el = filterTarget()
  if (!el || !stateOf(el).q.trim()) return status(tr("The search is already empty"), { timeout: 2000 }) || false
  status(tr("Search cleared · u brings it back"), { timeout: 3000 })
  return changeQuery(el, "", tr("Clear the search"))
})

handle("library.unfilter", () => {
  const el = filterTarget()
  const words = el ? termsOf(stateOf(el).q) : []
  if (!words.length) return status(tr("The search is already empty"), { timeout: 2000 }) || false
  status(tr("Took out {term} · u puts it back", { term: words.at(-1) }), { timeout: 3000 })
  return changeQuery(el, words.slice(0, -1).join(" "), tr("Take the last term out of the search"))
})

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
  if (!el) return status(tr("The Library has no results pane: ␣ w v, then l"), { kind: "error" }) || false
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

/** "1,234 positions" in the interface language. */
function countText(collection, n) {
  const shown = n.toLocaleString(locale)
  const forms = {
    positions: trn("{n} position", "{n} positions", n), games: trn("{n} game", "{n} games", n), puzzles: trn("{n} puzzle", "{n} puzzles", n),
    players: trn("{n} player", "{n} players", n), sources: trn("{n} source", "{n} sources", n), tags: trn("{n} tag", "{n} tags", n),
  }
  return (forms[collection] || `${n} ${collection}`).replace(String(n), shown)
}

const infoOf = (el) => JSON.parse(el.querySelector("[data-library-results] #query-info")?.textContent || "{}")

// `s`: sort by a column (the query's sort: term; the same column again reverses it)
handle("library.sort", withLibrary(async (el, st, [field]) => {
  const info = infoOf(el)
  const current = info.sort || ""
  if (!field) {
    field = await openMenu({
      title: tr("Sort by · the same again reverses · ▤ groups"),
      anchor: el,
      start: Math.max(0, (info.sorts || []).indexOf(current.replace(/^-/, ""))),
      items: (info.sorts || []).map((f) => ({
        label: `${f}${(info.groups || []).includes(f) ? " ▤" : ""}`,
        note: current === f ? tr("↑ now") : current === `-${f}` ? tr("↓ now") : "",
        key: f[0], keys: [f[0]], value: f,
      })),
    })
    if (!field) return false
  }
  const next = current === field ? `-${field}` : field
  st.q = [...termsOf(st.q).filter((w) => !/^-?sort:/.test(w)), `sort:${next}`].join(" ")
  el.querySelector("[data-querybar]").value = st.q
  return refresh(el)
}))

// ── Folded groups (`z` the cursor's group, `Z` all; a click on a group's header) ──────────────────────────────

const folds = new Map() // "collection sort" → the labels of the folded groups

const foldsOf = (el) => {
  const key = `${stateOf(el).c} ${infoOf(el).sort || ""}`
  if (!folds.has(key)) folds.set(key, new Set())
  return folds.get(key)
}

function paintFolds(el) {
  const list = el.querySelector("[data-library-results]")
  const folded = foldsOf(el)
  for (const head of list.querySelectorAll("[data-group-head]")) head.classList.toggle("is-folded", folded.has(head.dataset.groupHead))
  for (const row of list.querySelectorAll("[data-group]")) row.hidden = folded.has(row.dataset.group)
}

/** Fold or open groups; the cursor stays on its row, or goes to the next one that can be seen. */
function setFolds(el, change) {
  const list = el.querySelector("[data-library-results]")
  const rows = [...list.querySelectorAll("[data-row]")]
  const before = list.querySelector(".list__row.is-cursor")
  change(foldsOf(el))
  paintFolds(el)
  const start = Math.max(0, rows.indexOf(before))
  const target = [...rows.slice(start), ...rows.slice(0, start).reverse()].find((r) => !r.hidden)
  const visible = rows.filter((r) => !r.hidden)
  resetList(list, { index: Math.max(0, visible.indexOf(target)) })
}

handle("library.fold", withLibrary((el) => {
  const row = el.querySelector("[data-library-results] .list__row.is-cursor")
  const group = row?.dataset.group
  if (!group) return status(tr("Groups come with a sort by difficulty, source, year …: s"), { timeout: 2500 }) || false
  setFolds(el, (f) => (f.has(group) ? f.delete(group) : f.add(group)))
}))

handle("library.foldall", withLibrary((el) => {
  const heads = [...el.querySelectorAll("[data-library-results] [data-group-head]")].map((h) => h.dataset.groupHead)
  if (!heads.length) return status(tr("Groups come with a sort by difficulty, source, year …: s"), { timeout: 2500 }) || false
  const open = foldsOf(el).size > 0
  setFolds(el, (f) => (open ? f.clear() : heads.forEach((h) => f.add(h))))
  status(open ? tr("All groups open") : tr("All groups folded · z opens the one at the cursor"), { timeout: 1500 })
}))

document.addEventListener("click", (e) => {
  const head = e.target.closest("[data-library-results] [data-group-head]")
  if (!head) return
  const el = head.closest("[data-island='library']")
  const group = head.dataset.groupHead
  setFolds(el, (f) => (f.has(group) ? f.delete(group) : f.add(group)))
})

handle("library.collection", withLibrary((el, st, [c]) => {
  if (st.c === c) return false
  st.c = c
  return refresh(el, { clear: true })
}))

handle("library.display", withLibrary((el, st, [display]) => {
  st.display = display || DISPLAYS[(DISPLAYS.indexOf(st.display) + 1) % DISPLAYS.length]
  status({ table: tr("Results as a table"), list: tr("Results as a list"), grid: tr("Results as a grid") }[st.display] || st.display, { timeout: 1500 })
  return refresh(el, { keep: true })
}))

handle("library.query", async ([text]) => {
  if (!currentLibrary()) await switchMode("library") // a Library pane on screen (e.g. in Analyse) is used where it is
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
  status(result.message, { kind: "good", keys: result.undo ? { seq: ["u"], label: tr("undo") } : null })
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

/** The tag picker for a target: what it has, ↵ on / off (core/tagpicker.js). */
function pickTags(t, title) {
  if (!t?.ids.length) return status(tr("Nothing to tag here"), { kind: "error" }) || false
  return openTagPicker({ title, target: { c: t.c, ids: t.ids } })
}

const selectionTitle = (t) => (t.ids.length > 1 ? tr("Tags of {n} selected", { n: t.ids.length }) : tr("Tags"))

handle("library.tag", ([tag]) => {
  if (!tag) {
    const t = target({ moves: window.SPOS.library.pendingMoveTags })
    window.SPOS.library.pendingMoveTags = false
    return pickTags(t, selectionTitle(t || { ids: [] }))
  }
  const t = target({ moves: window.SPOS.library.pendingMoveTags }) // `t` in Analyse: the move, not the position
  window.SPOS.library.pendingMoveTags = false
  if (!t?.ids.length) return status(tr("Nothing to tag here"), { kind: "error" }) || false
  return bulk("library.tag", [tag], t)
})

handle("library.untag", ([tag]) => {
  if (!tag) return run("library.tag") // the picker: ↵ on a tag it has takes it off
  const t = target({ moves: window.SPOS.library.pendingMoveTags })
  window.SPOS.library.pendingMoveTags = false
  if (!t?.ids.length) return status(tr("Nothing selected"), { kind: "error" }) || false
  return bulk("library.untag", [tag], t)
})

const libraryTarget = (fn) => () => {
  const t = target()
  if (!t?.el) return false
  if (!t.ids.length) return status(tr("Nothing here"), { kind: "error" }) || false
  return fn(t, stateOf(t.el))
}

handle("library.detect", async () => {
  const t = target()
  if (!t?.ids.length || !["positions", "puzzles"].includes(t.c)) return status(tr("Select positions, or open one in Analyse"), { kind: "error" }) || false
  status(tr("Detecting…"), { timeout: 0 })
  return bulk("library.detect", [], t)
})

// `o`: the cursor row's position or game to the right, with a board and its move tree (linked to each other)
handle("library.beside", async () => {
  const el = focusedLibrary()
  const list = el?.querySelector("[data-library-results]")
  const row = list?.querySelector(".list__row.is-cursor")
  const id = row?.dataset.game || row?.dataset.position
  if (!id) return status(tr("o opens positions, puzzles and games beside the list"), { timeout: 2000 }) || false
  const group = await openBeside()
  const node = Number(row.dataset.node) || null
  await window.SPOS.analysis.open(id, { key: `library:${group}`, show: false, node })
  status(tr("{title} beside the list · ↵ opens it in Analyse", { title: row.dataset.title || tr("Position") }), { timeout: 2500 })
})

const VOCABULARY = ["players", "sources", "tags"]

// `d` on players, sources or tags deletes them (only those nothing uses); positions and games go to the trash
handle("library.trash", libraryTarget((t) => bulk(VOCABULARY.includes(t.c) ? "library.delete" : "library.trash", [], t)))

handle("library.edit", (args) => {
  if (!args.length) return openCmdline("edit ")
  const t = target()
  // `:edit @tal role=model` names what it edits; otherwise the Library's selection
  return bulk("library.edit", args, t?.el && VOCABULARY.includes(t.c) ? t : { c: "", ids: [] })
})

handle("library.delete", (args) => {
  const t = target()
  if (args.length) return bulk("library.delete", args, { c: "", ids: [] })
  if (!t?.el || !VOCABULARY.includes(t.c) || !t.ids.length) return status(tr("Select players, sources or tags in the Library (4 5 6)"), { kind: "error" }) || false
  return bulk("library.delete", [], t)
})
handle("library.restore", libraryTarget((t) => bulk("library.restore", [], t)))

handle("library.emptytrash", () => {
  offer(tr("Empty the trash? Its positions and games are deleted for good (trained ones stay). y / n"), {
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
  if (!data?.cards?.length) return status(tr("No puzzles in training among these (p r in Analyse puts one into training)"), { kind: "error" }) || false
  return window.SPOS.train.start({ mode: "review", cards: data.cards, look: "normal", side: "move" })
}))

// `a`: the cursor's row with the search as a live list (n opens the next one still to do), or the selection in order
handle("library.analyse", libraryTarget(async (t, st) => {
  const results = t.el.querySelector("[data-library-results]")
  const row = results.querySelector(".list__row.is-cursor") || results.querySelector("[data-row]")
  if (!targetRows(results).selected) {
    if (!row?.dataset.position && !row?.dataset.game) return status(tr("Positions, puzzles and games can be analysed"), { kind: "error" }) || false
    return openRow(t.el, row, { list: liveList(t.el, row) })
  }
  const data = await fetch(`/lib/subject/?${params(t, st)}`).then((r) => r.json()).catch(() => null)
  if (!data?.ids?.length) return status(tr("Nothing to analyse here"), { kind: "error" }) || false
  const first = results.querySelector(`[data-position="${CSS.escape(data.ids[0])}"], [data-game="${CSS.escape(data.ids[0])}"]`)
  if (first) return openRow(t.el, first, { list: { ids: data.ids, index: 0 } })
  return window.SPOS.analysis.open(data.ids[0], { list: { ids: data.ids, index: 0 } })
}))

handle("library.copyfen", libraryTarget(async (t, st) => {
  const data = await fetch(`/lib/fens/?${params(t, st)}`).then((r) => r.json()).catch(() => null)
  if (!data?.fens?.length) return false
  try {
    await navigator.clipboard.writeText(data.fens.join("\n"))
    status(trn("Copied {n} FEN", "Copied {n} FENs", data.fens.length), { kind: "good", timeout: 2500 })
  } catch {
    status(tr("The browser didn't allow copying"), { kind: "error" })
  }
}))

// `e`: PGN (positions and games), or a puzzle pack (positions, puzzles and games)
handle("library.export", libraryTarget(async (t, st) => {
  if (["positions", "puzzles", "games"].includes(st.c)) {
    const kind = await openMenu({
      title: tr("Export"), anchor: t.el,
      items: [{ label: "PGN", note: tr("for any chess program"), key: "p", keys: ["p"], value: "pgn" },
              { label: tr("Puzzle pack"), note: ":pack-export <title> [for=<name>]", key: "k", keys: ["k"], value: "pack" }],
    })
    if (kind === "pack") return openCmdline("pack-export ")
    if (kind !== "pgn") return false
  }
  if (!["positions", "games"].includes(st.c)) return status(tr("Positions and games export as PGN"), { kind: "error" }) || false
  const all = !targetRows(t.el.querySelector("[data-library-results]")).selected
  const link = document.createElement("a")
  link.href = `/lib/export/?${params(all ? { ids: [] } : t, st)}`
  link.download = ""
  document.body.append(link)
  link.click()
  link.remove()
  status(all ? tr("Exporting everything the query found") : tr("Exporting {n}", { n: t.ids.length }), { timeout: 2500 })
}))

// `:pack-export <title> [for=<student>]`: the selection, else everything the query found
handle("pack.export", async (args) => {
  if (!args.length) return openCmdline("pack-export ")
  const el = currentLibrary()
  if (!el) return status(tr("Packs are made in the Library: search, select, then :pack-export"), { kind: "error" }) || false
  const st = stateOf(el)
  if (!["positions", "puzzles", "games"].includes(st.c)) return status(tr("Packs hold positions and games: collection 1, 2 or 3"), { kind: "error" }) || false
  const rows = targetRows(el.querySelector("[data-library-results]"))
  status(tr("Making the pack…"), { timeout: 0 })
  const result = await serverRun("pack.export", args, { c: st.c, ids: rows.selected ? rows.ids : [], q: st.q })
  if (result) status(result.message, { kind: "good", timeout: 8000 })
})

// Analyse: `t` tags the move, `T` the position (through :tag, with the tag's completion).
const moveName = () => window.SPOS.analysis?.current()?.nodes.get(window.SPOS.analysis.current().cursor)?.san || ""

handle("analysis.tags", () => {
  const t = target({ moves: true })
  if (!t) return status(tr("Go to a move first (T tags the position)"), { kind: "error" }) || false
  return pickTags(t, tr("Tags of the move {move}", { move: moveName() }))
})
handle("analysis.untag", ([tag]) => {
  const t = target({ moves: true })
  if (!t) return status(tr("Go to a move first (T tags the position)"), { kind: "error" }) || false
  if (!tag) return pickTags(t, tr("Tags of the move {move}", { move: moveName() }))
  return bulk("library.untag", [tag], t)
})
handle("analysis.positiontags", () => {
  // in Analyse the position; in a Library pane its selection
  const t = target()
  return pickTags(t, focusedLibrary() ? selectionTitle(t || { ids: [] }) : tr("Tags of the position"))
})
handle("train.tag", () => pickTags(target(), tr("Tags of the position")))

Object.assign((window.SPOS ||= {}), {
  library: {
    toggleTerm,
    removeSpan,
    setQuery,
    openRow: (row) => {
      const el = row.closest("[data-island='library']")
      return el ? openRow(el, row, { list: liveList(el, row) }) : false
    },
    pendingMoveTags: false,
    hasTarget: () => Boolean(target()),
    state: () => {
      const el = currentLibrary()
      return el ? { ...stateOf(el) } : null
    },
  },
})
