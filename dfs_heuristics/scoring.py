from __future__ import annotations

import math
from typing import Any, Callable

from .normalize import clamp01, invert01, percentile_rank, safe_float


def _bool01(x: Any) -> float:
    if x is None:
        return 0.0
    if isinstance(x, bool):
        return 1.0 if x else 0.0
    try:
        return 1.0 if int(x) != 0 else 0.0
    except Exception:
        return 0.0


def _get(row: dict[str, Any], key: str) -> float | None:
    return safe_float(row.get(key))


def _nan_to_none(x: float | None) -> float | None:
    if x is None:
        return None
    if math.isnan(x):
        return None
    return x


def build_features_qb(rows: list[dict[str, Any]]) -> list[dict[str, float]]:
    med = percentile_rank([_get(r, "proj_points_median") for r in rows])
    floor = percentile_rank([_get(r, "proj_points_floor") for r in rows])
    value = percentile_rank([_get(r, "value_pts_per_1k") for r in rows])

    dropbacks = percentile_rank([_get(r, "proj_dropbacks") for r in rows])
    rush_att = percentile_rank([_get(r, "proj_rush_attempts") for r in rows])
    gl_rush = percentile_rank([_get(r, "proj_goal_line_rush_att") for r in rows])
    implied = percentile_rank([_get(r, "team_implied_points") for r in rows])

    # risk/fragility signals (lower is better)
    pressure = percentile_rank([_get(r, "opp_pressure_rate") for r in rows])
    ints = percentile_rank([_get(r, "proj_interceptions") for r in rows])

    out: list[dict[str, float]] = []
    for i, r in enumerate(rows):
        out.append(
            {
                "median": med[i],
                "floor": floor[i],
                "value": value[i],
                "dropbacks": dropbacks[i],
                "rush_att": rush_att[i],
                "gl_rush": gl_rush[i],
                "implied": implied[i],
                "low_pressure": invert01(pressure[i]),
                "low_ints": invert01(ints[i]),
                # keep some raw flags around for penalty rules
                "qb_rush_upside_flag": _bool01(r.get("qb_rush_upside_flag")),
            }
        )
    return out


def build_features_rb(rows: list[dict[str, Any]]) -> list[dict[str, float]]:
    med = percentile_rank([_get(r, "proj_points_median") for r in rows])
    floor = percentile_rank([_get(r, "proj_points_floor") for r in rows])
    value = percentile_rank([_get(r, "value_pts_per_1k") for r in rows])

    snaps = percentile_rank([_get(r, "proj_snaps") for r in rows])
    routes = percentile_rank([_get(r, "proj_route_participation") for r in rows])
    targets = percentile_rank([_get(r, "proj_targets") for r in rows])
    gl_share = percentile_rank([_get(r, "proj_goal_line_share") for r in rows])
    hv = percentile_rank([_get(r, "proj_high_value_touches") for r in rows])

    spread = percentile_rank([_get(r, "spread_home") for r in rows])

    out: list[dict[str, float]] = []
    for i, r in enumerate(rows):
        committee = _bool01(r.get("committee_risk_flag"))
        out.append(
            {
                "median": med[i],
                "floor": floor[i],
                "value": value[i],
                "snaps": snaps[i],
                "routes": routes[i],
                "targets": targets[i],
                "gl_share": gl_share[i],
                "hv_touches": hv[i],
                "favored": invert01(spread[i]),  # more negative spread is better; percentile rank assumes higher is "more"
                "low_committee": 1.0 - committee,
                "committee_risk_flag": committee,
            }
        )
    return out


def build_features_wr(rows: list[dict[str, Any]]) -> list[dict[str, float]]:
    med = percentile_rank([_get(r, "proj_points_median") for r in rows])
    floor = percentile_rank([_get(r, "proj_points_floor") for r in rows])
    value = percentile_rank([_get(r, "value_pts_per_1k") for r in rows])

    routes = percentile_rank([_get(r, "proj_route_participation") for r in rows])
    targets = percentile_rank([_get(r, "proj_targets") for r in rows])
    share = percentile_rank([_get(r, "proj_target_share") for r in rows])

    adot = percentile_rank([_get(r, "proj_adot") for r in rows])
    rz = percentile_rank([_get(r, "proj_red_zone_targets") for r in rows])

    out: list[dict[str, float]] = []
    for i, r in enumerate(rows):
        boom = _bool01(r.get("boom_bust_flag"))
        every = _bool01(r.get("every_down_role_flag"))
        out.append(
            {
                "median": med[i],
                "floor": floor[i],
                "value": value[i],
                "routes": routes[i],
                "targets": targets[i],
                "tgt_share": share[i],
                "low_adot": invert01(adot[i]),
                "rz_targets": rz[i],
                "every_down": every,
                "low_boombust": 1.0 - boom,
                "boom_bust_flag": boom,
            }
        )
    return out


def build_features_te(rows: list[dict[str, Any]]) -> list[dict[str, float]]:
    med = percentile_rank([_get(r, "proj_points_median") for r in rows])
    floor = percentile_rank([_get(r, "proj_points_floor") for r in rows])
    value = percentile_rank([_get(r, "value_pts_per_1k") for r in rows])

    routes = percentile_rank([_get(r, "proj_route_participation") for r in rows])
    targets = percentile_rank([_get(r, "proj_targets") for r in rows])
    share = percentile_rank([_get(r, "proj_target_share") for r in rows])
    rz = percentile_rank([_get(r, "proj_red_zone_targets") for r in rows])

    out: list[dict[str, float]] = []
    for i, r in enumerate(rows):
        td_bust = _bool01(r.get("td_or_bust_flag"))
        full_route = _bool01(r.get("full_route_role_flag"))
        out.append(
            {
                "median": med[i],
                "floor": floor[i],
                "value": value[i],
                "routes": routes[i],
                "targets": targets[i],
                "tgt_share": share[i],
                "rz_targets": rz[i],
                "full_route": full_route,
                "low_td_bust": 1.0 - td_bust,
                "td_or_bust_flag": td_bust,
            }
        )
    return out


def build_features_dst(rows: list[dict[str, Any]], *, site: str) -> list[dict[str, float]]:
    med = percentile_rank([_get(r, "proj_points_median") for r in rows])
    floor = percentile_rank([_get(r, "proj_points_floor") for r in rows])

    # Derive value without needing player_slate.value_pts_per_1k.
    # pts_per_1k = median / (salary/1000)
    vals = []
    for r in rows:
        salary = _get(r, "salary")
        pts = _get(r, "proj_points_median")
        if salary is None or pts is None or salary <= 0:
            vals.append(None)
        else:
            vals.append(pts / (salary / 1000.0))
    value = percentile_rank(vals)

    sacks = percentile_rank([_get(r, "proj_sacks") for r in rows])
    # turnovers: combine ints + fumbles
    tos = []
    for r in rows:
        i = _get(r, "proj_interceptions") or 0.0
        f = _get(r, "proj_fumbles_recovered") or 0.0
        tos.append(i + f)
    turnovers = percentile_rank(tos)

    drop = percentile_rank([_get(r, "opp_dropbacks_proj") for r in rows])
    opp_imp = percentile_rank([_get(r, "opp_implied_points") for r in rows])

    out: list[dict[str, float]] = []
    for i, r in enumerate(rows):
        pay = _bool01(r.get("pay_up_viable_flag"))

        # Site nuance: FD tends to justify paying up more often.
        if site.upper() == "FD":
            pay_adj = pay
        else:
            pay_adj = 0.5 * pay

        out.append(
            {
                "median": med[i],
                "floor": floor[i],
                "value": value[i],
                "sacks": sacks[i],
                "turnovers": turnovers[i],
                "opp_dropbacks": drop[i],
                "low_opp_implied": invert01(opp_imp[i]),
                "pay_up": pay_adj,
            }
        )
    return out


def linear_score(features: dict[str, float], weights: dict[str, float]) -> tuple[float, dict[str, float]]:
    """Compute a linear score plus per-feature contributions."""
    contributions: dict[str, float] = {}
    total = 0.0
    for k, w in weights.items():
        v = clamp01(features.get(k, 0.0))
        c = w * v
        contributions[k] = c
        total += c
    return total, contributions


def top_reasons(contributions: dict[str, float], *, mapping: dict[str, str], n: int = 3) -> list[str]:
    items = [(k, v) for k, v in contributions.items() if v > 0]
    items.sort(key=lambda kv: kv[1], reverse=True)
    out: list[str] = []
    for k, _ in items[:n]:
        label = mapping.get(k, k)
        out.append(label)
    return out


def apply_penalties(position: str, base_score: float, raw_row: dict[str, Any], features: dict[str, float]) -> float:
    """Apply small, explicit penalties for fragility flags.

    This mirrors the manuscript themes: avoid committees, TD-or-bust archetypes,
    and low-floor splash roles.
    """

    score = base_score

    if position == "RB":
        if features.get("committee_risk_flag", 0.0) >= 1.0:
            score -= 0.06

    if position == "WR":
        if features.get("boom_bust_flag", 0.0) >= 1.0:
            score -= 0.03

    if position == "TE":
        if features.get("td_or_bust_flag", 0.0) >= 1.0:
            score -= 0.04

    # Generic injury/nickname risk: if player is not active, demote heavily.
    status = (raw_row.get("status") or "").upper().strip()
    if status in {"O", "OUT", "IR"}:
        score -= 1.0

    return score


ReasonMappingFn = Callable[[str], dict[str, str]]


def default_reason_mapping(position: str) -> dict[str, str]:
    if position == "QB":
        return {
            "median": "Strong median projection",
            "floor": "Strong floor projection",
            "value": "Good points per dollar",
            "dropbacks": "High dropback volume",
            "rush_att": "Rushing equity",
            "gl_rush": "Goal-line rushing",
            "implied": "Strong implied team total",
            "low_pressure": "Cleaner pocket matchup",
            "low_ints": "Lower INT risk",
        }
    if position == "RB":
        return {
            "median": "Strong median projection",
            "floor": "Strong floor projection",
            "value": "Good points per dollar",
            "snaps": "High snap expectation",
            "routes": "Strong route participation",
            "targets": "Pass-game involvement",
            "gl_share": "Goal-line role",
            "hv_touches": "High-value touches",
            "favored": "Positive game script",
            "low_committee": "Clear backfield role",
        }
    if position == "WR":
        return {
            "median": "Strong median projection",
            "floor": "Strong floor projection",
            "value": "Good points per dollar",
            "routes": "Every-down routes",
            "targets": "Target volume",
            "tgt_share": "Target share",
            "low_adot": "Floor-friendly aDOT",
            "rz_targets": "Red-zone usage",
            "every_down": "Stable playing time",
            "low_boombust": "Lower volatility role",
        }
    if position == "TE":
        return {
            "median": "Strong median projection",
            "floor": "Strong floor projection",
            "value": "Good points per dollar",
            "routes": "Routes / dropbacks",
            "targets": "Target volume",
            "tgt_share": "Target share",
            "rz_targets": "Red-zone usage",
            "full_route": "Full-route role",
            "low_td_bust": "Not TD-or-bust",
        }
    if position == "DST":
        return {
            "value": "Good points per dollar",
            "sacks": "Sack expectation",
            "turnovers": "Turnover expectation",
            "opp_dropbacks": "Opponent dropback volume",
            "low_opp_implied": "Low opponent implied total",
            "pay_up": "Pay-up viable on this slate",
            "median": "Strong median projection",
            "floor": "Higher floor",
        }
    return {}
