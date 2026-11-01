// The pane menu (spec 03 §5): `⋯` in a pane's header, a right click on the header, or ␣ w w. It lists what the pane's
// view can do (core/layouts.py VIEW_MENUS) and what can be done with the pane itself, each with its keys, so the
// whole app works with the mouse and the menu teaches the keys. j k / ↑ ↓, ↵, Esc, or the mouse.

import { command, enabled, handle, primaryKeys, run } from "./commands.js"
import { ctx, lookup } from "./context.js"
import { focusPane } from "./layout.js"
import { cursorOn } from "./lists.js"
import { chosenBy, openMenu } from "./menu.js"
import { tr } from "./i18n.js"

const PANE = [
  ["pane.split.vertical"], ["pane.split.horizontal"], ["pane.view"], ["pane.maximize"], ["pane.collapse"], ["pane.group"],
  ["pane.pin"], ["pane.swap"], ["pane.rotate"], ["pane.equalize"], ["pane.only"], ["pane.buffers"], ["pane.close"],
]

// menu entries that belong to some rows only: Edit and Delete to players, sources and tags (typed, `:edit p529 …`
// works everywhere)
const ONLY = { "library.edit": "library.vocabulary", "library.delete": "library.vocabulary" }

// the whole window: layouts, and what a mouse user needs to get back from Zen (the pane headers stay)
const SCREEN = ["layout.menu", "ui.zen", "ui.appbar", "ui.keystrips", "ui.themepair", "help.all"]

function item(cid, args = [], label = "") {
  const state = enabled(cid)
  return {
    label: label || command(cid)?.title || cid,
    keys: primaryKeys(cid, args.length ? args : undefined) || undefined,
    note: state.ok ? "" : state.reason,
    disabled: !state.ok,
    value: { cid, args },
  }
}

async function openPaneMenu(paneEl, anchor, { viewOnly = false } = {}) {
  if (!paneEl) return false
  if (ctx.pane?.el !== paneEl) focusPane(paneEl.dataset.pane) // the commands act on the focused pane
  const view = window.SPOS.views[paneEl.dataset.view]
  const items = []
  if (view?.menu?.length) {
    items.push({ heading: view.label })
    for (const entry of view.menu) {
      if (ONLY[entry.cmd] && !lookup(ONLY[entry.cmd])) continue
      const one = item(entry.cmd, entry.args, entry.label)
      if (!(viewOnly && one.disabled)) items.push(one) // a right click: only what can be done here
    }
  }
  if (!viewOnly || !items.length) {
    items.push({ heading: tr("Pane") }, ...PANE.map(([cid]) => item(cid)))
    items.push({ heading: tr("Screen") }, ...SCREEN.map((cid) => item(cid)))
  }
  const chosen = await openMenu({ items, anchor })
  // chosen by a click: as a click, the status line shows its key; by a key: as a key
  if (chosen) run(chosen.cid, chosen.args, { source: chosenBy })
  return true
}

handle("pane.menu", () => {
  const paneEl = ctx.pane?.el
  return openPaneMenu(paneEl, paneEl?.querySelector(".pane__menu") || paneEl?.querySelector("[data-pane-header]"))
})

// A right click on a pane's header opens its menu where the pointer is; on a row of a list or a move, what can be
// done with that row or move (the view's part of the menu), the cursor on it first.
document.addEventListener("contextmenu", (e) => {
  if (e.target.closest("input, textarea, select")) return
  const header = e.target.closest("[data-pane-header]")
  const row = !header && e.target.closest("[data-pane] [data-list] [data-row]")
  const move = !header && !row && e.target.closest("[data-pane] [data-node]")
  if (!header && !row && !move) return
  e.preventDefault()
  if (row) cursorOn(row)
  if (move) move.click()
  openPaneMenu(e.target.closest("[data-pane]"), { x: e.clientX, y: e.clientY }, { viewOnly: !header })
})
