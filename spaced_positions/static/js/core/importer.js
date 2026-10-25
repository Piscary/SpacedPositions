// PGN import (spec 04 · Collect · Import, 11 §4): what a PGN holds, as a list: games and puzzles, duplicates marked
// and left out. j/k move, x (de)selects, a selects all or none, r puts the puzzles straight into training, ↵ imports,
// Esc closes. The import is one step of the undo stack: u moves what it added to the trash.

import { pushUndo } from "./commands.js"
import { inverse } from "./library.js"
import { ctx, keycaps, setLayer, status } from "./context.js"
import { setOverlayHandler } from "./keys.js"
import { offer } from "./confirm.js"
import { locale, tr, trn } from "./i18n.js"

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""
const post = (url, body) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(body) })
    .then(async (r) => ({ status: r.status, data: await r.json().catch(() => ({ ok: false, message: `error ${r.status}` })) }))
    .catch(() => ({ status: 0, data: { ok: false, message: tr("the app is not reachable") } }))

let open = null

export async function openImport(text) {
  status(tr("Reading the PGN…"), { timeout: 0 })
  const { data } = await post("/lib/import/scan/", { text })
  if (data.too_large) return importInBackground(new Blob([text]))
  if (!data.ok) return status(data.message, { kind: "error" }) || false
  if (data.more) {
    return offer(tr("More than 5,000 games: import all of them in the background (duplicates left out)? y · r with the puzzles in training · n"), {
      y: () => importInBackground(new Blob([text])),
      r: () => importInBackground(new Blob([text]), true),
    })
  }
  status("", { timeout: 1 })
  show(text, data.items)
}

const MAX_TEXT = 20_000_000
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/** A big PGN: uploaded as it is, imported in the background (the app stays usable); the status line follows it. */
export async function importInBackground(blob, ready = false) {
  status(tr("Uploading the PGN…"), { timeout: 0 })
  const data = await fetch(`/lib/import/upload/?ready=${ready ? 1 : 0}`, {
    method: "POST", headers: { "Content-Type": "application/octet-stream", "X-CSRFToken": csrf() }, body: blob,
  }).then((r) => r.json()).catch(() => ({ ok: false, message: tr("the app is not reachable") }))
  if (!data.ok) return status(data.message, { kind: "error" }) || false
  for (;;) {
    await sleep(1000)
    const job = await fetch(`/lib/import/job/${data.id}/`).then((r) => r.json()).catch(() => null)
    if (!job?.ok) return status(job?.message || job?.error || tr("The import stopped"), { kind: "error" }) || false
    if (!job.done) {
      status(tr("Importing in the background · {n} so far · {percent} %", { n: job.imported.toLocaleString(locale), percent: job.percent }), { timeout: 0 })
      continue
    }
    const parts = [trn("Imported {n} game", "Imported {n} games", job.games)]
    if (job.positions) parts.push(trn("{n} puzzle", "{n} puzzles", job.positions))
    if (job.duplicates) parts.push(tr("{n} already here", { n: job.duplicates }))
    if (job.failed) parts.push(tr("{n} could not be read", { n: job.failed }))
    job.message = parts.join(" · ")
    status(job.message, { kind: "good", keys: { seq: ["u"], label: tr("undo") } })
    pushUndo(inverse(job))
    if (job.games) window.SPOS.library?.setQuery?.("created:<1d", "games")
    return true
  }
}

function show(text, items) {
  close()
  const selected = new Set(items.filter((i) => !i.duplicate && !i.error).map((i) => i.i))
  const el = document.createElement("div")
  el.className = "importer"
  el.setAttribute("role", "dialog")
  el.setAttribute("aria-label", tr("Import"))
  const head = document.createElement("div")
  head.className = "importer__head"
  const list = document.createElement("div")
  list.className = "importer__list"
  list.setAttribute("role", "listbox")
  const foot = document.createElement("div")
  foot.className = "importer__foot"
  for (const [seq, label] of [[["j"], tr("down")], [["x"], tr("select")], [["a"], tr("all / none")], [["r"], tr("puzzles into training")], [["enter"], tr("import")], [["esc"], tr("cancel")]]) {
    const hint = document.createElement("span")
    hint.className = "keyhint"
    hint.append(keycaps(seq), ` ${label}`)
    foot.append(hint)
  }
  el.append(head, list, foot)
  document.body.append(el)
  open = { el, text, items, selected, cursor: 0, ready: false, previousLayer: ctx.layer }
  ctx.overlay = "import"
  setOverlayHandler(onKey)
  paint()
}

function paint() {
  const o = open
  const games = o.items.filter((i) => i.kind === "game").length
  const puzzles = o.items.length - games
  const dups = o.items.filter((i) => i.duplicate).length
  o.el.querySelector(".importer__head").textContent =
    `${tr("Import")} · ${trn("{n} game", "{n} games", games)}, ${trn("{n} puzzle", "{n} puzzles", puzzles)}` +
    `${dups ? ` · ${tr("{n} already in the library", { n: dups })}` : ""} · ${tr("{n} selected", { n: o.selected.size })}` +
    (puzzles ? ` · ${o.ready ? tr("puzzles into training") : tr("puzzles as drafts")}` : "")
  const list = o.el.querySelector(".importer__list")
  list.replaceChildren(...o.items.slice(0, 1000).map((item, index) => {
    const row = document.createElement("div")
    row.className = `list__row importer__row${index === o.cursor ? " is-cursor" : ""}${o.selected.has(item.i) ? " is-selected" : ""}`
    row.setAttribute("role", "option")
    row.setAttribute("aria-selected", String(o.selected.has(item.i)))
    row.append(
      Object.assign(document.createElement("span"), { className: "list__mark", textContent: o.selected.has(item.i) ? "▣" : "▢" }),
      Object.assign(document.createElement("span"), { className: "list__id", textContent: item.kind === "game" ? tr("game") : tr("puzzle") }),
      Object.assign(document.createElement("span"), { className: "list__title", textContent: item.title }),
      Object.assign(document.createElement("span"), {
        className: `list__meta${item.duplicate || item.error ? " importer__warn" : ""}`,
        textContent: item.error ? tr("error: {error}", { error: item.error }) : item.duplicate ? tr("duplicate of {id}", { id: item.duplicate }) : tr("{n} plies", { n: item.plies }),
      }),
    )
    row.addEventListener("click", () => { o.cursor = index; toggle() })
    return row
  }))
  list.children[o.cursor]?.scrollIntoView({ block: "nearest" })
}

function toggle() {
  const item = open.items[open.cursor]
  if (!item) return
  if (open.selected.has(item.i)) open.selected.delete(item.i)
  else open.selected.add(item.i)
  paint()
}

function onKey(e, token) {
  const o = open
  if (!o) return "fallthrough"
  if (token === "esc") return close()
  if (token === "j" || token === "down") o.cursor = Math.min(o.items.length - 1, o.cursor + 1)
  else if (token === "k" || token === "up") o.cursor = Math.max(0, o.cursor - 1)
  else if (token === "x" || token === "space") return toggle()
  else if (token === "a") o.selected = o.selected.size ? new Set() : new Set(o.items.map((i) => i.i))
  else if (token === "r") o.ready = !o.ready
  else if (token === "enter") return importSelected()
  paint()
}

async function importSelected() {
  const o = open
  if (!o.selected.size) return status(tr("Nothing selected"), { kind: "error" })
  const body = { text: o.text, selected: [...o.selected], ready: o.ready }
  close()
  status(tr("Importing…"), { timeout: 0 })
  const { data } = await post("/lib/import/run/", body)
  if (!data.ok) return status(data.message, { kind: "error" })
  status(data.message, { kind: "good", keys: { seq: ["u"], label: tr("undo") } })
  pushUndo(inverse(data))
  if (window.SPOS.library?.setQuery) {
    const games = data.added.games.length
    if (games) return window.SPOS.library.setQuery(`created:<1d`, "games")
    if (data.added.positions.length) return window.SPOS.library.setQuery(`created:<1d has:puzzle`, "positions")
  }
}

function close() {
  if (!open) return
  open.el.remove()
  setLayer(open.previousLayer === "pending" ? "normal" : open.previousLayer)
  open = null
  ctx.overlay = null
  setOverlayHandler(null)
}

/** `:import`: choose a PGN file. */
export function chooseFile() {
  const input = Object.assign(document.createElement("input"), { type: "file", accept: ".pgn,.txt,application/x-chess-pgn" })
  input.addEventListener("change", async () => {
    const file = input.files?.[0]
    if (!file) return
    if (file.size > MAX_TEXT) return importInBackground(file) // read on the server, a game at a time
    openImport(await file.text())
  })
  input.click()
}
