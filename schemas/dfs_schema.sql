-- DFS Heuristic Modeling Schema (portable SQL)
-- Notes:
-- - Types are chosen to work in Postgres and translate cleanly to SQLite.
-- - BOOLEAN may be stored as INTEGER (0/1) in SQLite.
-- - JSON columns are TEXT; store JSON-encoded strings.

-- =========================
-- Dimension / core entities
-- =========================

CREATE TABLE IF NOT EXISTS slate (
    slate_id            TEXT PRIMARY KEY,
    site                TEXT NOT NULL,                 -- e.g. 'DK' | 'FD'
    season              INTEGER,                       -- NFL season label (e.g. 2025)
    week                INTEGER,                       -- NFL week number
    slate_type          TEXT NOT NULL DEFAULT 'main',  -- 'main' | 'showdown' | 'single_game' | etc.
    slate_start_ts      TEXT,                          -- ISO timestamp
    timezone            TEXT,                          -- e.g. 'America/New_York'
    scoring_rules_json  TEXT,                          -- JSON: scoring + roster rules (PPR, bonuses, slots)
    salary_cap          INTEGER,                       -- optional; differs by site/slate
    created_ts          TEXT,
    updated_ts          TEXT
);

CREATE INDEX IF NOT EXISTS idx_slate_site_week ON slate(site, season, week);

CREATE TABLE IF NOT EXISTS team (
    team_id     TEXT PRIMARY KEY,   -- canonical key, typically the team abbreviation (e.g. 'BUF')
    team_name   TEXT,
    conference  TEXT,
    division    TEXT
);

CREATE TABLE IF NOT EXISTS player (
    player_id           TEXT PRIMARY KEY,   -- canonical player id (yours)
    full_name           TEXT NOT NULL,
    position            TEXT NOT NULL,       -- 'QB' | 'RB' | 'WR' | 'TE' | 'DST'
    team_id             TEXT,                -- current team (can change; slate-specific team is in player_slate)
    external_ids_json   TEXT,                -- JSON mapping to external ids (gsis, sleeper, etc.)
    active_flag         INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (team_id) REFERENCES team(team_id)
);

CREATE INDEX IF NOT EXISTS idx_player_team_pos ON player(team_id, position);

CREATE TABLE IF NOT EXISTS game (
    game_id                 TEXT PRIMARY KEY,
    slate_id                TEXT NOT NULL,
    kickoff_ts              TEXT,            -- ISO timestamp
    home_team_id            TEXT NOT NULL,
    away_team_id            TEXT NOT NULL,
    vegas_total             REAL,            -- game total
    spread_home             REAL,            -- home spread (negative = favored)
    home_implied_points     REAL,
    away_implied_points     REAL,
    neutral_pace_proj       REAL,            -- optional: plays/second or plays/game proxy
    dome_flag               INTEGER,         -- 1 if dome/closed roof
    wind_mph                REAL,
    temp_f                  REAL,
    precip_prob             REAL,
    notes                   TEXT,
    FOREIGN KEY (slate_id) REFERENCES slate(slate_id),
    FOREIGN KEY (home_team_id) REFERENCES team(team_id),
    FOREIGN KEY (away_team_id) REFERENCES team(team_id)
);

CREATE INDEX IF NOT EXISTS idx_game_slate ON game(slate_id);
CREATE INDEX IF NOT EXISTS idx_game_teams ON game(home_team_id, away_team_id);

-- ======================================
-- Player-on-slate shared projection layer
-- ======================================

CREATE TABLE IF NOT EXISTS player_slate (
    slate_id                    TEXT NOT NULL,
    player_id                   TEXT NOT NULL,

    team_id                     TEXT NOT NULL,
    opp_team_id                 TEXT NOT NULL,
    game_id                     TEXT,
    home_flag                   INTEGER,      -- 1 if player's team is home

    salary                      INTEGER NOT NULL,
    roster_positions_json       TEXT,         -- JSON array of eligible roster positions on the site

    status                      TEXT,         -- 'ACTIVE'|'Q'|'D'|'O' etc (site-agnostic)
    injury_designation          TEXT,         -- 'questionable', 'doubtful', ...

    proj_points_median          REAL NOT NULL,
    proj_points_floor           REAL,         -- e.g. p20 or p25
    proj_points_ceiling         REAL,         -- e.g. p80 or p90
    proj_ownership              REAL,         -- 0..1

    value_pts_per_1k            REAL,         -- convenience: median points / (salary/1000)

    proj_snaps                  REAL,         -- projected snaps (absolute) if available
    proj_snap_share             REAL,         -- 0..1
    proj_routes                 REAL,         -- useful for WR/TE/RB
    proj_route_share            REAL,
    proj_touches                REAL,

    projection_source           TEXT,
    projection_version          TEXT,
    features_json               TEXT,         -- JSON bag for extra shared features

    updated_ts                  TEXT,

    PRIMARY KEY (slate_id, player_id),
    FOREIGN KEY (slate_id) REFERENCES slate(slate_id),
    FOREIGN KEY (player_id) REFERENCES player(player_id),
    FOREIGN KEY (team_id) REFERENCES team(team_id),
    FOREIGN KEY (opp_team_id) REFERENCES team(team_id),
    FOREIGN KEY (game_id) REFERENCES game(game_id)
);

CREATE INDEX IF NOT EXISTS idx_player_slate_team ON player_slate(slate_id, team_id);
CREATE INDEX IF NOT EXISTS idx_player_slate_opp ON player_slate(slate_id, opp_team_id);
CREATE INDEX IF NOT EXISTS idx_player_slate_salary ON player_slate(slate_id, salary);

-- ======================
-- Position-specific tables
-- ======================

-- QB: passing/rushing composition and environment features.
CREATE TABLE IF NOT EXISTS qb_data (
    slate_id                    TEXT NOT NULL,
    player_id                   TEXT NOT NULL,

    proj_dropbacks              REAL,
    proj_pass_attempts          REAL,
    proj_completions            REAL,
    proj_pass_yards             REAL,
    proj_pass_tds               REAL,
    proj_interceptions          REAL,
    proj_sacks_taken            REAL,

    proj_rush_attempts          REAL,
    proj_designed_rush_att      REAL,
    proj_scramble_att           REAL,
    proj_rush_yards             REAL,
    proj_rush_tds               REAL,
    proj_goal_line_rush_att     REAL,

    -- Team/offense context
    team_pass_rate_neutral      REAL,     -- neutral situation pass rate
    team_no_huddle_rate         REAL,
    team_proe                   REAL,     -- pass rate over expected

    -- Matchup context
    game_total                  REAL,
    spread_home                 REAL,     -- copied from game for modeling convenience
    team_implied_points         REAL,
    opp_implied_points          REAL,

    opp_pressure_rate           REAL,
    opp_blitz_rate              REAL,

    qb_rush_upside_flag         INTEGER,  -- heuristic flag: rushing profile strong enough to matter

    features_json               TEXT,

    PRIMARY KEY (slate_id, player_id),
    FOREIGN KEY (slate_id, player_id) REFERENCES player_slate(slate_id, player_id)
);

-- RB: workload shares and high-value touches.
CREATE TABLE IF NOT EXISTS rb_data (
    slate_id                    TEXT NOT NULL,
    player_id                   TEXT NOT NULL,

    proj_rush_attempts          REAL,
    proj_rush_yards             REAL,
    proj_rush_tds               REAL,

    proj_targets                REAL,
    proj_receptions             REAL,
    proj_rec_yards              REAL,
    proj_rec_tds                REAL,

    -- Role / usage
    proj_rush_share             REAL,   -- share of team RB carries (0..1)
    proj_target_share           REAL,   -- share of team targets (0..1)
    proj_rb_target_share        REAL,   -- share of RB-room targets (0..1)
    proj_route_participation    REAL,   -- routes / team dropbacks (0..1)

    proj_goal_line_share        REAL,   -- share of goal-line carries (0..1)
    proj_two_minute_share       REAL,
    proj_third_down_share       REAL,

    proj_high_value_touches     REAL,   -- targets + goal-line carries proxy

    committee_risk_flag         INTEGER,

    game_total                  REAL,
    spread_home                 REAL,
    team_implied_points         REAL,

    features_json               TEXT,

    PRIMARY KEY (slate_id, player_id),
    FOREIGN KEY (slate_id, player_id) REFERENCES player_slate(slate_id, player_id)
);

-- WR: routes/targets, role archetype, and volatility indicators.
CREATE TABLE IF NOT EXISTS wr_data (
    slate_id                    TEXT NOT NULL,
    player_id                   TEXT NOT NULL,

    proj_targets                REAL,
    proj_receptions             REAL,
    proj_rec_yards              REAL,
    proj_rec_tds                REAL,

    proj_routes                 REAL,
    proj_route_participation    REAL,   -- routes / team dropbacks
    proj_target_share           REAL,   -- share of team targets

    proj_adot                   REAL,
    proj_air_yards              REAL,
    proj_air_yards_share        REAL,
    proj_yac_yards              REAL,

    proj_red_zone_targets       REAL,
    proj_end_zone_targets       REAL,

    slot_rate                   REAL,
    deep_target_rate            REAL,

    every_down_role_flag        INTEGER,
    boom_bust_flag              INTEGER,  -- heuristic: scoring path depends heavily on explosives

    game_total                  REAL,
    team_pass_attempts          REAL,
    team_implied_points         REAL,

    features_json               TEXT,

    PRIMARY KEY (slate_id, player_id),
    FOREIGN KEY (slate_id, player_id) REFERENCES player_slate(slate_id, player_id)
);

-- TE: similar to WR, with extra emphasis on route rate and red-zone.
CREATE TABLE IF NOT EXISTS te_data (
    slate_id                    TEXT NOT NULL,
    player_id                   TEXT NOT NULL,

    proj_targets                REAL,
    proj_receptions             REAL,
    proj_rec_yards              REAL,
    proj_rec_tds                REAL,

    proj_routes                 REAL,
    proj_route_participation    REAL,
    proj_target_share           REAL,

    proj_adot                   REAL,
    proj_air_yards              REAL,

    proj_red_zone_targets       REAL,
    proj_end_zone_targets       REAL,

    inline_rate                 REAL,    -- % snaps inline vs slot/wide (proxy for blocking/route risk)

    full_route_role_flag        INTEGER, -- 1 if expected to run routes on most dropbacks
    td_or_bust_flag             INTEGER,

    game_total                  REAL,
    team_pass_attempts          REAL,
    team_implied_points         REAL,

    features_json               TEXT,

    PRIMARY KEY (slate_id, player_id),
    FOREIGN KEY (slate_id, player_id) REFERENCES player_slate(slate_id, player_id)
);

-- D/ST uses team units rather than individual players.
CREATE TABLE IF NOT EXISTS dst_slate (
    slate_id                TEXT NOT NULL,
    team_id                 TEXT NOT NULL,   -- the defense being rostered
    opp_team_id             TEXT NOT NULL,
    game_id                 TEXT,
    home_flag               INTEGER,

    salary                  INTEGER NOT NULL,

    proj_points_median      REAL NOT NULL,
    proj_points_floor       REAL,
    proj_points_ceiling     REAL,
    proj_ownership          REAL,

    projection_source       TEXT,
    projection_version      TEXT,
    updated_ts              TEXT,

    PRIMARY KEY (slate_id, team_id),
    FOREIGN KEY (slate_id) REFERENCES slate(slate_id),
    FOREIGN KEY (team_id) REFERENCES team(team_id),
    FOREIGN KEY (opp_team_id) REFERENCES team(team_id),
    FOREIGN KEY (game_id) REFERENCES game(game_id)
);

CREATE INDEX IF NOT EXISTS idx_dst_slate_salary ON dst_slate(slate_id, salary);

CREATE TABLE IF NOT EXISTS dst_data (
    slate_id                        TEXT NOT NULL,
    team_id                         TEXT NOT NULL,

    proj_sacks                       REAL,
    proj_interceptions               REAL,
    proj_fumbles_recovered           REAL,
    proj_defensive_tds               REAL,
    proj_special_teams_tds           REAL,

    opp_dropbacks_proj               REAL,
    opp_sack_rate_allowed            REAL,
    opp_int_rate                     REAL,

    game_total                       REAL,
    spread_home                      REAL,
    opp_implied_points               REAL,

    pay_up_viable_flag               INTEGER,   -- heuristics: FD-like or elite spot

    features_json                    TEXT,

    PRIMARY KEY (slate_id, team_id),
    FOREIGN KEY (slate_id, team_id) REFERENCES dst_slate(slate_id, team_id)
);

-- ======================
-- Optional: heuristic outputs
-- ======================

CREATE TABLE IF NOT EXISTS heuristic_rank (
    slate_id            TEXT NOT NULL,
    entity_type         TEXT NOT NULL,   -- 'PLAYER' or 'DST'
    position            TEXT NOT NULL,   -- QB/RB/WR/TE/DST
    entity_id           TEXT NOT NULL,   -- player_id for PLAYER; team_id for DST

    cash_score          REAL NOT NULL,
    importance_score    REAL,
    final_score         REAL NOT NULL,

    tier                TEXT,            -- 'must'|'want'|'viable'|'fade'
    reasons_json        TEXT,            -- JSON array of short strings

    created_ts          TEXT,

    PRIMARY KEY (slate_id, entity_type, entity_id)
);
