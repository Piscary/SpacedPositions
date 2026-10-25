"""Fixture rows for the style guide's demo list: famous public-domain positions.
Rows: (id, title, tags, has solution, FEN or None)."""

DEMO_ROWS = [
    ("p1", "Légal's Mate: 5.Nxe5!", ("Opfer", "Matt in 3"), True, "rn1qkbnr/ppp2p1p/3p2p1/4p3/2B1P1b1/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 0 5"),
    ("p2", "Immortal Game: 18.Bd6!!", ("Damenopfer",), True, "rnb1k1nr/p2p1ppp/8/1pbN1N1P/4PBP1/3P1Q2/PqP5/R4KR1 w kq - 0 18"),
    ("p3", "Evergreen Game: 19.Rad1!!", ("Ablenkung", "Opfer"), True, "1r2k1r1/pbppnp1p/1bn2P2/7q/Q7/B1PB1N2/P4PPP/R3R1K1 w - - 1 19"),
    ("p4", "Opera Game finish: 16.Qb8+!!", ("Damenopfer", "Matt in 2"), True, "4kb1r/p2n1ppp/4q3/4p1B1/4P3/1Q6/PPP2PPP/2KR4 w k - 0 16"),
    ("p5", "Game of the Century: 17…Be6!!", ("Zwischenzug",), True, "r3r1k1/pp3pbp/1qp3p1/2B5/2BP2b1/Q1n2N2/P4PPP/3R1K1R b - - 3 17"),
    ("p6", "Kasparov's Immortal: 24.Rxd4!!", ("Opfer", "Königsjagd"), True, "b2r3r/k4p1p/p2q1np1/NppP4/3p1Q2/P4PPB/1PP4P/1K1RR3 w - - 1 24"),
    ("p7", "Saavedra position", ("Unterverwandlung", "Endspiel"), True, "8/8/1KP5/3r4/8/8/8/k7 w - - 0 1"),
    ("p8", "Réti's king march", ("Quadratregel", "Endspiel"), True, "7K/8/k1P5/7p/8/8/8/8 w - - 0 1"),
    ("p9", "Lucena position", ("Brückenbau", "Turmendspiel"), True, "1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1"),
    ("p10", "Philidor position", ("Philidor", "Turmendspiel"), True, "4k3/8/r7/4PK2/8/8/8/7R b - - 0 1"),
    ("p11", "Back-rank mate pattern", ("Grundreihenmatt",), False, None),
    ("p12", "Smothered mate pattern", ("Ersticktes Matt",), False, None),
    ("p13", "Arabian mate pattern", ("Arabisches Matt",), False, None),
    ("p14", "Anastasia's mate pattern", ("Anastasia-Matt",), False, None),
    ("p15", "Boden's mate pattern", ("Boden-Matt",), False, None),
    ("p16", "Knight fork on the royal family", ("Familiengabel",), False, None),
    ("p17", "Absolute pin against the king", ("Fesselung",), False, None),
    ("p18", "Skewer along the diagonal", ("Spieß",), False, None),
    ("p19", "Discovered check", ("Abzugsschach",), False, None),
    ("p20", "Windmill", ("Zwickmühle",), False, None),
    ("p21", "Opposition in the pawn ending", ("Opposition", "Bauernendspiel"), False, None),
    ("p22", "Triangulation", ("Dreiecksmanöver",), False, None),
    ("p23", "Wrong rook pawn", ("Falscher Randbauer",), False, None),
    ("p24", "Vancura defence", ("Vančura", "Turmendspiel"), False, None),
]
