// The pane menu (spec 03 §5): `⋯` in a pane's header, a right click on the header, or ␣ w w. It lists what the pane's
// view can do (core/layouts.py VIEW_MENUS) and what can be done with the pane itself, each with its keys, so the
// whole app works with the mouse and the menu teaches the keys. j k / ↑ ↓, ↵, Esc, or the mouse.

import { command, enabled, handle, primaryKeys, run } from "./commands.js"
import { ctx } from "./context.js"
import { focusPane } from "./layout.js"
import { openMenu } from "./menu.js"
import { tr } from "./i18n.js"

const PANE = [
  ["pane.split.vertical"], ["pane.split.horizontal"], ["pane.view"], ["pane.maximize"], ["pane.collapse"], ["pane.group"],
  ["pane.pin"], ["pane.swap"], ["pane.rotate"], ["pane.equalize"], ["pane.only"], ["pane.buffers"], ["pane.close"],
]

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

async function openPaneMenu(paneEl, anchor) {
  if (!paneEl) return false
  if (ctx.pane?.el !== paneEl) focusPane(paneEl.dataset.pane) // the commands act on the focused pane
  const view = window.SPOS.views[paneEl.dataset.view]
  const items = []
  if (view?.menu?.length) {
    items.push({ heading: view.label })
    for (const entry of view.menu) items.push(item(entry.cmd, entry.args, entry.label))
  }
  items.push({ heading: tr("Pane") }, ...PANE.map(([cid]) => item(cid)))
  const chosen = await openMenu({ items, anchor })
  if (chosen) run(chosen.cid, chosen.args, { source: "mouse" }) // as a click: the status line shows its key
  return true
}

handle("pane.menu", () => {
  const paneEl = ctx.pane?.el
  return openPaneMenu(paneEl, paneEl?.querySelector(".pane__menu") || paneEl?.querySelector("[data-pane-header]"))
})

// A right click on a pane's header opens its menu where the pointer is
document.addEventListener("contextmenu", (e) => {
  const header = e.target.closest("[data-pane-header]")
  if (!header) return
  e.preventDefault()
  openPaneMenu(header.closest("[data-pane]"), { x: e.clientX, y: e.clientY })
})
