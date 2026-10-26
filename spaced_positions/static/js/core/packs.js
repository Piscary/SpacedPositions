// Puzzle packs (spec 09 §12): `:pack-import` or a .sppack file dropped on the app. The file goes to the server once,
// the preview shows what it is (from whom, for whom, the licence) and what it would do; ↵ accepts the licence and
// imports, r switches the puzzles into training or not, Esc cancels. Dropped .pgn files go to the PGN import.

import { handle } from "./commands.js"
import { ctx, emit, keycaps, setLayer, status } from "./context.js"
import { setOverlayHandler } from "./keys.js"
import { openImport } from "./importer.js"
import { tr, trn } from "./i18n.js"

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""
let open = null

export async function importPack(file) {
  status(tr("Reading {file}…", { file: file.name }), { timeout: 0 })
  return preview(fetch("/packs/scan/", { method: "POST", headers: { "Content-Type": "application/zip", "X-CSRFToken": csrf() }, body: file }))
}

async function preview(request) {
  const data = await request.then((r) => r.json()).catch(() => ({ ok: false, message: tr("the app is not reachable") }))
  if (!data.ok) return status(data.message, { kind: "error" }) || false
  status("", { timeout: 1 })
  show(data)
}

function show(data) {
  close()
  const el = Object.assign(document.createElement("div"), { className: "importer packview" })
  el.setAttribute("role", "dialog")
  el.setAttribute("aria-label", tr("Puzzle pack {title}", { title: data.title }))
  open = { el, data, ready: true, previousLayer: ctx.layer }
  document.body.append(el)
  ctx.overlay = "pack"
  setOverlayHandler(onKey)
  paint()
}

function line(className, text) {
  return Object.assign(document.createElement("p"), { className, textContent: text })
}

function paint() {
  const { el, data, ready } = open
  const c = data.counts
  const what = [tr("{n} new", { n: c.new }), c.update ? tr("{n} updated (you had version {version})", { n: c.update, version: data.earlier }) : "",
                c.duplicate ? tr("{n} already in your library", { n: c.duplicate }) : "", c.yours ? tr("{n} yours already", { n: c.yours }) : ""].filter(Boolean).join(" · ")
  const head = Object.assign(document.createElement("div"), { className: "importer__head",
    textContent: tr("Puzzle pack · {title} · version {version}", { title: data.title, version: data.version }) })
  const body = Object.assign(document.createElement("div"), { className: "packview__body" })
  body.append(
    line("", [data.author ? tr("from {name}", { name: data.author }) : "", data.for ? tr("for {name}", { name: data.for }) : ""].filter(Boolean).join(" ") || tr("no author given")),
    ...(data.description ? [line("muted", data.description)] : []),
    line("", `${trn("{n} position", "{n} positions", data.positions)}, ${trn("{n} puzzle", "{n} puzzles", data.puzzles)}: ${what}`),
    ...(data.games ? [line("", `${trn("{n} game", "{n} games", data.games)}: ${tr("{n} new", { n: data.game_counts.new })}` +
                              (data.game_counts.update ? `, ${tr("{n} updated", { n: data.game_counts.update })}` : ""))] : []),
    ...(data.unknown_tags.length ? [line("muted", tr("New tags: {tags}", { tags: data.unknown_tags.join(", ") }))] : []),
    line("packview__licence", tr("Licence: {licence}", { licence: data.licence || tr("none given") })),
    line("muted", ready ? tr("Puzzles go straight into training") : tr("Puzzles come as drafts (not in training yet)")),
  )
  const foot = Object.assign(document.createElement("div"), { className: "importer__foot" })
  for (const [seq, label] of [[["enter"], tr("accept the licence and import")], [["r"], tr("training on / off")], [["esc"], tr("cancel")]]) {
    const hint = Object.assign(document.createElement("span"), { className: "keyhint" })
    hint.append(keycaps(seq), ` ${label}`)
    foot.append(hint)
  }
  el.replaceChildren(head, body, foot)
}

function onKey(e, token) {
  if (!open) return "fallthrough"
  if (token === "esc") return close()
  if (token === "r") {
    open.ready = !open.ready
    return paint()
  }
  if (token === "enter") return run()
}

async function run() {
  const { data, ready } = open
  close()
  status(tr("Importing the pack…"), { timeout: 0 })
  const result = await fetch("/packs/run/", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
    body: JSON.stringify({ token: data.token, ready }) }).then((r) => r.json()).catch(() => ({ ok: false, message: tr("the app is not reachable") }))
  if (!result.ok) return status(result.message, { kind: "error" })
  status(result.message, { kind: "good", timeout: 8000 })
  emit("effects", result.effects || {})
  window.SPOS.library?.setQuery?.(result.query, "positions")
}

function close() {
  if (!open) return
  open.el.remove()
  setLayer(open.previousLayer === "pending" ? "normal" : open.previousLayer)
  open = null
  ctx.overlay = null
  setOverlayHandler(null)
}

// The starter pack that comes with the app: the same preview, then the same import
handle("pack.starter", () => preview(fetch("/packs/starter/", { method: "POST", headers: { "X-CSRFToken": csrf() } })))

handle("pack.import", () => {
  const input = Object.assign(document.createElement("input"), { type: "file", accept: ".sppack,application/zip" })
  input.addEventListener("change", () => input.files?.[0] && importPack(input.files[0]))
  input.click()
})

// Drop a file anywhere: a pack is previewed, a PGN goes to the PGN import
document.addEventListener("dragover", (e) => {
  if ([...(e.dataTransfer?.items || [])].some((i) => i.kind === "file")) e.preventDefault()
})
document.addEventListener("drop", async (e) => {
  const file = e.dataTransfer?.files?.[0]
  if (!file) return
  e.preventDefault()
  if (file.name.endsWith(".sppack")) return importPack(file)
  if (/\.(pgn|txt)$/i.test(file.name)) return openImport(await file.text())
  status(tr("{file}: drop a puzzle pack (.sppack) or a PGN", { file: file.name }), { kind: "error" })
})
