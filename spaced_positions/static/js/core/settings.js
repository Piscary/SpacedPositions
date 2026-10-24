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
import { offer } from "./confirm.js"

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""
const settingsPanes = () => [...document.querySelectorAll("[data-island='settings']")]
const keymapPanes = () => [...document.querySelectorAll("[data-island='keymap']")]

async function load(el, url, box, list) {
  const html = await fetch(url).then((r) => r.text()).catch(() => null)
  if (html === null) return
  const target = el.querySelector(box)
  const old = target.querySelector(list)
  const index = old ? Math.max(0, cursorIndex(old)) : 0
  target.innerHTML = html
  window.htmx?.process(target)
  const fresh = target.querySelector(list)
  if (fresh) resetList(fresh, { index })
  filter(el)
}

const loadSettings = (el) => load(el, "/settings/rows/", "[data-settings-rows]", "[data-settings-list]")
const loadKeymap = (el) => load(el, "/settings/keymap/", "[data-keymap-rows]", "[data-keymap-list]")

export function mountSettings(el) {
  loadSettings(el)
  el.querySelector("[data-settings-filter]").addEventListener("input", () => filter(el))
}

export function mountKeymap(el) {
  loadKeymap(el)
  el.querySelector("[data-keymap-filter]").addEventListener("input", () => filter(el))
}

/** Rows that don't contain the search text are hidden, and sections without rows. */
function filter(el) {
  const text = (el.querySelector("[data-search]")?.value || "").trim().toLowerCase()
  for (const row of el.querySelectorAll("[data-row]")) row.hidden = Boolean(text) && !row.textContent.toLowerCase().includes(text)
  for (const section of el.querySelectorAll("[data-section]")) {
    section.hidden = Boolean(text) && ![...section.querySelectorAll("[data-row]")].some((r) => !r.hidden)
  }
}

on("effects", (effects) => {
  if (effects.theme || effects.settings || effects.themes) settingsPanes().forEach(loadSettings)
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
    return type === "px" ? `${next}px` : type === "ms" ? `${next}ms` : String(next)
  }
  return null
}

handle("settings.step", ([direction]) => {
  const row = currentRow("[data-settings-list]")
  if (!row?.dataset.set) return false
  const value = stepped(row, direction)
  if (value === null) return status("↵ edits this one on the command line", { timeout: 2000 }) || false
  row.dataset.value = value // the next step starts here, before the rows come back
  return run("pref.set", [`${row.dataset.set}=${value}`])
})

handle("settings.edit", () => {
  const row = currentRow("[data-settings-list]")
  if (row?.dataset.theme) return run("theme.set", [row.dataset.theme])
  if (!row?.dataset.set) return false
  return openCmdline(`set ${row.dataset.set}=${row.dataset.value === "—" ? "" : row.dataset.value}`)
})

handle("settings.reset", () => {
  const row = currentRow("[data-settings-list]")
  if (!row?.dataset.set) return false
  if (!row.classList.contains("is-changed")) return status("Already the default", { timeout: 1500 }) || false
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
  status("Settings exported as TOML: Settings → Data imports them on another machine", { timeout: 4000 })
})

/** Settings → Data: pasted settings or a theme (TOML), with ⌘↵. */
export async function importSettings(text) {
  const response = await fetch("/settings/import/", {
    method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify({ text }),
  }).catch(() => null)
  const data = response ? await response.json().catch(() => null) : null
  if (!data) return status("Import: the app is not reachable", { kind: "error" })
  status(data.message, { kind: data.ok ? "good" : "error", timeout: 8000 })
  if (data.ok && data.effects) emit("effects", data.effects)
}

/** Settings → Data: the migration from chess-study-manager. First what it would add, then `y` imports it. */
export async function importCsm(path, dryRun = true) {
  status(dryRun ? "Reading the old database…" : "Importing (after a backup)…", { timeout: 0 })
  const response = await fetch("/settings/csm/", {
    method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify({ path, dry_run: dryRun }),
  }).catch(() => null)
  const data = response ? await response.json().catch(() => null) : null
  if (!data) return status("Import: the app is not reachable", { kind: "error" })
  if (!data.ok) return status(data.message, { kind: "error", timeout: 8000 })
  const problems = data.problems.length ? ` · ${data.problems.length} left out: ${data.problems[0]}` : ""
  if (dryRun && data.new) return offer(`${data.message}${problems} · import it? y / n`, { y: () => importCsm(path, false) })
  status(`${data.message}${problems}`, { kind: "good", timeout: 0 })
  if (data.effects) emit("effects", data.effects)
}

// ── Keymap editor ─────────────────────────────────────────────────────────────────────────────────────────────

handle("keymap.bind", () => {
  const row = currentRow("[data-keymap-list]")
  if (!row) return false
  const command = row.dataset.command
  const keys = []
  const show = () => status(`New keys for “${row.dataset.title}”: ${keys.map((k) => displayKey(k)).join(" ") || "…"} · ↵ keep · Esc cancel`, { timeout: 0 })
  show()
  ctx.overlay = "record"
  setOverlayHandler((e, token) => {
    if (token === "esc") {
      finish()
      return status("Cancelled", { timeout: 1500 })
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
  status(result.message, { kind: "good", keys: { seq: ["u"], label: "undo" } })
  if (result.undo) pushUndo(inverse(result))
}

handle("keymap.unbind", async () => {
  const row = currentRow("[data-keymap-list]")
  const binding = row?.querySelector(".keymap__binding.is-mine") || row?.querySelector(".keymap__binding")
  if (!binding) return status("No keys to remove here", { timeout: 1500 }) || false
  const where = binding.dataset.context === "global" ? [] : [`@${binding.dataset.context}`]
  const id = binding.classList.contains("is-mine") ? "key.reset" : "key.unmap"
  const result = await serverRun(id, [...where, ...binding.dataset.keys.split(" ")])
  if (!result) return false
  status(result.message, { kind: "good" })
  if (result.undo) pushUndo(inverse(result))
})

