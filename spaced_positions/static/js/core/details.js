// The Details pane (spec 16): every field of the game, position, player or source its link group shows (the
// Library row under the cursor, the open analysis), as list rows. ↵ edits a field on the command line (`:edit`,
// so every change has its undo), ⌫ empties it; `I` brings the pane, `␣ n p` / `␣ n s` make a player or a source
// and show it here.

import { handle, run } from "./commands.js"
import { ctx, newest, on } from "./context.js"
import { focusPane, nodeOf } from "./layout.js"
import { openCmdline } from "./cmdline.js"
import { treeOf } from "./analysis.js"
import { resetList } from "./lists.js"

const loads = newest()
const EDITABLE = /^([pgs]\d+|@.+|[0-9a-f-]{36})$/ // a position, game, source, player, or an analysis's uuid
const panes = () => [...document.querySelectorAll(".workspace [data-island='details']")]
let pending = null // what `I` asked for, for a pane that is still being made

function groupKey(el) {
  const pane = el.closest("[data-pane]")
  const node = nodeOf(pane)
  return `${pane.closest(".workspace").dataset.mode}:${node?.group && !node.pinned ? node.group : node?.id}`
}

/** Show a thing (`g12`, `p529`, `@tal`, `s3`, a uuid) in a Details pane; `force`: again, after a change. */
async function show(el, ref, { force = false } = {}) {
  if (!ref || !EDITABLE.test(ref) || (!force && el.dataset.ref === ref)) return
  el.dataset.ref = ref
  const current = loads(el)
  const keep = el.querySelector("[data-row].is-cursor")?.dataset.row
  const html = await fetch(`/lib/details/?ref=${encodeURIComponent(ref)}`).then((r) => (r.ok ? r.text() : null)).catch(() => null)
  if (html === null || !current()) return
  el.innerHTML = html
  const list = el.querySelector("[data-list]")
  if (list) resetList(list, { index: Math.max(0, [...list.querySelectorAll("[data-row]")].findIndex((r) => r.dataset.row === keep)) })
}

export function mountDetails(el) {
  const t = treeOf(groupKey(el))
  show(el, pending || t?.position.id)
  pending = null
}

// The group's subject: a Library row under the cursor, the open analysis.
on("cursor", ({ group, id }) => {
  for (const el of panes()) {
    const node = nodeOf(el.closest("[data-pane]"))
    if (el.closest(".workspace").dataset.mode === ctx.mode && node?.group === group) show(el, id)
  }
})
on("analysis:cursor", ({ key }) => {
  for (const el of panes()) if (groupKey(el) === key) show(el, treeOf(key)?.position.id)
})
// After a change: the pane shows the new values; a player or source just made is shown.
on("effects", (effects) => {
  for (const el of panes()) {
    if (effects.details) show(el, effects.details, { force: true })
    else if (effects.library) show(el, el.dataset.ref, { force: true })
  }
})

function cursorRow() {
  const list = ctx.pane?.el?.querySelector("[data-details-list]")
  return list ? [list.dataset.ref, list.querySelector("[data-row].is-cursor")] : [null, null]
}

handle("details.edit", () => {
  const [ref, row] = cursorRow()
  if (!row) return false
  const raw = (row.dataset.raw || "").replace(/"/g, "'")
  const start = `edit ${ref} ${row.dataset.row}="`
  openCmdline(`${start}${raw}"`)
  document.querySelector(".cmdline__input")?.setSelectionRange(start.length, start.length + raw.length) // typing replaces it
})

handle("details.clear", () => {
  const [ref, row] = cursorRow()
  if (!row) return false
  return run("library.edit", [ref, `${row.dataset.row}=`])
})

/** What is selected where the keys are: a Library row, else the analysis of this pane's group. */
function selected() {
  const row = ctx.pane?.el?.querySelector("[data-list] [data-row].is-cursor")
  if (row && EDITABLE.test(row.dataset.row)) return row.dataset.row
  return window.SPOS.analysis?.current?.()?.position.id || null
}

handle("library.details", async () => {
  const ref = selected()
  const here = document.querySelector(`#ws-${ctx.mode} [data-island='details']`)
  if (here) {
    show(here, ref)
    return focusPane(here.closest("[data-pane]").dataset.pane)
  }
  pending = ref
  return run("pane.split.vertical", ["details"])
})
