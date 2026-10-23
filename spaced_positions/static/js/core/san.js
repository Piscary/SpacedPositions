// Typed move entry (spec 06 §5): which legal moves match what has been typed so far. Pure (no DOM): unit-tested
// with node in tests/js.
//
// Accepted: SAN (Nf3, exd5, O-O, e8=Q), without x or =, castling with zeros, German piece letters (S L T D K),
// UCI (g1f3, e7e8q). Files are lower case; upper-case letters are pieces. Lower-case piece letters that can't be a
// file (n r q k s t l) count as pieces too.

const GERMAN = { S: "N", L: "B", T: "R", D: "Q", K: "K" }

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

/** Normalise typed text: German pieces → English, lower-case piece letters that can't be files → upper case. */
export function normalise(text) {
  let t = text.trim().replace(/[+#!?\s]/g, "")
  if (!t) return ""
  const first = t[0]
  if (GERMAN[first.toUpperCase()] && (first === first.toUpperCase() || "stl".includes(first))) {
    t = GERMAN[first.toUpperCase()] + t.slice(1)
  } else if ("nrqk".includes(first)) {
    t = first.toUpperCase() + t.slice(1)
  }
  // a promotion piece may be German too: e8=D → e8=Q
  return t.replace(/=?([DTLS])$/, (m, p) => (m.startsWith("=") ? "=" : "") + GERMAN[p])
}

/**
 * Moves matching typed text. Returns {candidates, exact}: candidates are the moves that some spelling starts with
 * the text; exact is the single move a spelling equals, if any.
 */
export function matchMoves(text, moves) {
  const t = normalise(text)
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
  if (!candidates.length && t[0] === "b") return matchMoves("B" + t.slice(1), moves)
  return { candidates, exact: exact || (candidates.length === 1 ? candidates[0] : null) }
}

const isUci = (t) => /^[a-h][1-8]([a-h]([1-8][qrbn]?)?)?$/.test(t)
