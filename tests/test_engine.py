"""Unit tests for GameEngine state transitions, public/private boundary, and error isolation."""

from pathlib import Path

import pytest

from griductive.game.engine import GameEngine
from griductive.game.io import load_puzzle_from_json
from griductive.domain.model import CellId, Status


@pytest.fixture
def valid_puzzle():
    """Load valid 3x3 puzzle instance."""
    fixture_path = Path("tests/fixtures/puzzle_3x3_valid.json")
    return load_puzzle_from_json(fixture_path)


def test_engine_init_type_check():
    """Verify non-Puzzle raises TypeError."""
    with pytest.raises(TypeError, match="must be a Puzzle instance"):
        GameEngine({"not": "a puzzle"})  # type: ignore


def test_engine_initial_state(valid_puzzle):
    """Verify engine initial state exposes only initial face-up cards."""
    engine = GameEngine(valid_puzzle)

    assert engine.grid_size == 3
    assert engine.revision == 0
    assert not engine.is_solved

    state = engine.public_state
    assert state.grid_size == 3
    assert state.revision == 0
    assert state.revealed_cells == frozenset({CellId("A1"), CellId("B2")})

    # Characters sorted alphabetically by name
    names = [c.name for c in state.characters]
    assert names == sorted(names)

    # Initial face-up cards are revealed
    card_a1 = state.cards[CellId("A1")]
    assert card_a1.is_revealed is True
    assert card_a1.status == Status.CRIMINAL
    assert card_a1.clue is not None
    assert card_a1.clue.owner == CellId("A1")

    card_b2 = state.cards[CellId("B2")]
    assert card_b2.is_revealed is True
    assert card_b2.status == Status.CRIMINAL
    assert card_b2.clue is not None

    # Face-down cards must not expose status or clue
    face_down_cells = [
        CellId("B1"),
        CellId("C1"),
        CellId("A2"),
        CellId("C2"),
        CellId("A3"),
        CellId("B3"),
        CellId("C3"),
    ]
    for cell in face_down_cells:
        card = state.cards[cell]
        assert card.is_revealed is False
        assert card.status is None
        assert card.clue is None
        assert cell not in state.known_statuses

    assert frozenset(state.known_statuses.keys()) == state.revealed_cells
    assert len(state.revealed_clues) == 2
    # Clues ordered deterministically by owner cell
    assert [c.owner for c in state.revealed_clues] == [CellId("A1"), CellId("B2")]


def test_engine_aliases(valid_puzzle):
    """Verify public_state, get_public_state(), and public_view() return identical states."""
    engine = GameEngine(valid_puzzle)
    s1 = engine.public_state
    s2 = engine.get_public_state()
    s3 = engine.public_view()

    assert s1 == s2 == s3


def test_valid_reveal_advances_state(valid_puzzle):
    """Verify valid reveal exposes card, increments revision, and updates public state."""
    engine = GameEngine(valid_puzzle)
    initial_revision = engine.revision
    assert initial_revision == 0

    # Bob at B1 is INNOCENT
    status, clue = engine._reveal_proven(CellId("B1"), Status.INNOCENT)

    assert status == Status.INNOCENT
    assert clue.owner == CellId("B1")
    assert engine.revision == 1

    state = engine.public_state
    assert state.revision == 1
    assert CellId("B1") in state.revealed_cells
    assert state.cards[CellId("B1")].is_revealed is True
    assert state.cards[CellId("B1")].status == Status.INNOCENT
    assert state.cards[CellId("B1")].clue == clue
    assert state.known_statuses[CellId("B1")] == Status.INNOCENT
    assert clue in state.revealed_clues


def test_reveal_with_strings(valid_puzzle):
    """Verify reveal supports string cell coordinate and string status verdict."""
    engine = GameEngine(valid_puzzle)

    # Charlie at C1 is CRIMINAL
    status, clue = engine._reveal_proven("C1", "CRIMINAL")
    assert status == Status.CRIMINAL
    assert clue.owner == CellId("C1")
    assert engine.revision == 1


def test_rejected_reveal_wrong_verdict_leaves_state_unchanged(valid_puzzle):
    """Verify wrong verdict raises ValueError and CRITICALLY leaves state and revision unchanged."""
    engine = GameEngine(valid_puzzle)
    rev_before = engine.revision
    cells_before = set(engine.public_state.revealed_cells)
    state_before = engine.public_state

    # David at A2 is INNOCENT; propose CRIMINAL (wrong!)
    with pytest.raises(ValueError, match="cannot be committed") as exc_info:
        engine._reveal_proven(CellId("A2"), Status.CRIMINAL)
    assert Status.INNOCENT.value not in str(exc_info.value)
    assert Status.CRIMINAL.value not in str(exc_info.value)

    # Assert completely untouched
    assert engine.revision == rev_before
    assert engine.public_state.revealed_cells == cells_before
    assert engine.public_state == state_before


def test_reveal_already_revealed_cell_raises(valid_puzzle):
    """Verify attempting to reveal an already revealed card raises ValueError and mutates nothing."""
    engine = GameEngine(valid_puzzle)
    rev_before = engine.revision

    # A1 is already face-up
    with pytest.raises(ValueError, match="already been revealed"):
        engine._reveal_proven(CellId("A1"), Status.CRIMINAL)

    assert engine.revision == rev_before


def test_reveal_invalid_cell_raises(valid_puzzle):
    """Verify out-of-bounds or non-existent cell raises ValueError."""
    engine = GameEngine(valid_puzzle)
    rev_before = engine.revision

    with pytest.raises(ValueError, match="out of bounds"):
        engine._reveal_proven(CellId("D4"), Status.INNOCENT)

    with pytest.raises(ValueError, match="Invalid cell coordinate format"):
        engine._reveal_proven("BAD_COORD", Status.INNOCENT)

    with pytest.raises(TypeError, match="cell must be CellId or str"):
        engine._reveal_proven(999, Status.INNOCENT)  # type: ignore

    assert engine.revision == rev_before


def test_reveal_invalid_verdict_type_raises(valid_puzzle):
    """Verify invalid verdict string or type raises ValueError/TypeError."""
    engine = GameEngine(valid_puzzle)
    rev_before = engine.revision

    with pytest.raises(ValueError, match="Invalid status verdict"):
        engine._reveal_proven(CellId("B1"), "MAYBE")

    with pytest.raises(TypeError, match="verdict must be Status or str"):
        engine._reveal_proven(CellId("B1"), 123)  # type: ignore

    assert engine.revision == rev_before


def test_solve_and_restart(valid_puzzle):
    """Verify full reveal path solves puzzle, and restart restores initial view."""
    engine = GameEngine(valid_puzzle)

    assert not engine.is_solved

    # Remaining 7 cards:
    # B1: INNOCENT, C1: CRIMINAL, A2: INNOCENT, C2: INNOCENT, A3: CRIMINAL, B3: INNOCENT, C3: INNOCENT
    moves = [
        ("B1", Status.INNOCENT),
        ("C1", Status.CRIMINAL),
        ("A2", Status.INNOCENT),
        ("C2", Status.INNOCENT),
        ("A3", Status.CRIMINAL),
        ("B3", Status.INNOCENT),
        ("C3", Status.INNOCENT),
    ]

    for cell_str, verdict in moves:
        engine._reveal_proven(cell_str, verdict)

    assert engine.revision == 7
    assert engine.is_solved is True

    # In solved state, all cards are revealed
    state = engine.public_state
    for card in state.cards.values():
        assert card.is_revealed is True
        assert card.status is not None
        assert card.clue is not None

    # Restart restoring initial state
    restarted_state = engine.restart()
    assert engine.revision == 0
    assert not engine.is_solved
    assert engine.public_state.revealed_cells == frozenset({CellId("A1"), CellId("B2")})
    assert restarted_state == engine.public_state

    # Previously revealed cards are once again face-down
    assert restarted_state.cards[CellId("B1")].is_revealed is False
    assert restarted_state.cards[CellId("B1")].status is None
    assert restarted_state.cards[CellId("B1")].clue is None
