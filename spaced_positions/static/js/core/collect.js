// Collect (spec 04 · Collect): the entry session (source, page, diagram number, title, tags, presets, ready) and
// saving the board's position, with its solution when one was played, diagram after diagram. The session survives
// reloads; a duplicate is merged or saved anyway only when asked.

import { handle } from "./commands.js"
import { ctx, on, status } from "./context.js"
import { offer } from "./confirm.js"
import { openCmdline } from "./cmdline.js"
import { focusPane, switchMode } from "./layout.js"
import * as lines from "./lines.js"

const EMPTY = "8/8/8/8/8/8/8/8 w - - 0 1"
const DEFAULT = { source: null, page: "", ref: "1", title: "", tags: [], ready: true, saved: [] }
let session = { ...DEFAULT }

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""
const post = (url, body) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(body) })
    .then(async (r) => ({ status: r.status, data: await r.json().catch(() => ({ ok: false, message: `error ${r.status}` })) }))
    .catch(() => ({ status: 0, data: { ok: false, message: "the app is not reachable" } }))

const pane = () => document.querySelector("#ws-collect [data-island='entry']")
const board = () => document.querySelector("#ws-collect [data-island='board']")?.board || null

on("workspace", ({ mode, el }) => {
  if (mode !== "collect") return
  const script = el.querySelector(":scope > script#subject-collect")
  session = { ...DEFAULT, ...(JSON.parse(script?.textContent || "{}").entry || {}) }
})

let saveTimer
function save() {
  render()
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    fetch("/state/collect/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ subject: { entry: session } }),
      keepalive: true,
    }).catch(() => {})
  }, 400)
}

/** The title of the next position: the template with {source}, {page} and {n} filled in. */
export function titleNow() {
  const template = session.title || (session.source ? "{source} Nr. {n}" : "")
  return template
    .replaceAll("{source}", session.source?.label || "")
    .replaceAll("{page}", session.page || "")
    .replaceAll("{n}", session.ref || "")
    .trim()
}

function render() {
  const el = pane()
  if (!el) return
  el.querySelector("[data-entry-source]").textContent = session.source?.label || "— none —"
  for (const field of el.querySelectorAll("[data-entry]")) {
    if (document.activeElement !== field) field.value = session[field.dataset.entry] ?? ""
  }
  el.querySelector("[data-entry-title-now]").textContent = titleNow() || "(none)"
  const tags = el.querySelector("[data-entry-tags]")
  tags.replaceChildren(...session.tags.map((t) => Object.assign(document.createElement("span"), { className: "chip chip--tag", textContent: t.name })))
  if (!session.tags.length) tags.append(Object.assign(document.createElement("span"), { className: "muted", textContent: "none · t adds one, ⌫ removes the last" }))
  for (const button of el.querySelectorAll("[data-cmd='collect.preset']")) {
    const keys = (button.dataset.keys || "").split(",").filter(Boolean)
    button.setAttribute("aria-pressed", String(keys.length > 0 && keys.every((k) => session.tags.some((t) => t.key === k))))
  }
  el.querySelector("[data-entry-ready]").setAttribute("aria-pressed", String(session.ready))
  const list = el.querySelector("[data-entry-saved]")
  list.replaceChildren(...session.saved.map((p) => {
    const row = document.createElement("div")
    row.className = "list__row"
    row.setAttribute("role", "option")
    row.dataset.row = p.short
    row.dataset.position = p.id
    row.dataset.title = p.title
    row.append(
      Object.assign(document.createElement("span"), { className: "list__id", textContent: p.short }),
      Object.assign(document.createElement("span"), { className: "list__title", textContent: p.title || "(no title)" }),
      Object.assign(document.createElement("span"), { className: "list__meta", textContent: p.note || "" }),
    )
    return row
  }))
}

export function mountEntry(el) {
  render()
  el.addEventListener("input", (e) => {
    const name = e.target.dataset?.entry
    if (!name) return
    session[name] = e.target.value
    save()
  })
  showDuplicate()
}

// ── The board's position ──────────────────────────────────────────────────────────────────────────────────────

function boardPosition(b) {
  if (b.layer === "setup") return { start: b.fullFen(), moves: [], diagram: Boolean(b.setup.diagram) }
  const line = b.line
  return { start: line.start, moves: line.moves.map((m) => m.uci), diagram: !b.chess && line.ply === 0 }
}

function showDuplicate() {
  const el = pane()
  const dup = board()?.duplicate
  if (!el) return
  el.querySelector("[data-entry-state]").textContent = dup ? `This position: duplicate of ${dup.short} ${dup.title} · g d go there` : "This position: new"
  el.querySelector("[data-entry-state]").classList.toggle("is-duplicate", Boolean(dup))
}
on("duplicate", showDuplicate)

async function saveBoard({ open = false, how = null } = {}) {
  const b = board()
  if (!b) return status("Collect needs a board pane", { kind: "error" }) || false
  const position = boardPosition(b)
  if (position.start.startsWith(EMPTY.split(" ")[0])) return status("The board is empty: set up the diagram first", { kind: "error" }) || false
  const body = {
    ...position, how, title: titleNow(), source: session.source?.id || null, page: session.page, ref: session.ref,
    tags: session.tags.map((t) => t.key), ready: session.ready,
  }
  const { data } = await post("/lib/collect/save/", body)
  if (data.duplicate) {
    return offer(`Duplicate of ${data.duplicate.short} ${data.duplicate.title}: m merge into it · s save anyway · g go there · Esc cancel`, {
      m: () => saveBoard({ open, how: "merge" }),
      s: () => saveBoard({ open, how: "new" }),
      g: () => window.SPOS.analysis.open(data.duplicate.id),
    })
  }
  if (!data.ok) return status(data.message, { kind: "error" }) || false
  session.saved = [{ ...data.position, note: data.message.split(" · ").slice(1).join(" · ") }, ...session.saved].slice(0, 12)
  if (/^\d+$/.test(session.ref)) session.ref = String(Number(session.ref) + 1)
  save()
  status(`${data.message}${open ? "" : " · next: diagram " + session.ref}`, { kind: "good", timeout: 4000 })
  if (open) return window.SPOS.analysis.open(data.position.id)
  lines.load(b.key, { start: EMPTY }, { undo: null })
  b.enterSetup()
  b.duplicate = null
  showDuplicate()
}

// ── Commands ──────────────────────────────────────────────────────────────────────────────────────────────────

handle("collect.save", () => saveBoard())
handle("collect.saveopen", () => saveBoard({ open: true }))

handle("collect.source", async ([value]) => {
  if (!value) return openCmdline("source ")
  if (/^\d+$/.test(value)) {
    const data = await fetch(`/lib/complete/?kind=source&q=`).then((r) => r.json()).catch(() => ({ items: [] }))
    const found = data.items.find((i) => i.value === value)
    if (!found) return status("No such source", { kind: "error" }) || false
    session.source = { id: Number(value), label: found.label }
  } else {
    const { data } = await post("/lib/sources/new/", { title: value })
    if (!data.ok) return status(data.message, { kind: "error" }) || false
    session.source = { id: data.id, label: data.label }
    status(`New source: ${data.label}`, { kind: "good", timeout: 2500 })
  }
  save()
})

const step = (name) => ([direction]) => {
  const n = Number(session[name]) || 0
  session[name] = String(Math.max(1, n + (direction === "down" ? -1 : 1)))
  save()
}
handle("collect.page", step("page"))
handle("collect.diagram", step("ref"))

handle("collect.tag", async ([key]) => {
  if (!key) return openCmdline("collect.tag ")
  const data = await fetch(`/lib/complete/?kind=tag&q=${encodeURIComponent(key)}`).then((r) => r.json()).catch(() => ({ items: [] }))
  const tag = data.items.find((i) => i.value === key) || data.items[0]
  if (!tag) return status(`No tag '${key}'`, { kind: "error" }) || false
  if (!session.tags.some((t) => t.key === tag.value)) session.tags.push({ key: tag.value, name: tag.label.split(" › ").pop() })
  save()
})
handle("collect.untag", () => {
  if (!session.tags.length) return false
  session.tags.pop()
  save()
})

handle("collect.preset", ([n]) => {
  const button = pane()?.querySelectorAll("[data-cmd='collect.preset']")[Number(n) - 1]
  if (!button) return status(`No preset ${n} (:preset-save <name> makes one)`, { kind: "error" }) || false
  const keys = button.dataset.keys.split(",")
  const names = button.dataset.names.split("|")
  const on = keys.every((k) => session.tags.some((t) => t.key === k))
  if (on) session.tags = session.tags.filter((t) => !keys.includes(t.key))
  else keys.forEach((k, i) => { if (!session.tags.some((t) => t.key === k)) session.tags.push({ key: k, name: names[i] }) })
  save()
})

handle("collect.presetsave", async (args) => {
  const { data } = await post("/lib/presets/", { name: args.join(" "), tags: session.tags.map((t) => t.key) })
  status(data.message, { kind: data.ok ? "good" : "error" })
  if (data.ok) {
    const box = pane()?.querySelector("[data-entry-presets]")
    if (box) {
      box.replaceChildren(...data.presets.map((p, i) => {
        const button = document.createElement("button")
        Object.assign(button, { type: "button", className: "segmented__option entry__preset", title: p.names, textContent: `${p.name} ` })
        Object.assign(button.dataset, { cmd: "collect.preset", args: String(i + 1), keys: p.keys, names: p.names })
        button.append(Object.assign(document.createElement("kbd"), { className: "keycap", textContent: String(i + 1) }))
        return button
      }))
      render()
    }
  }
})

handle("collect.ready", () => {
  session.ready = !session.ready
  save()
})

handle("collect.duplicate", () => {
  const dup = board()?.duplicate
  if (!dup) return false
  return window.SPOS.analysis.open(dup.id)
})

/** paste → c: one FEN goes onto the Collect board, a list of FENs is saved at once with the session's source and tags. */
export async function collectPaste(detected) {
  if (detected.kind === "fens") {
    const { data } = await post("/lib/collect/many/", { fens: detected.fens, source: session.source?.id || null, tags: session.tags.map((t) => t.key) })
    if (!data.ok) return status(data.message, { kind: "error" }) || false
    session.saved = [...data.positions.reverse().map((p) => ({ ...p, note: "pasted" })), ...session.saved].slice(0, 12)
    save()
    return status(data.message, { kind: "good" })
  }
  if (ctx.mode !== "collect") await switchMode("collect")
  const b = board()
  if (!b) return false
  const fen = detected.kind === "fen" ? detected.fen : detected.start
  lines.load(b.key, { start: fen, moves: detected.kind === "pgn" ? detected.moves.map((m) => m.uci) : [] }, { undo: "Paste position" })
  focusPane(b.pane.dataset.pane) // check and correct it on the board
  if (detected.kind === "fen") b.enterSetup()
}

Object.assign((window.SPOS ||= {}), { collect: { hasDuplicate: () => Boolean(board()?.duplicate), session: () => session } })
