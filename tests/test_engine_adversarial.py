"""Adversarial stress tests for GameEngine boundary security and state lifecycle.

Probing:
1. Public/private boundary leakage (attempting to reach hidden solution, unrevealed clues).
2. Deep immutability of PublicState, CardState, and engine properties.
3. Strict invariant that unrevealed cards expose strictly None for status and clue.
4. Engine state and revision isolation under rejected/invalid reveal actions.
5. Lifecycle transitions: sequential reveals to solved, actions after solved, restart.
6. Multi-instance isolation on shared Puzzle models.
"""

from pathlib import Path
import pytest

from griductive.game.engine import GameEngine
from griductive.game.io import load_puzzle_from_json
from griductive.domain.model import (
    CellId,
    Character,
    FactClue,
    PublicCard,
    Puzzle,
    Status,
)


@pytest.fixture
def puzzle_3x3() -> Puzzle:
    fixture_path = Path("tests/fixtures/puzzle_3x3_valid.json")
    return load_puzzle_from_json(fixture_path)


# ============================================================================
# 1. Boundary Testing: Private Data Leakage Probes
# ============================================================================


def test_public_state_has_no_puzzle_or_solution_attributes(puzzle_3x3):
    """Verify PublicState does not expose _puzzle, puzzle, or solution."""
    engine = GameEngine(puzzle_3x3)
    state = engine.public_state

    # Direct attributes inspection
    public_attrs = [attr for attr in dir(state) if not attr.startswith("__")]
    assert "_puzzle" not in public_attrs
    assert "puzzle" not in public_attrs
    assert "solution" not in public_attrs
    assert "_solution" not in public_attrs

    # Check that cards do not hold references to puzzle or solution
    for cell, card in state.cards.items():
        card_attrs = [attr for attr in dir(card) if not attr.startswith("__")]
        assert "_puzzle" not in card_attrs
        assert "puzzle" not in card_attrs
        assert "solution" not in card_attrs


def test_unrevealed_cards_strictly_expose_none(puzzle_3x3):
    """Verify face-down cards expose strictly None for status and clue."""
    engine = GameEngine(puzzle_3x3)
    state = engine.public_state

    unrevealed_cells = set(state.cards.keys()) - state.revealed_cells
    assert len(unrevealed_cells) == 7

    for cell in unrevealed_cells:
        card = state.cards[cell]
        assert card.is_revealed is False
        assert card.status is None
        assert card.clue is None
        assert cell not in state.known_statuses


def test_revealed_clues_tuple_contains_only_face_up_clues(puzzle_3x3):
    """Verify revealed_clues only includes clues belonging to revealed cards."""
    engine = GameEngine(puzzle_3x3)
    state = engine.public_state

    revealed_cells = state.revealed_cells
    assert len(state.revealed_clues) == len(revealed_cells)

    for clue in state.revealed_clues:
        assert clue.owner in revealed_cells
        # Hidden clues from unrevealed cards must NOT be in revealed_clues
        assert clue.owner not in (set(state.cards.keys()) - revealed_cells)


def test_public_card_invariant_enforcement():
    """Verify PublicCard __post_init__ prevents illegal combinations."""
    char = Character(cell=CellId("A1"), name="Alice", profession="Detective")
    clue = FactClue(clue_id="C_A1", owner=CellId("A1"), target=CellId("B1"), status=Status.CRIMINAL)

    # Cannot have is_revealed=False with status or clue
    with pytest.raises(ValueError, match="Face-down card at .* must not expose status or clue"):
        PublicCard(cell=CellId("A1"), character=char, is_revealed=False, status=Status.CRIMINAL)

    with pytest.raises(ValueError, match="Face-down card at .* must not expose status or clue"):
        PublicCard(cell=CellId("A1"), character=char, is_revealed=False, clue=clue)

    # Cannot have is_revealed=True with missing status or clue
    with pytest.raises(ValueError, match="Revealed card at .* must have both status and clue"):
        PublicCard(cell=CellId("A1"), character=char, is_revealed=True, status=Status.CRIMINAL, clue=None)

    with pytest.raises(ValueError, match="Revealed card at .* must have both status and clue"):
        PublicCard(cell=CellId("A1"), character=char, is_revealed=True, status=None, clue=clue)


# ============================================================================
# 2. Immutability Testing
# ============================================================================


def test_public_state_mutation_attempts_fail(puzzle_3x3):
    """Verify PublicState, mappings, tuples, and frozensets are deeply immutable."""
    engine = GameEngine(puzzle_3x3)
    state = engine.public_state

    # Attempt to mutate mappingproxy cards
    with pytest.raises(TypeError):
        state.cards[CellId("A1")] = "fake_card"  # type: ignore

    # Attempt to mutate mappingproxy known_statuses
    with pytest.raises(TypeError):
        state.known_statuses[CellId("A1")] = Status.INNOCENT  # type: ignore

    # Attempt to mutate frozenset revealed_cells
    with pytest.raises(AttributeError):
        state.revealed_cells.add(CellId("B1"))  # type: ignore

    # Attempt to mutate tuple revealed_clues
    with pytest.raises(TypeError):
        state.revealed_clues[0] = "fake_clue"  # type: ignore

    # Attempt to mutate tuple characters
    with pytest.raises(TypeError):
        state.characters[0] = "fake_char"  # type: ignore

    # Attempt to reassign dataclass fields on frozen PublicState
    with pytest.raises(Exception):  # FrozenInstanceError is a subclass of AttributeError
        state.grid_size = 4  # type: ignore

    with pytest.raises(Exception):
        state.revision = 99  # type: ignore

    with pytest.raises(Exception):
        state.cards = {}  # type: ignore


def test_engine_property_reassignment_fails(puzzle_3x3):
    """Verify engine properties cannot be directly set."""
    engine = GameEngine(puzzle_3x3)

    with pytest.raises(AttributeError):
        engine.grid_size = 5  # type: ignore

    with pytest.raises(AttributeError):
        engine.revision = 10  # type: ignore

    with pytest.raises(AttributeError):
        engine.is_solved = True  # type: ignore

    with pytest.raises(AttributeError):
        engine.public_state = None  # type: ignore


def test_card_state_mutation_attempts_fail(puzzle_3x3):
    """Verify PublicCard instances are frozen."""
    engine = GameEngine(puzzle_3x3)
    card = engine.public_state.cards[CellId("A1")]

    with pytest.raises(Exception):
        card.status = Status.INNOCENT  # type: ignore

    with pytest.raises(Exception):
        card.is_revealed = False  # type: ignore

    with pytest.raises(Exception):
        card.clue = None  # type: ignore


# ============================================================================
# 3. Operation Testing: Rejection Invariants
# ============================================================================


def test_rejected_out_of_bounds_cell_preserves_state(puzzle_3x3):
    """Verify out-of-bounds coordinates raise ValueError and leave state unchanged."""
    engine = GameEngine(puzzle_3x3)
    rev_before = engine.revision
    state_before = engine.public_state

    # Invalid coordinates
    bad_coords = ["D1", "A4", "Z9", "B0", "E5"]
    for bad in bad_coords:
        with pytest.raises(ValueError):
            engine._reveal_proven(bad, Status.CRIMINAL)
        assert engine.revision == rev_before
        assert engine.public_state == state_before


def test_rejected_malformed_cell_types_and_formats(puzzle_3x3):
    """Verify malformed coordinate types and strings preserve state."""
    engine = GameEngine(puzzle_3x3)
    rev_before = engine.revision
    state_before = engine.public_state

    # Bad formats
    bad_inputs = ["", "   ", "1A", "ABC", "A-1", "!@", "123", None, 42, 3.14, []]
    for bad in bad_inputs:
        with pytest.raises((ValueError, TypeError)):
            engine._reveal_proven(bad, Status.CRIMINAL)  # type: ignore
        assert engine.revision == rev_before
        assert engine.public_state == state_before


def test_rejected_already_revealed_preserves_state(puzzle_3x3):
    """Verify re-revealing already face-up cards raises ValueError and mutates nothing."""
    engine = GameEngine(puzzle_3x3)
    rev_before = engine.revision
    state_before = engine.public_state

    # A1 and B2 are initially face-up
    for cell_id in [CellId("A1"), "A1", CellId("B2"), "B2"]:
        # Try both correct and wrong verdicts
        with pytest.raises(ValueError, match="already been revealed"):
            engine._reveal_proven(cell_id, Status.CRIMINAL)
        assert engine.revision == rev_before
        assert engine.public_state == state_before

        with pytest.raises(ValueError, match="already been revealed"):
            engine._reveal_proven(cell_id, Status.INNOCENT)
        assert engine.revision == rev_before
        assert engine.public_state == state_before


def test_rejected_incorrect_verdict_preserves_state(puzzle_3x3):
    """Verify incorrect verdict raises ValueError and mutates nothing."""
    engine = GameEngine(puzzle_3x3)
    rev_before = engine.revision
    state_before = engine.public_state

    # B1 is INNOCENT; propose CRIMINAL
    with pytest.raises(ValueError, match="cannot be committed") as exc_info:
        engine._reveal_proven("B1", Status.CRIMINAL)
    assert Status.INNOCENT.value not in str(exc_info.value)
    assert engine.revision == rev_before
    assert engine.public_state == state_before

    # C1 is CRIMINAL; propose INNOCENT
    with pytest.raises(ValueError, match="cannot be committed"):
        engine._reveal_proven("C1", Status.INNOCENT)
    assert engine.revision == rev_before
    assert engine.public_state == state_before


def test_rejected_invalid_verdict_values_and_types(puzzle_3x3):
    """Verify illegal verdict representations raise ValueError/TypeError and preserve state."""
    engine = GameEngine(puzzle_3x3)
    rev_before = engine.revision
    state_before = engine.public_state

    invalid_verdicts = ["GUILTY", "SUSPECT", "TRUE", "FALSE", "", "UNKNOWN", 1, 0, True, False, None, []]
    for inv in invalid_verdicts:
        with pytest.raises((ValueError, TypeError)):
            engine._reveal_proven("B1", inv)  # type: ignore
        assert engine.revision == rev_before
        assert engine.public_state == state_before


# ============================================================================
# 4. Lifecycle: Sequential Reveals, Solved State, Post-Solved Actions, Restart
# ============================================================================


def test_sequential_reveals_to_solved_and_post_solved_rejection(puzzle_3x3):
    """Verify monotonic progress to is_solved and rejection of actions once solved."""
    engine = GameEngine(puzzle_3x3)

    assert not engine.is_solved
    assert engine.revision == 0
    assert len(engine.public_state.revealed_cells) == 2

    # Sequential reveal sequence
    steps = [
        ("B1", Status.INNOCENT, 1),
        ("C1", Status.CRIMINAL, 2),
        ("A2", Status.INNOCENT, 3),
        ("C2", Status.INNOCENT, 4),
        ("A3", Status.CRIMINAL, 5),
        ("B3", Status.INNOCENT, 6),
        ("C3", Status.INNOCENT, 7),
    ]

    for cell_str, verdict, expected_rev in steps:
        assert not engine.is_solved
        status, clue = engine._reveal_proven(cell_str, verdict)
        assert status == verdict
        assert clue.owner == CellId(cell_str)
        assert engine.revision == expected_rev
        assert CellId(cell_str) in engine.public_state.revealed_cells

    # All 9 cells now revealed
    assert engine.is_solved is True
    assert engine.revision == 7
    assert len(engine.public_state.revealed_cells) == 9

    # State in solved state
    state = engine.public_state
    for card in state.cards.values():
        assert card.is_revealed is True
        assert card.status is not None
        assert card.clue is not None

    # Post-solved attempts: reveals on any cell must fail without corrupting state
    for cell in ["A1", "B1", "C1", "A2", "B2", "C2", "A3", "B3", "C3"]:
        with pytest.raises(ValueError, match="already been revealed"):
            engine._reveal_proven(cell, Status.CRIMINAL)
        assert engine.revision == 7
        assert engine.is_solved is True

    # Post-solved attempts on invalid cell
    with pytest.raises(ValueError, match="out of bounds"):
        engine._reveal_proven("D1", Status.CRIMINAL)
    assert engine.revision == 7
    assert engine.is_solved is True


def test_restart_resets_to_initial_state_and_allows_replaying(puzzle_3x3):
    """Verify restart resets revision to 0, restores initial cards, and allows replaying."""
    engine = GameEngine(puzzle_3x3)

    # Advance 3 moves
    engine._reveal_proven("B1", Status.INNOCENT)
    engine._reveal_proven("C1", Status.CRIMINAL)
    engine._reveal_proven("A2", Status.INNOCENT)
    assert engine.revision == 3
    assert len(engine.public_state.revealed_cells) == 5

    # Restart
    reset_state = engine.restart()
    assert engine.revision == 0
    assert not engine.is_solved
    assert reset_state == engine.public_state
    assert reset_state.revealed_cells == frozenset({CellId("A1"), CellId("B2")})

    # Cards that were revealed are face-down again
    for cell in ["B1", "C1", "A2"]:
        card = reset_state.cards[CellId(cell)]
        assert card.is_revealed is False
        assert card.status is None
        assert card.clue is None

    # Replaying moves works as expected
    st, cl = engine._reveal_proven("B1", Status.INNOCENT)
    assert st == Status.INNOCENT
    assert engine.revision == 1


def test_restart_idempotency_and_initial_restart(puzzle_3x3):
    """Verify calling restart on fresh engine or repeatedly behaves consistently."""
    engine = GameEngine(puzzle_3x3)
    init_state = engine.public_state

    # Restart on fresh engine
    s1 = engine.restart()
    assert s1 == init_state
    assert engine.revision == 0

    # Successive restarts
    s2 = engine.restart()
    assert s2 == init_state
    assert engine.revision == 0


# ============================================================================
# 5. Isolation: Multiple GameEngine Instances Sharing Same Puzzle
# ============================================================================


def test_multi_engine_isolation_on_shared_puzzle(puzzle_3x3):
    """Verify actions on one engine instance do not leak into another."""
    engine1 = GameEngine(puzzle_3x3)
    engine2 = GameEngine(puzzle_3x3)

    # Initial states match
    assert engine1.public_state == engine2.public_state
    assert engine1.revision == 0
    assert engine2.revision == 0

    # Advance engine1
    engine1._reveal_proven("B1", Status.INNOCENT)
    engine1._reveal_proven("C1", Status.CRIMINAL)

    assert engine1.revision == 2
    assert len(engine1.public_state.revealed_cells) == 4

    # engine2 MUST remain completely at initial state
    assert engine2.revision == 0
    assert len(engine2.public_state.revealed_cells) == 2
    assert engine2.public_state.cards[CellId("B1")].is_revealed is False
    assert engine2.public_state.cards[CellId("B1")].status is None

    # Restart engine1 does not affect engine2
    engine1.restart()
    assert engine1.revision == 0
    assert engine2.revision == 0
