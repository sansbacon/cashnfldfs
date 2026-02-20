from __future__ import annotations

from typing import Iterable


def clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def safe_float(x) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def percentile_rank(values: list[float | None]) -> list[float]:
    """Return percentile ranks in [0, 1] for each value.

    - None is treated as missing and receives 0.0.
    - Ties share the average rank.
    """

    indexed: list[tuple[int, float]] = []
    for i, v in enumerate(values):
        fv = safe_float(v)
        if fv is None:
            continue
        indexed.append((i, fv))

    n = len(indexed)
    out = [0.0] * len(values)
    if n == 0:
        return out

    indexed.sort(key=lambda t: t[1])

    # Assign average ranks for ties.
    rank = 0
    while rank < n:
        start = rank
        val = indexed[rank][1]
        while rank < n and indexed[rank][1] == val:
            rank += 1
        end = rank  # exclusive
        # ranks are 1..n; average rank for this tie group:
        avg_rank = (start + 1 + end) / 2.0
        pr = 0.0 if n == 1 else (avg_rank - 1.0) / (n - 1.0)
        for j in range(start, end):
            out[indexed[j][0]] = pr

    return out


def invert01(x: float) -> float:
    return 1.0 - clamp01(x)


def mean(xs: Iterable[float]) -> float:
    total = 0.0
    n = 0
    for x in xs:
        total += x
        n += 1
    return total / n if n else 0.0
