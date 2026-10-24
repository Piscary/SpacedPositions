// A question in the status line, answered with one key (spec 02 §7): `offer(text, {y: fn})`. Esc or n cancel;
// other keys are swallowed while it is open, so nothing runs by accident.

import { ctx, status } from "./context.js"
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
