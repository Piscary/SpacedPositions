// The usage report's counts (spec 14 §5): how often each command ran and how it was started (a key, a click, a hint
// label, the command line), and the errors the app caught. Counts only, gathered here and kept in the app's own
// database every half minute; nothing leaves the computer. `:test-report` writes them into a file.

import { handle } from "./commands.js"
import { on, status } from "./context.js"
import { tr } from "./i18n.js"

const COUNTED = new Set(["key", "mouse", "hint", "cmdline"]) // what the user did; not "code", "undo" or "repeat"
const FLUSH_MS = 30_000

let pending = new Map() // "name source" → count

function add(name, source) {
  const key = `${name} ${source}`
  pending.set(key, (pending.get(key) || 0) + 1)
}

on("command", ({ id, source }) => {
  if (COUNTED.has(source)) add(id, source)
})
window.addEventListener("error", (e) => {
  if (!String(e.message || "").startsWith("ResizeObserver")) add("error.js", "error") // the browser's harmless note
})
window.addEventListener("unhandledrejection", () => add("error.js", "error"))

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || ""

/** Store what was counted since the last time (keepalive: also while the tab closes). */
export function flush() {
  if (!pending.size) return Promise.resolve()
  const counts = [...pending].map(([key, n]) => [...key.split(" "), n])
  pending = new Map()
  return fetch("/usage/", {
    method: "POST", keepalive: true, headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
    body: JSON.stringify({ counts }),
  }).catch(() => null)
}
setInterval(flush, FLUSH_MS)
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") flush()
})

handle("app.testreport", async () => {
  await flush()
  const link = Object.assign(document.createElement("a"), { href: "/usage/report/", download: "" })
  document.body.append(link)
  link.click()
  link.remove()
  status(tr("Usage report written: look it over, then send it as the test group's note says"), { timeout: 5000 })
})

window.SPOS ||= {}
window.SPOS.usage = { flush }
