from __future__ import annotations

from dataclasses import dataclass

from .types import Position


@dataclass(frozen=True)
class WeightSet:
    """A simple linear model over feature percentiles.

    Each field name corresponds to a computed feature key.
    Positive weight increases score; negative decreases score.
    """

    weights: dict[str, float]


@dataclass(frozen=True)
class PositionWeightProfile:
    position: Position
    tight: WeightSet
    loose: WeightSet


def default_weight_profiles() -> dict[Position, PositionWeightProfile]:
    # Feature keys are created in scoring.py per position.
    return {
        "QB": PositionWeightProfile(
            position="QB",
            tight=WeightSet(
                weights={
                    "median": 0.22,
                    "floor": 0.14,
                    "value": 0.16,
                    "dropbacks": 0.10,
                    "rush_att": 0.14,
                    "gl_rush": 0.04,
                    "implied": 0.06,
                    "low_pressure": 0.04,
                    "low_ints": 0.06,
                }
            ),
            loose=WeightSet(
                weights={
                    "median": 0.30,
                    "floor": 0.12,
                    "value": 0.10,
                    "dropbacks": 0.10,
                    "rush_att": 0.18,
                    "gl_rush": 0.05,
                    "implied": 0.08,
                    "low_pressure": 0.03,
                    "low_ints": 0.04,
                }
            ),
        ),
        "RB": PositionWeightProfile(
            position="RB",
            tight=WeightSet(
                weights={
                    "median": 0.18,
                    "floor": 0.14,
                    "value": 0.14,
                    "snaps": 0.12,
                    "routes": 0.10,
                    "targets": 0.12,
                    "gl_share": 0.08,
                    "hv_touches": 0.10,
                    "favored": 0.02,
                    "low_committee": 0.08,
                }
            ),
            loose=WeightSet(
                weights={
                    "median": 0.24,
                    "floor": 0.12,
                    "value": 0.10,
                    "snaps": 0.12,
                    "routes": 0.10,
                    "targets": 0.12,
                    "gl_share": 0.08,
                    "hv_touches": 0.08,
                    "favored": 0.04,
                    "low_committee": 0.00,
                }
            ),
        ),
        "WR": PositionWeightProfile(
            position="WR",
            tight=WeightSet(
                weights={
                    "median": 0.16,
                    "floor": 0.12,
                    "value": 0.14,
                    "routes": 0.12,
                    "targets": 0.16,
                    "tgt_share": 0.10,
                    "low_adot": 0.08,
                    "rz_targets": 0.04,
                    "every_down": 0.06,
                    "low_boombust": 0.02,
                }
            ),
            loose=WeightSet(
                weights={
                    "median": 0.22,
                    "floor": 0.10,
                    "value": 0.10,
                    "routes": 0.12,
                    "targets": 0.16,
                    "tgt_share": 0.10,
                    "low_adot": 0.06,
                    "rz_targets": 0.06,
                    "every_down": 0.06,
                    "low_boombust": 0.02,
                }
            ),
        ),
        "TE": PositionWeightProfile(
            position="TE",
            tight=WeightSet(
                weights={
                    "median": 0.14,
                    "floor": 0.10,
                    "value": 0.18,
                    "routes": 0.16,
                    "targets": 0.16,
                    "tgt_share": 0.10,
                    "rz_targets": 0.08,
                    "full_route": 0.06,
                    "low_td_bust": 0.02,
                }
            ),
            loose=WeightSet(
                weights={
                    "median": 0.18,
                    "floor": 0.10,
                    "value": 0.12,
                    "routes": 0.18,
                    "targets": 0.18,
                    "tgt_share": 0.10,
                    "rz_targets": 0.08,
                    "full_route": 0.06,
                    "low_td_bust": 0.00,
                }
            ),
        ),
        "DST": PositionWeightProfile(
            position="DST",
            tight=WeightSet(
                weights={
                    "median": 0.10,
                    "floor": 0.04,
                    "value": 0.22,
                    "sacks": 0.18,
                    "turnovers": 0.16,
                    "opp_dropbacks": 0.10,
                    "low_opp_implied": 0.16,
                    "pay_up": 0.04,
                }
            ),
            loose=WeightSet(
                weights={
                    "median": 0.12,
                    "floor": 0.04,
                    "value": 0.18,
                    "sacks": 0.18,
                    "turnovers": 0.16,
                    "opp_dropbacks": 0.10,
                    "low_opp_implied": 0.18,
                    "pay_up": 0.04,
                }
            ),
        ),
    }
