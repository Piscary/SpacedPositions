// The Ticker (spec 05 · Ticker): a number that changes counts up or down over 300 ms, in tabular figures so nothing
// shifts. Off with Settings → Sound and motion · counting numbers, or when motion is 0.

const DURATION = 300

const animated = () =>
  window.SPOS.settings?.["display.ticker"] !== false &&
  Number(getComputedStyle(document.documentElement).getPropertyValue("--motion") || 1) > 0 &&
  !matchMedia("(prefers-reduced-motion: reduce)").matches

/** Show `value` in `el`; a number counts there from the one shown now. Other text is set as it is. */
export function setNumber(el, value) {
  if (!el) return
  const to = Number(value)
  const from = Number(el.dataset.tickerValue ?? el.textContent)
  el.dataset.tickerValue = String(value)
  cancelAnimationFrame(Number(el.dataset.tickerFrame || 0))
  if (!Number.isFinite(to) || !Number.isFinite(from) || from === to || !animated() || !el.isConnected) {
    el.textContent = String(value)
    return
  }
  const t0 = performance.now()
  const step = (now) => {
    const k = Math.min(1, (now - t0) / DURATION)
    const eased = 1 - (1 - k) ** 3
    el.textContent = String(Math.round(from + (to - from) * eased))
    if (k < 1) el.dataset.tickerFrame = String(requestAnimationFrame(step))
  }
  el.dataset.tickerFrame = String(requestAnimationFrame(step))
}

/** Numbers marked `data-ticker` in freshly shown HTML count up from 0 (Home, Stats). */
export function tickIn(root) {
  for (const el of root.querySelectorAll("[data-ticker]:not([data-ticker-value])")) {
    const value = el.textContent.trim()
    if (!/^\d+$/.test(value)) continue
    el.textContent = "0"
    el.dataset.tickerValue = "0"
    setNumber(el, Number(value))
  }
}
