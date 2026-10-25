"""The Storm clock: how much time a right answer adds, measured on your own solving.

    typical time   the median of your last WINDOW successful Storm solves (at least MIN_SAMPLES of them), else
                   DEFAULT_MS, clamped to MIN_MS … MAX_MS. A median over a long window follows you as you get
                   faster; one slow puzzle doesn't move it.
    bonus          typical time × pace × combo multiplier
                   pace: fast 0.5 · medium 0.75 · slow 1.0: you gain time only when you're quicker than that share
                   of your usual time; combo levels ×1 … ×5 multiply by 1.0 … 1.4
    a miss         costs PENALTY_MS and the combo
"""

import statistics

from .models import Attempt

WINDOW = 300
MIN_SAMPLES = 15
DEFAULT_MS = 8000
MIN_MS, MAX_MS = 1500, 30000
PENALTY_MS = 10000
PACES = {"fast": 0.5, "medium": 0.75, "slow": 1.0}
COMBO_LEVELS = [0, 5, 12, 20, 30]  # solved in a row to reach ×1 … ×5
COMBO_MULT = [1.0, 1.1, 1.2, 1.3, 1.4]


def typical_ms() -> int:
    rows = list(Attempt.objects.filter(mode="storm", success=True, ms__gt=0).order_by("-at").values_list("ms", flat=True)[:WINDOW])
    if len(rows) < MIN_SAMPLES:
        return DEFAULT_MS
    return int(max(MIN_MS, min(MAX_MS, statistics.median(rows))))


def clock(pace: str) -> dict:
    pace = pace if pace in PACES else "medium"
    return {
        "pace": pace,
        "factor": PACES[pace],
        "typical": typical_ms(),
        "penalty": PENALTY_MS,
        "levels": COMBO_LEVELS,
        "mult": COMBO_MULT,
    }
