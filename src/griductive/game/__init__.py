"""Game module for Griductive.

Contains the game engine (holding private truth), JSON loader, and gameplay controller.
"""

from griductive.game.controller import (
    AutoSolveReport,
    AutoSolveStatus,
    CallResult,
    DeductionStep,
    GameController,
    Hint,
    RejectionReason,
)
from griductive.game.engine import GameEngine
from griductive.game.io import (
    PUZZLE_SCHEMA_VERSION,
    load_puzzle_from_dict,
    load_puzzle_from_json,
    validate_puzzle_data,
)

__all__ = [
    # Engine
    "GameEngine",
    # IO
    "PUZZLE_SCHEMA_VERSION",
    "load_puzzle_from_dict",
    "load_puzzle_from_json",
    "validate_puzzle_data",
    # Controller
    "RejectionReason",
    "CallResult",
    "Hint",
    "DeductionStep",
    "AutoSolveStatus",
    "AutoSolveReport",
    "GameController",
]
