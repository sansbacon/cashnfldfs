"""DFS heuristic ranking library.

This package computes cash-oriented heuristic scores by position (QB/RB/WR/TE/DST)
from the tables defined in schemas/dfs_schema.sql.

Entry points:
- rank_slate_positions(conn, slate_id, ...)
- write_rankings(conn, rankings, ...)

The library is intentionally lightweight (no CLI, minimal dependencies).
"""

from .api import rank_slate_positions, write_rankings
from .types import RankedEntity, RankingResults

__all__ = [
    "rank_slate_positions",
    "write_rankings",
    "RankedEntity",
    "RankingResults",
]
