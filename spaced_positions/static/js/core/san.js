// Typed move entry (spec 06 §5): which legal moves match what has been typed so far. Pure (no DOM): unit-tested
// with node in tests/js.
//
// Accepted: SAN (Nf3, exd5, O-O, e8=Q), without x or =, castling with zeros, UCI (g1f3, e7e8q), and the piece
// letters of the board.letters setting: German (S L T D K) always, French (C F T D R) or Italian (C A T D R) when
// chosen (their R is the king). Files are lower case; upper-case letters are pieces. Lower-case piece letters that
// can't be a file (n r q k s t l) count as pieces too.

const LETTERS = {
  de: { S: "N", L: "B", T: "R", D: "Q", K: "K" },
  fr: { C: "N", F: "B", T: "R", D: "Q", R: "K" },
  it: { C: "N", A: "B", T: "R", D: "Q", R: "K" },
}
const GERMAN = LETTERS.de

/** All spellings of a move (chess.js verbose move) that typing may match. */
export function spellings(move) {
  const san = move.san.replace(/[+#]/g, "")
  const out = new Set([san, san.replace("x", ""), san.replace("=", ""), san.replace("x", "").replace("=", "")])
  if (san.startsWith("O-O")) {
    for (const s of [...out]) {
      out.add(s.replaceAll("O", "0"))
      out.add(s.replaceAll("O", "o"))
    }
  }
  out.add(move.from + move.to + (move.promotion || ""))
  return [...out]
}

/** Normalise typed text: German (or French, Italian) pieces → English, lower-case piece letters that can't be files
 *  → upper case. */
export function normalise(text, letters = "en") {
  let t = text.trim().replace(/[+#!?\s]/g, "")
  if (!t) return ""
  const first = t[0]
  const local = LETTERS[letters] && letters !== "de" ? LETTERS[letters] : null
  if (local && local[first]) {
    t = local[first] + t.slice(1) // French and Italian letters: upper case only (c, f, a, d are files)
  } else if (!local && GERMAN[first.toUpperCase()] && (first === first.toUpperCase() || "stl".includes(first))) {
    t = GERMAN[first.toUpperCase()] + t.slice(1)
  } else if ("nrqk".includes(first) && !(local && first === "r")) {
    t = first.toUpperCase() + t.slice(1)
  }
  // a promotion piece may be in the letters too: e8=D → e8=Q
  const promotions = local || GERMAN
  return t.replace(/=?([A-Z])$/, (m, p) => (promotions[p] && promotions[p] !== "K" ? (m.startsWith("=") ? "=" : "") + promotions[p] : m))
}

/**
 * Moves matching typed text. Returns {candidates, exact}: candidates are the moves that some spelling starts with
 * the text; exact is the single move a spelling equals, if any.
 */
export function matchMoves(text, moves, letters = "en") {
  const t = normalise(text, letters)
  if (!t) return { candidates: [], exact: null }
  const lower = t.toLowerCase()
  const candidates = []
  let exact = null
  for (const move of moves) {
    const forms = spellings(move)
    const hit = forms.some((s) => s.startsWith(t) || (isUci(lower) && s.startsWith(lower)))
    if (!hit) continue
    candidates.push(move)
    if (forms.includes(t) || forms.includes(lower)) exact = exact ? null : move // two exact matches: not exact
  }
  // A lower-case 'b' is the b-file; only if no pawn move matches is it a bishop.
  if (!candidates.length && t[0] === "b") return matchMoves("B" + t.slice(1), moves, letters)
  return { candidates, exact: exact || (candidates.length === 1 ? candidates[0] : null) }
}

const isUci = (t) => /^[a-h][1-8]([a-h]([1-8][qrbn]?)?)?$/.test(t)

const FIGURINES = { K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘" }
const LETTERS_OF = {
  de: { K: "K", Q: "D", R: "T", B: "L", N: "S" }, fr: { K: "R", Q: "D", R: "T", B: "F", N: "C" }, it: { K: "R", Q: "D", R: "T", B: "A", N: "C" },
}

/** A SAN as DOM nodes whose piece letters carry their German, French and Italian letter and figurine; `html[data-letters]` and
 *  `html[data-figurines]` draw those instead (07 · figurines, Settings → Board · piece letters). */
export function sanNodes(san) {
  const piece = (letter) => {
    const p = Object.assign(document.createElement("span"), { className: "san-p" })
    Object.assign(p.dataset, { de: LETTERS_OF.de[letter], fr: LETTERS_OF.fr[letter], it: LETTERS_OF.it[letter], fig: FIGURINES[letter] })
    p.append(Object.assign(document.createElement("span"), { className: "san-l", textContent: letter }))
    return [p]
  }
  const m = san.match(/^([KQRBN]?)(.*?)(=([KQRBN]))?([+#]?)$/)
  if (!m) return [document.createTextNode(san)]
  const out = m[1] ? piece(m[1]) : []
  out.push(document.createTextNode(m[2]))
  if (m[4]) out.push(document.createTextNode("="), ...piece(m[4]))
  if (m[5]) out.push(document.createTextNode(m[5]))
  return out
}
