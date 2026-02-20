from __future__ import annotations

from .normalize import clamp01


def assign_tier(scores: list[float], *, looseness: float) -> list[str]:
    """Assign tiers based on relative score gaps.

    Heuristic intent:
    - 'must' when the player is a clear tier above peers.
    - 'want' for strong options.
    - 'viable' for playable options.
    - 'fade' for the rest.

    looseness in [0,1] slightly tightens/loosens the must threshold.
    """

    if not scores:
        return []

    # Normalize scores to 0..1 scale using min/max.
    smin = min(scores)
    smax = max(scores)
    denom = (smax - smin) if (smax - smin) != 0 else 1.0
    norm = [(s - smin) / denom for s in scores]

    # Thresholds are relative; looseness increases willingness to pay for raw points
    # but doesn't change tiers much.
    looseness = clamp01(looseness)

    must_th = 0.86 - 0.04 * looseness
    want_th = 0.68
    viable_th = 0.50

    out: list[str] = []
    for x in norm:
        if x >= must_th:
            out.append("must")
        elif x >= want_th:
            out.append("want")
        elif x >= viable_th:
            out.append("viable")
        else:
            out.append("fade")
    return out
