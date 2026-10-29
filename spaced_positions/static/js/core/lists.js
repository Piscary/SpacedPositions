// Generic behaviour of List views and Sections (spec 05 · E, 03 §5), plus link-group following (spec 03 §4).
// A list is [data-list] with rows [data-row]; its cursor and selection live on the element.

import { addDynamicPrefix } from "./keys.js"
import { handle, run } from "./commands.js"
import { ctx, emit, on, setLayer, status, updateStatus } from "./context.js"

const state = new WeakMap() // list element → {cursor, selected:Set, anchor}

function focusedList() {
  return ctx.pane?.el?.querySelector("[data-list]") || null
}

function listState(list) {
  if (!state.has(list)) state.set(list, { cursor: -1, selected: new Set(), anchor: null })
  return state.get(list)
}

// folded (a collapsed section) or filtered out: skipped
const rowsOf = (list) => [...list.querySelectorAll("[data-row]")].filter((row) => !row.closest("[hidden], .is-collapsed > .section__body"))

function paint(list) {
  const st = listState(list)
  for (const row of list.querySelectorAll("[data-row].is-cursor")) row.classList.remove("is-cursor") // also on hidden rows
  rowsOf(list).forEach((row, i) => {
    const selected = st.selected.has(row.dataset.row)
    row.classList.toggle("is-cursor", i === st.cursor)
    row.classList.toggle("is-selected", selected)
    row.setAttribute("aria-selected", String(selected))
    const mark = row.querySelector(".list__mark")
    if (mark) mark.textContent = selected ? "▣" : "▢"
  })
  syncSelection(list)
}

function syncSelection(list) {
  const st = listState(list)
  ctx.selection = { count: st.selected.size, visual: st.anchor !== null }
  emit("selection", { list, count: st.selected.size })
  const row = rowsOf(list)[st.cursor]
  if (ctx.pane) ctx.pane.subject = row ? `${row.dataset.row} ${row.dataset.title || ""}`.trim() : ""
  updateStatus()
}

function moveTo(list, index) {
  const rows = rowsOf(list)
  if (!rows.length) return false
  const st = listState(list)
  st.cursor = Math.max(0, Math.min(rows.length - 1, index))
  if (st.anchor !== null) {
    const [a, b] = [Math.min(st.anchor, st.cursor), Math.max(st.anchor, st.cursor)]
    st.selected = new Set(st.visualBase)
    rows.slice(a, b + 1).forEach((r) => st.selected.add(r.dataset.row))
  }
  paint(list)
  rows[st.cursor].scrollIntoView({ block: "nearest" })
  const row = rows[st.cursor]
  emit("list:cursor", { list, row })
  if (ctx.pane?.group) {
    emit("cursor", { group: ctx.pane.group, from: ctx.pane.id, id: row.dataset.row, title: row.dataset.title, fen: row.dataset.fen,
                     position: row.dataset.position || row.dataset.game || null })
  }
}

/** The rows a bulk command acts on: the selected ones, else the row under the cursor. */
export function targetRows(list) {
  const st = listState(list)
  const rows = rowsOf(list)
  if (st.selected.size) return { ids: [...st.selected], selected: true }
  const row = rows[Math.max(0, st.cursor)]
  return { ids: row ? [row.dataset.row] : [], selected: false }
}

/** After a list's rows were replaced: cursor back to `index` (selection kept unless `clear`). */
export function resetList(list, { index = 0, clear = false } = {}) {
  const st = listState(list)
  if (clear) st.selected.clear()
  st.anchor = null
  st.cursor = rowsOf(list).length ? Math.min(index, rowsOf(list).length - 1) : -1
  paint(list)
}

export function cursorIndex(list) {
  return listState(list).cursor
}

const withList = (fn) => (args) => {
  const list = focusedList()
  if (!list) return false
  return fn(list, listState(list), args)
}

handle("list.down", withList((list, st) => moveTo(list, st.cursor + 1)))
handle("list.up", withList((list, st) => moveTo(list, st.cursor - 1)))
handle("list.first", withList((list) => moveTo(list, 0)))
handle("list.last", withList((list) => moveTo(list, rowsOf(list).length - 1)))

handle("list.select", withList((list, st) => {
  const row = rowsOf(list)[st.cursor]
  if (!row) return moveTo(list, 0)
  const id = row.dataset.row
  st.selected.has(id) ? st.selected.delete(id) : st.selected.add(id)
  paint(list)
}))

handle("list.visual", withList((list, st) => {
  if (st.anchor !== null) {
    st.anchor = null
    setLayer("normal")
    paint(list)
    return
  }
  if (st.cursor < 0) st.cursor = 0
  st.anchor = st.cursor
  st.visualBase = new Set(st.selected)
  setLayer("visual")
  moveTo(list, st.cursor)
}))

handle("list.selectall", withList((list, st) => {
  st.selected = new Set(rowsOf(list).map((r) => r.dataset.row))
  paint(list)
}))

handle("list.open", withList((list, st) => {
  const row = rowsOf(list)[Math.max(0, st.cursor)] // no cursor yet: the first row
  if (!row) return false
  row.classList.remove("is-flash-row")
  void row.offsetWidth
  row.classList.add("is-flash-row")
  if (row.dataset.term) return window.SPOS.library.toggleTerm(row.dataset.term, row) // a facet of the filter pane
  if (row.dataset.span) return window.SPOS.library.removeSpan(row.dataset.span, row) // a term of the search: out
  if (row.hasAttribute("data-clear")) return run("library.clear")
  if (row.dataset.query) return window.SPOS.library.setQuery(row.dataset.query, row.dataset.queryCollection) // a player, source or tag
  // a row of the Library's results: opened right here when this mode shows its group's analysis, else in Analyse
  if ((row.dataset.game || row.dataset.position) && list.matches("[data-library-results]")) return window.SPOS.library.openRow(row)
  if (row.dataset.game) return window.SPOS.analysis.openGame?.(row.dataset.game)
  if (row.dataset.position) {
    // Positions open in Analyse; n / N there step through the rest of the list.
    const rows = rowsOf(list).filter((r) => r.dataset.position)
    const ids = rows.map((r) => r.dataset.position)
    return window.SPOS.analysis.open(row.dataset.position, { node: Number(row.dataset.node) || null, list: { ids, index: rows.indexOf(row) } })
  }
  status(`Open ${row.dataset.row} ${row.dataset.title}: a demo row, nothing to open`, { timeout: 3000 })
}))

/** Esc steps: leave visual, then clear the selection. Returns true if it did something. */
export function escapeSelection() {
  const list = focusedList()
  if (!list) return false
  const st = listState(list)
  if (st.anchor !== null) {
    st.anchor = null
    setLayer("normal")
    paint(list)
    return true
  }
  if (st.selected.size) {
    st.selected.clear()
    paint(list)
    return true
  }
  return false
}

// Mouse: click moves the cursor, double click opens.
// A click puts the cursor on the row, also a click on one of its buttons (a setting's choice): the cursor is where
// you just worked, and stays there when the rows come back.
document.addEventListener("click", (e) => {
  const row = e.target.closest("[data-list] [data-row]")
  if (!row) return
  const list = row.closest("[data-list]")
  const index = rowsOf(list).indexOf(row)
  if (index !== listState(list).cursor) moveTo(list, index)
}, true)
document.addEventListener("dblclick", (e) => {
  if (e.target.closest("[data-list] [data-row]")) run("list.open", [], { source: "mouse" })
})

on("focus", () => {
  const list = focusedList()
  if (list) syncSelection(list)
  else {
    ctx.selection = { count: 0 }
    updateStatus()
  }
})

// ── Sections: z / Z, ] / [, click on a header, g + letter ───────────────────────────────────────────────────────
// One rule in every pane, so it becomes muscle memory: ] and [ (and g + a section's letter) go to the next /
// previous section, unfold it and put the pane's cursor on its first item (a list's first row, the Stats pane's
// first chart); j / k go on from there. [ inside a section goes to its first item before the section above. The
// section of the cursor is the current one. A list's groups (the Library sorted by source, the filter facets, the
// keymap) are sections too.

const sectionCursor = new WeakMap() // pane element → section element: where the cursor (or the last jump) is

function setSectionCursor(section) {
  const pane = section.closest("[data-pane]")
  if (!pane) return
  pane.querySelectorAll("[data-section].is-cursor").forEach((s) => s.classList.remove("is-cursor"))
  section.classList.add("is-cursor")
  sectionCursor.set(pane, section)
}

/** The cursor moved to `item` (a row, a chart): its section becomes the current one. The item shows the cursor,
 *  so no section header is highlighted meanwhile. */
export function noteSection(item) {
  const section = item?.closest("[data-section]")
  const pane = section?.closest("[data-pane]")
  if (!pane) return
  pane.querySelectorAll("[data-section].is-cursor").forEach((s) => s.classList.remove("is-cursor"))
  sectionCursor.set(pane, section)
}
on("list:cursor", ({ row }) => noteSection(row))

function currentSection() {
  const pane = ctx.pane?.el
  if (!pane) return null
  const remembered = sectionCursor.get(pane)
  if (remembered?.isConnected) return remembered
  const body = pane.querySelector(".pane__body")
  const top = body?.getBoundingClientRect().top ?? 0
  return [...pane.querySelectorAll("[data-section]")].find((s) => s.getBoundingClientRect().bottom > top) || null
}

export function setCollapsed(section, collapsed) {
  if (section.hasAttribute("data-pinned")) return
  section.classList.toggle("is-collapsed", collapsed)
  section.querySelector(".section__header")?.setAttribute("aria-expanded", String(!collapsed))
}

handle("section.toggle", () => {
  const section = currentSection()
  if (!section) return false
  setSectionCursor(section)
  setCollapsed(section, !section.classList.contains("is-collapsed"))
})

/** The heads of a list's groups: its sections. */
const GROUP_HEADS = "[data-group-head], .filters__group"
const ITEMS = "[data-list] [data-row], figure[data-chart]"
const isShown = (el) => !el.closest("[hidden]")

/** The pane's sections in order, each with its items: [{el, items}]. */
function sectionsOf(pane) {
  const sections = [...pane.querySelectorAll("[data-section]")].filter(isShown)
  if (sections.length) return sections.map((el) => ({ el, items: [...el.querySelectorAll(ITEMS)].filter(isShown) }))
  const list = pane.querySelector("[data-list]")
  const heads = list ? [...list.querySelectorAll(GROUP_HEADS)].filter(isShown) : []
  const rows = list ? rowsOf(list) : []
  const after = (a, b) => a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING
  return heads.map((el, i) => ({ el, items: rows.filter((r) => after(el, r) && (!heads[i + 1] || after(r, heads[i + 1]))) }))
}

const cursorItem = (pane) => pane.querySelector("[data-list] [data-row].is-cursor, figure[data-chart].is-focused")

function moveSection(step) {
  const pane = ctx.pane?.el
  const sections = pane ? sectionsOf(pane) : []
  if (!sections.length) return false
  const item = cursorItem(pane)
  const groups = !sections[0].el.matches("[data-section]")
  const current = groups ? sections.findIndex((s) => s.items.includes(item)) : sections.findIndex((s) => s.el === currentSection())
  const inside = current >= 0 && sections[current].items.includes(item)
  const target = step < 0 && inside && sections[current].items[0] !== item ? current : current + step
  enterSection(sections[Math.max(0, Math.min(sections.length - 1, target))])
}

/** Go into a section: unfolded, in view, the cursor on its first item. */
function enterSection({ el, items }) {
  if (el.matches("[data-section]")) {
    setCollapsed(el, false)
    setSectionCursor(el)
  }
  el.scrollIntoView({ block: "start" })
  const first = items[0]
  if (first?.matches("[data-row]")) { // the row shows the cursor (noteSection)
    const list = first.closest("[data-list]")
    moveTo(list, rowsOf(list).indexOf(first))
  }
  emit("section:enter", { section: el, item: first || null })
}
handle("section.next", () => moveSection(1))
handle("section.prev", () => moveSection(-1))

handle("section.all", () => {
  const sections = [...(ctx.pane?.el?.querySelectorAll("[data-section]") || [])]
  const collapse = sections.some((s) => !s.classList.contains("is-collapsed"))
  sections.forEach((s) => setCollapsed(s, collapse))
})

document.addEventListener("click", (e) => {
  const header = e.target.closest("[data-section-toggle]")
  if (!header || e.target.closest("[data-cmd]")) return
  const section = header.closest("[data-section]")
  setSectionCursor(section)
  run("section.toggle", [], { source: "mouse" })
})

addDynamicPrefix((seq) => {
  if (seq.join(" ") !== "g" || !ctx.pane?.el) return []
  return [...ctx.pane.el.querySelectorAll("[data-section-key]")].map((section) => ({
    key: section.dataset.sectionKey,
    label: `Section: ${section.querySelector(".section__title")?.textContent || ""}`,
    action: () => enterSection(sectionsOf(ctx.pane.el).find((s) => s.el === section) || { el: section, items: [] }),
  }))
})

// ── Style guide helpers ────────────────────────────────────────────────────────────────────────────────────────

handle("demo.flash", () => status("Every button of this command flashed.", { kind: "good", timeout: 2000 }))

handle("search.open", () => {
  const field = ctx.pane?.el?.querySelector("[data-search]")
  if (!field) return false
  field.focus()
})

// SegmentedControl and Toggle without a command (style guide only): local state.
document.addEventListener("click", (e) => {
  const option = e.target.closest("[data-segmented] [role=radio]")
  if (option && !option.dataset.cmd) {
    option.parentElement.querySelectorAll("[role=radio]").forEach((o) => o.setAttribute("aria-checked", String(o === option)))
  }
  const toggle = e.target.closest("[data-toggle]")
  if (toggle && !toggle.dataset.cmd) toggle.setAttribute("aria-pressed", String(toggle.getAttribute("aria-pressed") !== "true"))
})
