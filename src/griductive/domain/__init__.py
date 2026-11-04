"""Domain module for Griductive.

Contains core entities, value objects, board geometry, and independent semantics.
"""

from griductive.domain.model import (
    AtLeastClue,
    AtMostClue,
    CellId,
    Character,
    Clue,
    ColRegion,
    CommonNeighborsRegion,
    DifferentClue,
    ExactlyClue,
    ExplicitRegion,
    FactClue,
    NeighborsRegion,
    Parity,
    ParityClue,
    PublicCard,
    PublicState,
    Puzzle,
    RegionExpr,
    RowRegion,
    SameClue,
    Status,
    Verdict,
)
from griductive.domain.regions import get_clue_highlight_cells, resolve_region
from griductive.domain.semantics import (
    evaluate_cardinality,
    evaluate_clue,
    evaluate_different,
    evaluate_fact,
    evaluate_parity,
    evaluate_same,
)

__all__ = [
    # Model
    "CellId",
    "Character",
    "Status",
    "Verdict",
    "RegionExpr",
    "RowRegion",
    "ColRegion",
    "NeighborsRegion",
    "ExplicitRegion",
    "CommonNeighborsRegion",
    "Clue",
    "FactClue",
    "SameClue",
    "DifferentClue",
    "AtMostClue",
    "AtLeastClue",
    "ExactlyClue",
    "Parity",
    "ParityClue",
    "PublicCard",
    "PublicState",
    "Puzzle",
    # Regions
    "resolve_region",
    "get_clue_highlight_cells",
    # Semantics
    "evaluate_clue",
    "evaluate_fact",
    "evaluate_same",
    "evaluate_different",
    "evaluate_cardinality",
    "evaluate_parity",
]
