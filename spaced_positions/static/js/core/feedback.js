// `:feedback` (spec 14 §5): what kind of feedback, then the feedback page opens with a message started for the
// tester: the kind, room to write, and what the app adds (version, system, language, where you were). The same text
// goes to the clipboard, for a form that doesn't take it from the link. Nothing is sent: the tester writes and sends.

import { handle } from "./commands.js"
import { ctx, status } from "./context.js"
import { openMenu } from "./menu.js"
import { tr } from "./i18n.js"

const KINDS = [
  ["broke", "b", () => tr("Something broke")],
  ["confused", "c", () => tr("Something confused me")],
  ["wish", "w", () => tr("I wish …")],
  ["other", "o", () => tr("Something else")],
]

/** The message: the kind, an empty line to write on, and the app's details below a line. */
export function message(kind) {
  const app = window.SPOS.app || {}
  const mode = window.SPOS.modes?.[ctx.mode]?.label || ctx.mode || ""
  const view = ctx.pane ? window.SPOS.views?.[ctx.pane.view]?.label || ctx.pane.view : ""
  const label = KINDS.find(([k]) => k === kind)?.[2]() || kind
  return [
    `${label}:`,
    "",
    "",
    `— ${tr("added by the app")} —`,
    `Spaced Positions ${app.version || "?"} · ${app.system || navigator.platform} · ${document.documentElement.lang || "en"}`,
    `${mode}${view ? ` · ${view}` : ""}`,
  ].join("\n")
}

handle("app.feedback", async ([kind]) => {
  if (!kind) {
    kind = await openMenu({
      title: tr("Feedback: what is it about?"),
      items: KINDS.map(([value, key, label]) => ({ label: label(), key, keys: [key], value })),
    })
    if (!kind) return false
  }
  const text = message(kind)
  const url = new URL(window.SPOS.app?.feedback || "https://piscarys.com/pages/spaced-positions")
  url.searchParams.set("kind", kind)
  url.searchParams.set("message", text)
  let copied = true
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    copied = false
  }
  window.open(url.toString(), "_blank", "noopener")
  status(copied ? tr("The feedback page is open; if its message field is empty, paste (the text is in the clipboard)")
    : tr("The feedback page is open: write your message there"), { kind: "good", timeout: 8000 })
})
