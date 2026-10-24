// The command line `:` (spec 02 §3): fuzzy search over all commands, each row with its keys and its disabled
// reason, typed arguments with completion (Tab), history (↑ on an empty line).

import { commands, enabled, handle, primaryKeys, run } from "./commands.js"
import { ctx, keycaps, setLayer, status, storage } from "./context.js"
import { setOverlayHandler } from "./keys.js"
import { bufferIds, layoutNames } from "./layout.js"

const MAX_ROWS = 12
let el, input, results, hint
let rows = [] // [{id, title, ...}] or completions [{value, label}]
let cursor = 0
let historyIndex = -1
let previousLayer = "normal"
let layoutCache = []

function build() {
  el = document.createElement("div")
  el.className = "bottom-overlay cmdline"
  el.hidden = true
  results = document.createElement("div")
  results.className = "cmdline__results"
  const row = document.createElement("div")
  row.className = "cmdline__input-row"
  const prompt = document.createElement("span")
  prompt.className = "cmdline__prompt"
  prompt.textContent = ":"
  input = document.createElement("input")
  input.className = "cmdline__input"
  input.setAttribute("aria-label", "Command")
  input.autocomplete = "off"
  input.spellcheck = false
  hint = document.createElement("span")
  hint.className = "cmdline__hint"
  row.append(prompt, input, hint)
  el.append(results, row)
  document.getElementById("statusline").append(el)
  input.addEventListener("input", refresh)
}

export function openCmdline(prefill = "") {
  if (!el) build()
  previousLayer = ctx.layer === "pending" ? "normal" : ctx.layer
  ctx.overlay = "cmdline"
  setLayer("command")
  el.hidden = false
  input.value = prefill
  historyIndex = -1
  setOverlayHandler(onKey)
  input.focus()
  layoutNames().then((names) => { layoutCache = names }).catch(() => {})
  refresh()
}

function close() {
  el.hidden = true
  ctx.overlay = null
  setOverlayHandler(null)
  input.blur()
  setLayer(previousLayer)
}

// ── Parsing and matching ───────────────────────────────────────────────────────────────────────────────────────

function byName(word) {
  const all = commands()
  if (all[word]) return word
  return Object.keys(all).find((id) => all[id].aliases?.includes(word)) || null
}

/** Fuzzy score of `query` in `text` (subsequence; bonus for word starts and runs). null = no match. */
function fuzzy(query, text) {
  if (!query) return { score: 0, hits: [] }
  const q = query.toLowerCase(), t = text.toLowerCase()
  let score = 0, ti = 0, run = 0
  const hits = []
  for (const ch of q) {
    const found = t.indexOf(ch, ti)
    if (found < 0) return null
    run = found === ti ? run + 1 : 0
    score += 1 + run * 2 + (found === 0 || /[\s.\-:]/.test(t[found - 1]) ? 4 : 0) - Math.min(3, found - ti) * 0.2
    hits.push(found)
    ti = found + 1
  }
  return { score, hits }
}

function completions(type) {
  const themes = window.SPOS.themes
  switch (type) {
    case "theme":
      return ["auto", ...Object.keys(themes.themes)].map((v) => ({ value: v, label: v === "auto" ? "auto · follow the system" : themes.themes[v].label }))
    case "view":
      return Object.entries(window.SPOS.views).map(([k, v]) => ({ value: k, label: `${v.label}${v.phase ? ` · phase ${v.phase}` : ""}` }))
    case "token":
    case "tokenname":
      return Object.entries(themes.schema).map(([k, v]) => ({ value: type === "token" ? `${k}=` : k, label: v.description }))
    case "layout":
      return layoutCache.map((name) => ({ value: name, label: "saved layout" }))
    case "pieceset":
      return Object.entries(themes.pieces || {}).map(([k, v]) => ({ value: k, label: `${v.label} · ${v.author} · ${v.licence}` }))
    case "buffer":
      return bufferIds().map((id) => ({ value: id, label: "hidden buffer" }))
    case "position":
    case "tag":
    case "source":
      return fromServer(type, parse().rest || "")
    default:
      return []
  }
}

// Positions and tags come from the server (the rows follow the text as it is typed).
const SERVER = {
  position: (q) => fetch(`/positions/search/?q=${encodeURIComponent(q)}`).then((r) => r.json())
    .then((data) => data.positions.map((p) => ({ value: p.id, title: p.title, label: p.source || "", server: true }))),
  tag: (q) => fetch(`/lib/complete/?kind=tag&q=${encodeURIComponent(q)}`).then((r) => r.json())
    .then((data) => data.items.map((t) => ({ value: t.value, title: t.label, label: `${t.value} · ${t.note}`, server: true }))),
  source: (q) => fetch(`/lib/complete/?kind=source&q=${encodeURIComponent(q)}`).then((r) => r.json())
    .then((data) => data.items.map((s) => ({ value: s.value, title: s.label, label: s.note || "", server: true }))),
}
let serverRows = []
let serverQuery = null
let serverTimer
function fromServer(type, q) {
  const key = `${type}:${q}`
  if (key !== serverQuery) {
    serverQuery = key
    clearTimeout(serverTimer)
    serverTimer = setTimeout(async () => {
      const rows = await SERVER[type](q).catch(() => [])
      if (serverQuery !== key || !input) return
      serverRows = rows
      refresh()
    }, 120)
  }
  return serverRows
}

function parse() {
  const text = input.value.replace(/^\s+/, "")
  const space = text.indexOf(" ")
  const word = space < 0 ? text : text.slice(0, space)
  const rest = space < 0 ? null : text.slice(space + 1)
  const id = rest !== null ? byName(word) : null
  return { text, word, rest, id }
}

function refresh() {
  const { text, rest, id } = parse()
  results.replaceChildren()
  rows = []
  cursor = 0
  if (id) {
    const spec = commands()[id]
    const arg = spec.args?.[0]
    hint.textContent = arg ? `${spec.title} · ${arg.name}${arg.optional ? " (optional)" : ""}` : spec.title
    const values = arg ? (arg.type === "enum" ? arg.values.map((v) => ({ value: v, label: v })) : completions(arg.type)) : []
    rows = values
      .map((c) => ({ ...c, match: c.server ? { score: 0 } : fuzzy(rest, c.value) }))
      .filter((c) => c.match)
      .sort((a, b) => b.match.score - a.match.score)
      .slice(0, MAX_ROWS)
    rows.forEach((c, i) => results.append(completionRow(c, i)))
  } else {
    hint.textContent = text ? "" : "type a command · Tab completes · ↑ history"
    const all = commands()
    rows = Object.entries(all)
      .filter(([, spec]) => !spec.hidden)
      .map(([cid, spec]) => {
        const names = [spec.title, ...(spec.aliases || []), cid]
        const best = names.map((n, i) => ({ i, m: fuzzy(text, n) })).filter((x) => x.m).sort((a, b) => b.m.score - a.m.score)[0]
        return best ? { id: cid, spec, score: best.m.score + (best.i === 1 ? 2 : 0), hits: best.i === 0 ? best.m.hits : [] } : null
      })
      .filter(Boolean)
      .sort((a, b) => b.score - a.score || a.spec.title.localeCompare(b.spec.title))
      .slice(0, MAX_ROWS)
    rows.forEach((r, i) => results.append(commandRow(r, i)))
  }
  paint()
}

function commandRow(r, i) {
  const row = document.createElement("div")
  const state = enabled(r.id)
  row.className = `cmdline__row${state.ok ? "" : " is-disabled"}`
  const title = document.createElement("span")
  title.className = "cmdline__title"
  ;[...r.spec.title].forEach((ch, j) => title.append(r.hits.includes(j) ? Object.assign(document.createElement("mark"), { textContent: ch }) : ch))
  if (r.spec.aliases?.length) {
    const alias = document.createElement("span")
    alias.className = "cmdline__alias"
    alias.textContent = `:${r.spec.aliases[0]}`
    title.append(alias)
  }
  if (!state.ok) {
    const reason = document.createElement("span")
    reason.className = "cmdline__reason"
    reason.textContent = `· ${state.reason}`
    title.append(reason)
  }
  const keys = primaryKeys(r.id)
  const group = document.createElement("span")
  group.className = "cmdline__group"
  group.textContent = r.spec.group || ""
  row.append(title, keys ? keycaps(keys) : document.createElement("span"), group)
  row.addEventListener("click", () => { cursor = i; accept() })
  return row
}

function completionRow(c, i) {
  const row = document.createElement("div")
  row.className = "cmdline__row"
  const title = document.createElement("span")
  title.className = "cmdline__title"
  title.textContent = c.title || c.value
  const label = document.createElement("span")
  label.className = "cmdline__reason"
  label.textContent = c.label
  title.append(label)
  row.append(title, document.createElement("span"), document.createElement("span"))
  row.addEventListener("click", () => { cursor = i; complete(); input.focus() })
  return row
}

function paint() {
  ;[...results.children].forEach((row, i) => row.classList.toggle("is-cursor", i === cursor))
  results.children[cursor]?.scrollIntoView({ block: "nearest" })
}

// ── Running ────────────────────────────────────────────────────────────────────────────────────────────────────

function argsFor(id, rest) {
  const spec = commands()[id]
  const text = (rest || "").trim()
  if (!text) return []
  if (spec.args?.length === 1 && ["text", "token", "layout", "source"].includes(spec.args[0].type)) return [text]
  return text.split(/\s+/)
}

function complete() {
  const { word, id } = parse()
  const choice = rows[cursor]
  if (!choice) return
  if (id && "value" in choice) input.value = `${word} ${choice.value}`
  else if (choice.id) input.value = `${choice.spec.aliases?.[0] || choice.id} `
  refresh()
}

async function accept() {
  const { text, rest, id } = parse()
  if (!text) {
    const last = (storage("cmdhistory") || [])[0]
    if (last) {
      input.value = last
      return accept()
    }
    return close()
  }
  let commandId = id
  let args = id ? argsFor(id, rest) : []
  if (!commandId) {
    const exact = byName(text.trim())
    const choice = exact ? { id: exact } : rows[cursor]
    if (!choice?.id) return status(`no command '${text}'`, { kind: "error" })
    commandId = choice.id
    const spec = commands()[commandId]
    const required = (spec.args || []).filter((a) => !a.optional)
    if (required.length) {
      input.value = `${spec.aliases?.[0] || commandId} `
      return refresh() // ask for the argument first
    }
  } else {
    // A closed argument type (a theme, a view …) takes the highlighted completion unless the typed word is exact.
    const arg = commands()[id].args?.[0]
    const closed = arg && ["enum", "theme", "view", "tokenname", "layout", "buffer", "pieceset", "position", "tag", "source"].includes(arg.type)
    const choice = rows[cursor]
    if (closed && choice && "value" in choice && !rows.some((r) => r.value === args[0])) args = [choice.value]
  }
  remember(input.value.trim())
  close()
  await run(commandId, args, { source: "cmdline" })
}

function remember(line) {
  const history = (storage("cmdhistory") || []).filter((h) => h !== line)
  history.unshift(line)
  storage("cmdhistory", history.slice(0, 50))
}

function onKey(e, token) {
  if (token === "esc") return close()
  if (token === "enter") return accept()
  if (token === "tab") return complete()
  const browsingHistory = historyIndex >= 0 || !input.value
  if (token === "up" && browsingHistory) return history(1)
  if (token === "down" && historyIndex >= 0) return history(-1)
  if (token === "shift+tab" || token === "up") {
    cursor = Math.max(0, cursor - 1)
    return paint()
  }
  if (token === "down") {
    cursor = Math.min(rows.length - 1, cursor + 1)
    return paint()
  }
  historyIndex = -1
  return "pass" // typing
}

function history(step) {
  const items = storage("cmdhistory") || []
  historyIndex = Math.max(-1, Math.min(items.length - 1, historyIndex + step))
  input.value = historyIndex >= 0 ? items[historyIndex] : ""
  refresh()
}

handle("cmdline.open", () => openCmdline())
handle("layout.menu", () => openCmdline("layout-"))
