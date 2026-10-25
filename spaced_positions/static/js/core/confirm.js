// A question in the status line, answered with one key (spec 02 §7): `offer(text, {y: fn})`. Esc or n cancel;
// other keys are swallowed while it is open, so nothing runs by accident.

import { ctx, keycaps, status } from "./context.js"
import { setOverlayHandler } from "./keys.js"

export function offer(text, actions) {
  status(text, { timeout: 0 })
  ctx.overlay = "confirm"
  setOverlayHandler((e, token) => {
    if (!actions[token] && token !== "n" && token !== "esc") return
    ctx.overlay = null
    setOverlayHandler(null)
    status("", { timeout: 1 })
    actions[token]?.()
  })
}

/**
 * A suggestion in the status line that doesn't stop the work (spec 02 §7): what happened, and keys for the
 * alternatives, e.g. `suggest("Added as a variation", [{ key: "r", label: "replace instead", run }])`. Its keys act;
 * any other key closes it and does what it always does. Questions that can't be undone use offer().
 */
export function suggest(text, choices, { timeout = 8000 } = {}) {
  const el = document.getElementById("status-message")
  status(text, { timeout: 0 })
  for (const c of choices) {
    const hint = document.createElement("span")
    hint.className = "keyhint"
    hint.append(keycaps([c.key]), ` ${c.label}`)
    hint.addEventListener("click", () => { done(); c.run() })
    el.append(" · ", hint)
  }
  const done = () => {
    clearTimeout(timer)
    if (ctx.overlay !== "suggest") return
    ctx.overlay = null
    setOverlayHandler(null)
    status("", { timeout: 1 })
  }
  const timer = setTimeout(done, timeout)
  ctx.overlay = "suggest"
  setOverlayHandler((e, token) => {
    const chosen = choices.find((c) => c.key === token)
    done()
    if (chosen) return void chosen.run()
    return "fallthrough"
  })
}
