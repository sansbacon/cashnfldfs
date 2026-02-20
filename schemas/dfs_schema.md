# DFS Heuristic Algorithm — Data Schemas

Goal: make it easy to compute “cash-style” heuristics (floor, fragility, separation) and then rank best plays by position for a given slate/site.

This schema is intentionally split into:
- **Shared** tables (`slate`, `game`, `player`, `team`, `player_slate`) that every position uses.
- **Position** tables (`qb_data`, `rb_data`, `wr_data`, `te_data`, `dst_slate`, `dst_data`) that hold the features you actually need for heuristics.

All `*_json` columns are JSON-encoded strings.

---

## 1) Core tables

### `slate`
One row per slate (site + week + slate type).

**Primary key:** `slate_id`

**Columns**
- `slate_id` (TEXT): Your canonical slate identifier.
- `site` (TEXT): DFS site (e.g., `DK`, `FD`).
- `season` (INTEGER): NFL season label (e.g., 2025).
- `week` (INTEGER): NFL week number.
- `slate_type` (TEXT): `main`, `showdown`, etc.
- `slate_start_ts` (TEXT): ISO timestamp for first lock.
- `timezone` (TEXT): Timezone used for timestamps.
- `scoring_rules_json` (TEXT): Roster/scoring settings (PPR, bonuses, roster slots).
- `salary_cap` (INTEGER): Optional; helpful for multiple slate types.
- `created_ts` / `updated_ts` (TEXT): Metadata.

Why this matters for heuristics: your “tight vs loose slate” logic depends on site rules and pricing behavior.

---

### `team`
Canonical team dimension.

**Primary key:** `team_id`

**Columns**
- `team_id` (TEXT): Team abbreviation (e.g., `BUF`).
- `team_name` (TEXT): Full name.
- `conference` / `division` (TEXT): Optional metadata.

---

### `player`
Canonical player dimension.

**Primary key:** `player_id`

**Columns**
- `player_id` (TEXT): Your internal ID.
- `full_name` (TEXT): Display name.
- `position` (TEXT): `QB`, `RB`, `WR`, `TE`, `DST`.
- `team_id` (TEXT): Current team (slate-specific team goes in `player_slate`).
- `external_ids_json` (TEXT): Mapping to external identifiers.
- `active_flag` (INTEGER): 1/0.

---

### `game`
One row per game on a slate.

**Primary key:** `game_id`

**Foreign keys:** `slate_id`, `home_team_id`, `away_team_id`

**Columns**
- `slate_id` (TEXT): Slate.
- `kickoff_ts` (TEXT): ISO timestamp.
- `home_team_id` / `away_team_id` (TEXT): Teams.
- `vegas_total` (REAL): Game total.
- `spread_home` (REAL): Home spread (negative means home favorite).
- `home_implied_points` / `away_implied_points` (REAL): Derived/ingested.
- `neutral_pace_proj` (REAL): Optional pace proxy.
- `dome_flag` (INTEGER): 1 if dome/closed roof.
- `wind_mph` / `temp_f` / `precip_prob` (REAL): Weather inputs.
- `notes` (TEXT): Freeform.

Why this matters: game totals, pace, and weather are often “context not foundation” — but they are useful tie-breakers.

---

### `player_slate`
Shared player-on-slate layer (salary + projection summaries + shared usage). Position tables extend this.

**Primary key:** `(slate_id, player_id)`

**Foreign keys:** `slate_id`, `player_id`, `team_id`, `opp_team_id`, `game_id`

**Columns**
- Identity
  - `slate_id` (TEXT)
  - `player_id` (TEXT)
  - `team_id` / `opp_team_id` (TEXT)
  - `game_id` (TEXT)
  - `home_flag` (INTEGER)
- Salary / roster rules
  - `salary` (INTEGER)
  - `roster_positions_json` (TEXT): Eligible slots.
- Availability
  - `status` (TEXT): Active/Q/D/O etc.
  - `injury_designation` (TEXT): Questionable/Doubtful/Out etc.
- Projections
  - `proj_points_median` (REAL): Median projection.
  - `proj_points_floor` (REAL): Lower percentile (p20/p25).
  - `proj_points_ceiling` (REAL): Upper percentile (p80/p90).
  - `proj_ownership` (REAL): 0..1.
  - `value_pts_per_1k` (REAL): Convenience.
- Shared usage
  - `proj_snaps` (REAL)
  - `proj_snap_share` (REAL)
  - `proj_routes` (REAL)
  - `proj_route_share` (REAL)
  - `proj_touches` (REAL)
- Lineage
  - `projection_source` / `projection_version` (TEXT)
  - `features_json` (TEXT): Any extra shared features.
  - `updated_ts` (TEXT)

Why this matters: this table lets you rank *anything* quickly without joining multiple sources, while still letting you store deeper features by position.

---

## 2) Position tables

### `qb_data`
QB-specific features used for “rushing equity + dropbacks + environment.”

**Primary key / FK:** `(slate_id, player_id)` references `player_slate`.

**Columns**
- Passing volume/efficiency projections
  - `proj_dropbacks` (REAL)
  - `proj_pass_attempts` (REAL)
  - `proj_completions` (REAL)
  - `proj_pass_yards` (REAL)
  - `proj_pass_tds` (REAL)
  - `proj_interceptions` (REAL)
  - `proj_sacks_taken` (REAL)
- Rushing equity
  - `proj_rush_attempts` (REAL)
  - `proj_designed_rush_att` (REAL)
  - `proj_scramble_att` (REAL)
  - `proj_rush_yards` (REAL)
  - `proj_rush_tds` (REAL)
  - `proj_goal_line_rush_att` (REAL)
- Team tendencies
  - `team_pass_rate_neutral` (REAL)
  - `team_no_huddle_rate` (REAL)
  - `team_proe` (REAL)
- Matchup context (copied for modeling convenience)
  - `game_total` (REAL)
  - `spread_home` (REAL)
  - `team_implied_points` / `opp_implied_points` (REAL)
  - `opp_pressure_rate` / `opp_blitz_rate` (REAL)
- Heuristic flags
  - `qb_rush_upside_flag` (INTEGER): 1 if the QB’s rushing profile is meaningful.
- `features_json` (TEXT): Extra inputs (e.g., weapon consolidation index).

Typical cash heuristics supported:
- “Dual threat separation” (rush attempts + GL rush).
- “High-volume passer” (dropbacks + pace + implied points).

---

### `rb_data`
RB workload is the core cash driver: snaps + routes + targets + goal-line.

**Primary key / FK:** `(slate_id, player_id)` references `player_slate`.

**Columns**
- Production projections
  - `proj_rush_attempts`, `proj_rush_yards`, `proj_rush_tds` (REAL)
  - `proj_targets`, `proj_receptions`, `proj_rec_yards`, `proj_rec_tds` (REAL)
- Role shares
  - `proj_rush_share` (REAL): share of RB carries.
  - `proj_target_share` (REAL): share of all team targets.
  - `proj_rb_target_share` (REAL): share of RB-room targets.
  - `proj_route_participation` (REAL): routes/team dropbacks.
- High-value usage
  - `proj_goal_line_share` (REAL)
  - `proj_two_minute_share` (REAL)
  - `proj_third_down_share` (REAL)
  - `proj_high_value_touches` (REAL): targets + GL carries proxy.
- Risk
  - `committee_risk_flag` (INTEGER)
- Matchup convenience
  - `game_total`, `spread_home`, `team_implied_points` (REAL)
- `features_json` (TEXT)

Typical cash heuristics supported:
- “Three-down + goal-line” archetype.
- Penalizing ambiguous committees.

---

### `wr_data`
WR cash heuristics emphasize every-down routes + targets, not “needs a bomb.”

**Primary key / FK:** `(slate_id, player_id)` references `player_slate`.

**Columns**
- Production projections
  - `proj_targets`, `proj_receptions`, `proj_rec_yards`, `proj_rec_tds` (REAL)
- Role and volume stability
  - `proj_routes` (REAL)
  - `proj_route_participation` (REAL)
  - `proj_target_share` (REAL)
- Profile / volatility drivers
  - `proj_adot` (REAL)
  - `proj_air_yards` / `proj_air_yards_share` (REAL)
  - `proj_yac_yards` (REAL)
  - `proj_red_zone_targets` / `proj_end_zone_targets` (REAL)
  - `slot_rate` (REAL)
  - `deep_target_rate` (REAL)
- Heuristic flags
  - `every_down_role_flag` (INTEGER)
  - `boom_bust_flag` (INTEGER)
- Team context
  - `game_total` (REAL)
  - `team_pass_attempts` (REAL)
  - `team_implied_points` (REAL)
- `features_json` (TEXT)

---

### `te_data`
TE cash heuristics emphasize route participation and “not a rotational blocker.”

**Primary key / FK:** `(slate_id, player_id)` references `player_slate`.

**Columns**
- Production projections
  - `proj_targets`, `proj_receptions`, `proj_rec_yards`, `proj_rec_tds` (REAL)
- Route / target role
  - `proj_routes` (REAL)
  - `proj_route_participation` (REAL)
  - `proj_target_share` (REAL)
- Profile
  - `proj_adot` (REAL)
  - `proj_air_yards` (REAL)
  - `proj_red_zone_targets` / `proj_end_zone_targets` (REAL)
  - `inline_rate` (REAL): proxy for blocking/route risk.
- Heuristic flags
  - `full_route_role_flag` (INTEGER)
  - `td_or_bust_flag` (INTEGER)
- Team context
  - `game_total`, `team_pass_attempts`, `team_implied_points` (REAL)
- `features_json` (TEXT)

---

### `dst_slate` and `dst_data`
D/ST is modeled as a **team unit**.

`dst_slate` stores the shared “salary + projection summary” layer analogous to `player_slate`.

**Primary key:** `(slate_id, team_id)`

**`dst_slate` columns**
- `slate_id` (TEXT)
- `team_id` (TEXT): the rostered defense.
- `opp_team_id` (TEXT)
- `game_id` (TEXT)
- `home_flag` (INTEGER)
- `salary` (INTEGER)
- `proj_points_median` / `proj_points_floor` / `proj_points_ceiling` (REAL)
- `proj_ownership` (REAL)
- `projection_source` / `projection_version` (TEXT)
- `updated_ts` (TEXT)

`dst_data` stores the sack/turnover drivers used in heuristics.

**Primary key / FK:** `(slate_id, team_id)` references `dst_slate`.

**`dst_data` columns**
- Direct component projections
  - `proj_sacks` (REAL)
  - `proj_interceptions` (REAL)
  - `proj_fumbles_recovered` (REAL)
  - `proj_defensive_tds` (REAL)
  - `proj_special_teams_tds` (REAL)
- Opponent drivers
  - `opp_dropbacks_proj` (REAL)
  - `opp_sack_rate_allowed` (REAL)
  - `opp_int_rate` (REAL)
- Convenience context
  - `game_total` (REAL)
  - `spread_home` (REAL)
  - `opp_implied_points` (REAL)
- Heuristic flags
  - `pay_up_viable_flag` (INTEGER): for FD-like slates or elite mismatch spots.
- `features_json` (TEXT)

---

## 3) Optional outputs

### `heuristic_rank`
Stores your algorithm’s outputs per slate.

**Primary key:** `(slate_id, entity_type, entity_id)`

**Columns**
- `entity_type` (TEXT): `PLAYER` or `DST`.
- `position` (TEXT): `QB/RB/WR/TE/DST`.
- `entity_id` (TEXT): `player_id` for players, `team_id` for DST.
- `cash_score` (REAL): floor/role-driven score.
- `importance_score` (REAL): “makes the optimal lineup work” score.
- `final_score` (REAL): blended ranking score.
- `tier` (TEXT): `must` / `want` / `viable` / `fade`.
- `reasons_json` (TEXT): short explanations.

---

## Implementation notes (so this stays practical)
- Keep projection lineage fields (`projection_source`, `projection_version`) so you can compare runs.
- Use `features_json` as an escape hatch so you don’t churn schemas.
- If you later want stricter typing for JSON, you can migrate to native JSON columns in Postgres.
