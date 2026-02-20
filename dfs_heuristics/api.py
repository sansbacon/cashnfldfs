from __future__ import annotations

import json
from typing import Any

from . import db
from .normalize import clamp01, percentile_rank
from .scoring import (
    apply_penalties,
    build_features_dst,
    build_features_qb,
    build_features_rb,
    build_features_te,
    build_features_wr,
    default_reason_mapping,
    linear_score,
    top_reasons,
)
from .tiering import assign_tier
from .types import RankedEntity, RankingResults
from .weights import default_weight_profiles


def _estimate_looseness(conn, slate_id: str) -> float:
    rows = db.fetch_all(
        conn,
        """
        SELECT proj_points_median, salary
        FROM player_slate
        WHERE slate_id = ?
          AND status NOT IN ('O','OUT','IR')
          AND salary IS NOT NULL
        """,
        [slate_id],
    )
    if not rows:
        return 0.5

    # Derive pts per 1k to avoid relying on value_pts_per_1k.
    vals: list[float | None] = []
    for r in rows:
        pts = r.get("proj_points_median")
        sal = r.get("salary")
        if pts is None or sal is None:
            vals.append(None)
            continue
        try:
            sal = float(sal)
            pts = float(pts)
        except Exception:
            vals.append(None)
            continue
        if sal <= 0:
            vals.append(None)
            continue
        vals.append(pts / (sal / 1000.0))

    prs = percentile_rank(vals)

    # How many players are in the top value band? More -> looser pricing.
    high = sum(1 for p in prs if p >= 0.80)
    # Map count to 0..1 with conservative scaling.
    # Typical main slate might have ~15-30 "real" value plays; tune later.
    looseness = (high - 12) / 24.0
    return clamp01(looseness)


def _get_slate_site(conn, slate_id: str) -> str:
    row = db.fetch_one(conn, "SELECT site FROM slate WHERE slate_id = ?", [slate_id])
    if not row or not row.get("site"):
        return "DK"
    return str(row["site"]).upper()


def rank_slate_positions(
    conn,
    slate_id: str,
    *,
    max_per_position: int | None = 30,
) -> RankingResults:
    """Compute ranked heuristic lists for QB/RB/WR/TE/DST.

    Parameters
    - conn: DB-API connection (qmark style, e.g. sqlite3).
    - slate_id: slate identifier.
    - max_per_position: cap results returned per position.

    Returns
    - RankingResults with per-position RankedEntity sequences.

    This function does not write to the database.
    Use write_rankings(...) if you want persistence to heuristic_rank.
    """

    site = _get_slate_site(conn, slate_id)
    looseness = _estimate_looseness(conn, slate_id)

    profiles = default_weight_profiles()

    by_position: dict[str, list[RankedEntity]] = {}

    # ---- Players (QB/RB/WR/TE) ----
    for pos in ("QB", "RB", "WR", "TE"):
        rows = db.fetch_all(
            conn,
            f"""
            SELECT
                ps.slate_id,
                ps.player_id,
                p.full_name AS name,
                ps.team_id,
                ps.opp_team_id,
                ps.salary,
                ps.status,
                ps.injury_designation,
                ps.proj_points_median,
                ps.proj_points_floor,
                ps.proj_points_ceiling,
                ps.value_pts_per_1k,
                ps.proj_snaps,
                ps.proj_routes,
                ps.proj_route_share,
                ps.proj_touches,
                -- Position table columns (may be NULL)
                t.*
            FROM player_slate ps
            JOIN player p ON p.player_id = ps.player_id
            LEFT JOIN {pos.lower()}_data t
              ON t.slate_id = ps.slate_id AND t.player_id = ps.player_id
            WHERE ps.slate_id = ?
              AND p.position = ?
              AND COALESCE(ps.status,'') NOT IN ('O','OUT','IR')
            """,
            [slate_id, pos],
        )

        if not rows:
            by_position[pos] = []
            continue

        # Build normalized features
        if pos == "QB":
            feats = build_features_qb(rows)
        elif pos == "RB":
            feats = build_features_rb(rows)
        elif pos == "WR":
            feats = build_features_wr(rows)
        else:
            feats = build_features_te(rows)

        prof = profiles[pos]
        weights = {
            k: (1.0 - looseness) * prof.tight.weights.get(k, 0.0)
            + looseness * prof.loose.weights.get(k, 0.0)
            for k in set(prof.tight.weights) | set(prof.loose.weights)
        }

        reason_map = default_reason_mapping(pos)

        scored: list[tuple[float, float, dict[str, float], list[str], dict[str, Any]]] = []
        for row, f in zip(rows, feats):
            base, contrib = linear_score(f, weights)
            base = apply_penalties(pos, base, row, f)

            # Small explicit bonus for QB rushing profile (if provided).
            if pos == "QB" and f.get("qb_rush_upside_flag", 0.0) >= 1.0:
                base += 0.02

            reasons = top_reasons(contrib, mapping=reason_map, n=3)
            scored.append((base, base, contrib, reasons, row))

        # Sort best-first.
        scored.sort(key=lambda t: t[0], reverse=True)

        final_scores = [t[0] for t in scored]
        tiers = assign_tier(final_scores, looseness=looseness)

        out: list[RankedEntity] = []
        for rank, ((final_score, cash_score, contrib, reasons, row), tier) in enumerate(
            zip(scored, tiers), start=1
        ):
            ent = RankedEntity(
                slate_id=slate_id,
                entity_type="PLAYER",
                position=pos,  # type: ignore[arg-type]
                entity_id=str(row.get("player_id")),
                name=str(row.get("name") or ""),
                team_id=str(row.get("team_id") or "") or None,
                opp_team_id=str(row.get("opp_team_id") or "") or None,
                salary=int(row.get("salary") or 0),
                cash_score=float(cash_score),
                importance_score=None,
                final_score=float(final_score),
                tier=tier,  # type: ignore[arg-type]
                reasons=reasons,
                features={**row, "_contrib": contrib},
            )
            out.append(ent)
            if max_per_position is not None and len(out) >= max_per_position:
                break

        by_position[pos] = out

    # ---- DST ----
    dst_rows = db.fetch_all(
        conn,
        """
        SELECT
            ds.slate_id,
            ds.team_id,
            t.team_name AS name,
            ds.opp_team_id,
            ds.salary,
            ds.proj_points_median,
            ds.proj_points_floor,
            ds.proj_points_ceiling,
            dd.proj_sacks,
            dd.proj_interceptions,
            dd.proj_fumbles_recovered,
            dd.opp_dropbacks_proj,
            dd.opp_implied_points,
            dd.pay_up_viable_flag
        FROM dst_slate ds
        JOIN team t ON t.team_id = ds.team_id
        LEFT JOIN dst_data dd
          ON dd.slate_id = ds.slate_id AND dd.team_id = ds.team_id
        WHERE ds.slate_id = ?
        """,
        [slate_id],
    )

    if dst_rows:
        feats = build_features_dst(dst_rows, site=site)
        prof = profiles["DST"]
        weights = {
            k: (1.0 - looseness) * prof.tight.weights.get(k, 0.0)
            + looseness * prof.loose.weights.get(k, 0.0)
            for k in set(prof.tight.weights) | set(prof.loose.weights)
        }
        reason_map = default_reason_mapping("DST")

        scored_dst: list[tuple[float, dict[str, float], list[str], dict[str, Any]]] = []
        for row, f in zip(dst_rows, feats):
            base, contrib = linear_score(f, weights)
            reasons = top_reasons(contrib, mapping=reason_map, n=3)

            # Site nuance: on DK, apply a mild pay-down preference; on FD, less so.
            try:
                sal = int(row.get("salary") or 0)
            except Exception:
                sal = 0
            if site == "DK" and sal >= 3800:
                base -= 0.04
            if site == "FD" and sal >= 4800:
                base -= 0.02

            scored_dst.append((base, contrib, reasons, row))

        scored_dst.sort(key=lambda t: t[0], reverse=True)
        final_scores = [t[0] for t in scored_dst]
        tiers = assign_tier(final_scores, looseness=looseness)

        out_dst: list[RankedEntity] = []
        for (final_score, contrib, reasons, row), tier in zip(scored_dst, tiers):
            out_dst.append(
                RankedEntity(
                    slate_id=slate_id,
                    entity_type="DST",
                    position="DST",
                    entity_id=str(row.get("team_id")),
                    name=str(row.get("name") or ""),
                    team_id=str(row.get("team_id") or "") or None,
                    opp_team_id=str(row.get("opp_team_id") or "") or None,
                    salary=int(row.get("salary") or 0),
                    cash_score=float(final_score),
                    importance_score=None,
                    final_score=float(final_score),
                    tier=tier,  # type: ignore[arg-type]
                    reasons=reasons,
                    features={**row, "_contrib": contrib},
                )
            )
            if max_per_position is not None and len(out_dst) >= max_per_position:
                break

        by_position["DST"] = out_dst
    else:
        by_position["DST"] = []

    return RankingResults(
        slate_id=slate_id,
        site=site,
        looseness=looseness,
        by_position=by_position,  # type: ignore[arg-type]
    )


def write_rankings(
    conn,
    rankings: RankingResults,
    *,
    replace: bool = True,
) -> None:
    """Persist rankings into heuristic_rank.

    This is optional; you can also just use the returned RankingResults.

    Notes:
    - Uses SQLite-style UPSERT. If you are not on SQLite, you may need to adapt.
    """

    if replace:
        cur = conn.cursor()
        cur.execute("DELETE FROM heuristic_rank WHERE slate_id = ?", (rankings.slate_id,))
        conn.commit()

    cur = conn.cursor()

    def _insert(e):
        reasons_json = json.dumps(list(e.reasons))
        cur.execute(
            """
            INSERT INTO heuristic_rank (
                slate_id, entity_type, position, entity_id,
                cash_score, importance_score, final_score,
                tier, reasons_json, created_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                e.slate_id,
                e.entity_type,
                e.position,
                e.entity_id,
                float(e.cash_score),
                float(e.importance_score) if e.importance_score is not None else None,
                float(e.final_score),
                e.tier,
                reasons_json,
            ),
        )

    for pos, ents in rankings.by_position.items():
        for e in ents:
            _insert(e)

    conn.commit()
