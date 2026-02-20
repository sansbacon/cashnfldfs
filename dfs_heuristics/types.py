from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence


Position = Literal["QB", "RB", "WR", "TE", "DST"]
EntityType = Literal["PLAYER", "DST"]
Tier = Literal["must", "want", "viable", "fade"]


@dataclass(frozen=True)
class RankedEntity:
    slate_id: str
    entity_type: EntityType
    position: Position
    entity_id: str  # player_id for PLAYER, team_id for DST

    name: str
    team_id: str | None
    opp_team_id: str | None
    salary: int

    cash_score: float
    importance_score: float | None
    final_score: float

    tier: Tier
    reasons: Sequence[str]

    # Full, raw row data used to compute the score (useful for debugging/analysis)
    features: Mapping[str, Any]


@dataclass(frozen=True)
class RankingResults:
    slate_id: str
    site: str
    looseness: float
    by_position: Mapping[Position, Sequence[RankedEntity]]
