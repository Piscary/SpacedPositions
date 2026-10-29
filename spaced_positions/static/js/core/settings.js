// The Settings mode and the keymap editor (spec 04 · Settings, 07 §5). Settings: themes preview live while the
// cursor is on them (↵ keeps one), h/l step a value, ↵ edits it on the command line, ⌫ resets it, / searches.
// Keymap: ↵ on a command records new keys (↵ keeps them, Esc cancels), ⌫ removes the binding.

import { handle, pushUndo, run, serverRun } from "./commands.js"
import { ctx, displayKey, emit, on, setLayer, status } from "./context.js"
import { setOverlayHandler } from "./keys.js"
import { focusPane } from "./layout.js"
import { cursorIndex, resetList, targetRows } from "./lists.js"
import { openCmdline } from "./cmdline.js"
import { inverse } from "./library.js"
import { tr } from "./i18n.js"

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""
const settingsPanes = () => [...document.querySelectorAll("[data-island='settings']")]
const keymapPanes = () => [...document.querySelectorAll("[data-island='keymap']")]

// The cursor stays on its row when the rows come back (after every change) and across a reload of the page (a new
// language reloads it): the row and the search text are kept in sessionStorage per pane kind.
const remembered = (kind) => {
  try { return JSON.parse(sessionStorage.getItem(`spos.${kind}`) || "{}") } catch { return {} }
}
const remember = (kind, state) => {
  try { sessionStorage.setItem(`spos.${kind}`, JSON.stringify({ ...remembered(kind), ...state })) } catch { /* not kept: fine */ }
}
const kindOf = (el) => (el.matches("[data-island='keymap']") ? "keymap" : "settings")

async function load(el, url, box, list) {
  const html = await fetch(url).then((r) => r.text()).catch(() => null)
  if (html === null) return
  const target = el.querySelector(box)
  const old = target.querySelector(list)
  const keep = old?.querySelector("[data-row].is-cursor")?.dataset.row ?? remembered(kindOf(el)).row
  const index = old ? Math.max(0, cursorIndex(old)) : 0
  target.innerHTML = html
  window.htmx?.process(target)
  filter(el) // first: the cursor counts the rows that are shown
  const fresh = target.querySelector(list)
  if (!fresh) return
  const rows = [...fresh.querySelectorAll("[data-row]")].filter((r) => !r.closest("[hidden]"))
  const at = keep ? rows.findIndex((r) => r.dataset.row === keep) : -1
  resetList(fresh, { index: at >= 0 ? at : index })
  rows[at]?.scrollIntoView({ block: "nearest" })
}

const loadSettings = (el) => load(el, "/settings/rows/", "[data-settings-rows]", "[data-settings-list]")
const loadKeymap = (el) => load(el, "/settings/keymap/", "[data-keymap-rows]", "[data-keymap-list]")

function mountSearch(el, selector) {
  const field = el.querySelector(selector)
  field.value = remembered(kindOf(el)).search || ""
  field.addEventListener("input", () => {
    remember(kindOf(el), { search: field.value })
    filter(el)
  })
}

export function mountSettings(el) {
  mountSearch(el, "[data-settings-filter]")
  loadSettings(el)
}

export function mountKeymap(el) {
  mountSearch(el, "[data-keymap-filter]")
  loadKeymap(el)
}

/** Rows that don't contain the search text (or their group's name) are hidden, and sections and groups without rows. */
function filter(el) {
  const text = (el.querySelector("[data-search]")?.value || "").trim().toLowerCase()
  for (const row of el.querySelectorAll("[data-row]")) {
    row.hidden = Boolean(text) && !`${row.dataset.group || ""} ${row.textContent}`.toLowerCase().includes(text)
  }
  for (const section of el.querySelectorAll("[data-section]")) {
    section.hidden = Boolean(text) && ![...section.querySelectorAll("[data-row]")].some((r) => !r.hidden)
  }
  for (const head of el.querySelectorAll("[data-group-head]")) {
    head.hidden = Boolean(text) && ![...el.querySelectorAll("[data-row]")].some((r) => !r.hidden && r.dataset.group === head.dataset.groupHead)
  }
}

on("effects", (effects) => {
  if (effects.theme || effects.settings || effects.themes || effects.storage) settingsPanes().forEach(loadSettings)
  if (effects.registry) {
    keymapPanes().forEach(loadKeymap)
    settingsPanes().forEach(loadSettings)
  }
})

// ── Live theme preview ────────────────────────────────────────────────────────────────────────────────────────

let original = null // the theme CSS before a preview

function preview(name) {
  const style = document.getElementById("theme")
  const themes = window.SPOS.themes.themes
  if (original === null) original = style.textContent
  if (name === "auto" || !themes[name]) return restore()
  style.textContent = `:root {${Object.entries(themes[name].css).map(([k, v]) => `${k}: ${v};`).join(" ")}}`
}

function restore() {
  if (original !== null) document.getElementById("theme").textContent = original
  original = null
}

on("list:cursor", ({ row }) => {
  const island = row.closest("[data-island='settings'], [data-island='keymap']")
  if (island) remember(kindOf(island), { row: row.dataset.row })
  if (!row.closest("[data-island='settings']")) return
  if (row.dataset.theme) preview(row.dataset.theme)
  else restore()
})
on("theme", () => { original = null }) // a theme was chosen: that is the theme now
on("mode", () => restore())
on("focus", ({ pane }) => { if (!pane?.el?.querySelector("[data-island='settings']")) restore() })

// ── Commands ──────────────────────────────────────────────────────────────────────────────────────────────────

function currentRow(kind) {
  const list = ctx.pane?.el?.querySelector(kind)
  if (!list) return null
  const [id] = targetRows(list).ids
  return id ? list.querySelector(`[data-row="${CSS.escape(id)}"]`) : null
}

function stepped(row, direction) {
  const { type, value, values, low, high } = row.dataset
  const step = direction === "prev" ? -1 : 1
  if (type === "bool") return value === "on" ? "off" : "on"
  if (type === "enum") {
    const options = values.split(",")
    return options[(options.indexOf(value) + step + options.length) % options.length]
  }
  if (type === "int" || type === "px" || type === "ms" || type === "number") {
    const n = Number.parseFloat(value)
    if (Number.isNaN(n)) return null
    const size = type === "number" ? (Math.abs(n) < 2 ? 0.05 : 0.5) : type === "ms" ? 25 : 1
    let next = Math.round((n + step * size) * 100) / 100
    if (low !== undefined && low !== "None") next = Math.max(Number(low), next)
    if (high !== undefined && high !== "None") next = Math.min(Number(high), next)
    return String(next) // the number alone: the unit (px, ms) is the setting's, not the value's
  }
  return null
}

handle("settings.step", ([direction]) => {
  const row = currentRow("[data-settings-list]")
  if (!row?.dataset.set) return false
  const value = stepped(row, direction)
  if (value === null) return status(tr("↵ edits this one on the command line"), { timeout: 2000 }) || false
  row.dataset.value = value // the next step starts here, before the rows come back
  return run("pref.set", [`${row.dataset.set}=${value}`])
})

handle("settings.edit", () => {
  const row = currentRow("[data-settings-list]")
  if (row?.dataset.theme) return run("theme.set", [row.dataset.theme])
  if (!row?.dataset.set) return false
  // a choice: the list of choices (the current one marked) to pick from; a number or a text: the value to change
  const choice = ["enum", "bool"].includes(row.dataset.type)
  return openCmdline(`set ${row.dataset.set}=${choice || row.dataset.value === "—" ? "" : row.dataset.value}`)
})

handle("settings.reset", () => {
  const row = currentRow("[data-settings-list]")
  if (!row?.dataset.set) return false
  if (!row.classList.contains("is-changed")) return status(tr("Already the default"), { timeout: 1500 }) || false
  return run("pref.reset", [row.dataset.set])
})

handle("settings.keymap", async () => {
  const pane = document.querySelector(".workspace:not([hidden]) [data-view='keymap']")
  if (pane) return focusPane(pane.dataset.pane)
  return run("pane.split.vertical", ["keymap"])
})

handle("settings.export", () => {
  const link = Object.assign(document.createElement("a"), { href: "/settings/export/", download: "" })
  document.body.append(link)
  link.click()
  link.remove()
  status(tr("Settings exported as TOML: Settings → Data imports them on another machine"), { timeout: 4000 })
})

/** Settings → Data: pasted settings or a theme (TOML), with ⌘↵. */
export async function importSettings(text) {
  const response = await fetch("/settings/import/", {
    method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify({ text }),
  }).catch(() => null)
  const data = response ? await response.json().catch(() => null) : null
  if (!data) return status(tr("Import: the app is not reachable"), { kind: "error" })
  status(data.message, { kind: data.ok ? "good" : "error", timeout: 8000 })
  if (data.ok && data.effects) emit("effects", data.effects)
}

// ── Keymap editor ─────────────────────────────────────────────────────────────────────────────────────────────

handle("keymap.bind", () => {
  const row = currentRow("[data-keymap-list]")
  if (!row) return false
  const command = row.dataset.command
  const keys = []
  const show = () => status(tr("New keys for “{command}”: {keys} · ↵ keep · Esc cancel", { command: row.dataset.title, keys: keys.map((k) => displayKey(k)).join(" ") || "…" }), { timeout: 0 })
  show()
  ctx.overlay = "record"
  setOverlayHandler((e, token) => {
    if (token === "esc") {
      finish()
      return status(tr("Cancelled"), { timeout: 1500 })
    }
    if (token === "enter" && keys.length) {
      finish()
      return bind([...keys, command])
    }
    if (keys.length < 3) keys.push(token)
    show()
  })
  function finish() {
    ctx.overlay = null
    setOverlayHandler(null)
    setLayer("normal")
  }
})

async function bind(args) {
  const result = await serverRun("key.map", args)
  if (!result) return false
  status(result.message, { kind: "good", keys: { seq: ["u"], label: tr("undo") } })
  if (result.undo) pushUndo(inverse(result))
}

handle("keymap.unbind", async () => {
  const row = currentRow("[data-keymap-list]")
  const binding = row?.querySelector(".keymap__binding.is-mine") || row?.querySelector(".keymap__binding")
  if (!binding) return status(tr("No keys to remove here"), { timeout: 1500 }) || false
  const where = binding.dataset.context === "global" ? [] : [`@${binding.dataset.context}`]
  const id = binding.classList.contains("is-mine") ? "key.reset" : "key.unmap"
  const result = await serverRun(id, [...where, ...binding.dataset.keys.split(" ")])
  if (!result) return false
  status(result.message, { kind: "good" })
  if (result.undo) pushUndo(inverse(result))
})

