// The interface language (spec 09 §14). The server puts the catalogue of the page's language into the page (#i18n,
// built by `manage.py i18n build`); tr() looks a text up, trc() one with a context, trn() picks the plural form for n.
// All three fill {name} placeholders from params. A text without a translation stays English.

export const language = document.documentElement.lang || "en"
/** For numbers and dates: the Swiss conventions (2’001 · 2 001), the app's main audience. */
export const locale = { de: "de-CH", fr: "fr-CH", it: "it-CH" }[language] || "en"
const source = document.getElementById("i18n")
const catalog = source ? JSON.parse(source.textContent) : {}
const pluralForm = language === "fr" ? (n) => (n > 1 ? 1 : 0) : (n) => (n === 1 ? 0 : 1)

function fill(text, params) {
  return params ? text.replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m)) : text
}

export function tr(text, params) {
  const found = catalog[text]
  return fill(typeof found === "string" && found ? found : text, params)
}

export function trc(context, text, params) {
  const found = catalog[`${context}\u0004${text}`]
  return fill(typeof found === "string" && found ? found : text, params)
}

export function trn(one, many, n, params) {
  const forms = catalog[one]
  const form = Array.isArray(forms) && forms[pluralForm(n)] ? forms[pluralForm(n)] : n === 1 ? one : many
  return fill(form, { n, ...params })
}

/** A number or a date in the interface language (Intl). */
export const formats = {
  number: (n, options) => new Intl.NumberFormat(locale, options).format(n),
  date: (d, options) => new Intl.DateTimeFormat(locale, options).format(d),
}
