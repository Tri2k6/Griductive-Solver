"""Comprehensive unit and integration tests for GUI, presentation, and interactions (T16 & T17)."""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from griductive.game.controller import (
    AutoSolveStatus,
    GameController,
    RejectionReason,
)
from griductive.ui.gui import (
    GriductiveApp,
    format_clue_text,
    format_region_text,
)
from griductive.game.io import load_puzzle_from_json
from griductive.domain.model import (
    CellId,
    Character,
    ColRegion,
    CommonNeighborsRegion,
    DifferentClue,
    ExactlyClue,
    ExplicitRegion,
    FactClue,
    NeighborsRegion,
    Parity,
    ParityClue,
    Puzzle,
    RowRegion,
    SameClue,
    Status,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "puzzles"


@pytest.fixture
def puzzle_3x3_prog():
    return load_puzzle_from_json(FIXTURES_DIR / "puzzle_3x3_progressive.json")


@pytest.fixture
def puzzle_3x3_stalled():
    return load_puzzle_from_json(FIXTURES_DIR / "puzzle_3x3_stalled.json")


@pytest.fixture
def puzzle_4x4_prog():
    return load_puzzle_from_json(FIXTURES_DIR / "puzzle_4x4_progressive.json")


@pytest.fixture
def puzzle_4x4_stalled():
    return load_puzzle_from_json(FIXTURES_DIR / "puzzle_4x4_stalled.json")


# =============================================================================
# T16: View Model, Formatting, and Board Rendering
# =============================================================================


def test_format_region_and_clue_text(puzzle_3x3_prog):
    """Test human-readable formatting of regions and clues."""
    # Regions
    assert format_region_text(RowRegion(2)) == "Row 2"
    assert format_region_text(ColRegion("C")) == "Col C"
    assert format_region_text(NeighborsRegion(CellId("B2"))) == "Neighbors of B2"
    assert format_region_text(ExplicitRegion((CellId("A1"), CellId("B2")))) == "{A1, B2}"
    assert format_region_text(CommonNeighborsRegion(CellId("A1"), CellId("C1"))) == "Common neighbors of A1 & C1"

    # Clues
    c_fact = FactClue("c1", CellId("A1"), CellId("B1"), Status.INNOCENT, "Bob")
    assert "Bob (B1) is INNOCENT" in format_clue_text(c_fact)

    c_same = SameClue("c2", CellId("A1"), CellId("B1"), CellId("C1"), "Bob", "Charlie")
    assert "Bob and Charlie have SAME status" in format_clue_text(c_same)

    c_diff = DifferentClue("c3", CellId("A1"), CellId("B1"), CellId("C1"), "Bob", "Charlie")
    assert "Bob and Charlie have DIFFERENT status" in format_clue_text(c_diff)

    c_ex0 = ExactlyClue("c4", CellId("A1"), 0, RowRegion(1))
    assert "NO criminals in Row 1" in format_clue_text(c_ex0)

    c_ex2 = ExactlyClue("c5", CellId("A1"), 2, RowRegion(1))
    assert "EXACTLY 2 criminal(s) in Row 1" in format_clue_text(c_ex2)

    c_parity = ParityClue("c6", CellId("A1"), Parity.EVEN, ColRegion("A"))
    assert "EVEN number of criminals in Col A" in format_clue_text(c_parity)


def test_app_preserves_public_private_boundary(puzzle_3x3_prog):
    """Verify that GriductiveApp never holds private puzzle solution or GameEngine."""
    ctrl = GameController(puzzle_3x3_prog)
    app = GriductiveApp(ctrl)

    # Controller deliberately does not expose private engine
    assert not hasattr(app.controller, "engine")
    assert not hasattr(app.controller, "_puzzle")

    # State visible to app is strictly PublicState
    pub_state = app.controller.public_state
    assert not hasattr(pub_state, "solution")

    # Unrevealed cards must not expose status or clue
    unrevealed = [c for c in pub_state.cards.values() if not c.is_revealed]
    assert len(unrevealed) == 8  # 1 face-up (A1), 8 face-down
    for card in unrevealed:
        assert card.status is None
        assert card.clue is None

        view_data = app.get_cell_view_data(card.cell)
        assert view_data.status is None
        assert view_data.status_label == "HIDDEN"
        assert view_data.clue is None
        assert view_data.clue_text == ""


def test_alphabetical_character_ordering(puzzle_3x3_prog):
    """Verify that PublicState characters are ordered alphabetically by display name."""
    ctrl = GameController(puzzle_3x3_prog)
    app = GriductiveApp(ctrl)

    names = [c.name for c in app.controller.public_state.characters]
    assert names == sorted(names)
    assert names == [
        "Alice", "Bob", "Charlie", "David", "Eve",
        "Frank", "Grace", "Heidi", "Ivan",
    ]


def test_board_grid_representation(puzzle_3x3_prog, puzzle_4x4_prog):
    """Verify 3x3 and 4x4 grid representation structure."""
    app3 = GriductiveApp(GameController(puzzle_3x3_prog))
    grid3 = app3.get_board_grid()
    assert len(grid3) == 3
    assert all(len(row) == 3 for row in grid3)
    assert grid3[0][0].cell == CellId("A1")
    assert grid3[2][2].cell == CellId("C3")

    app4 = GriductiveApp(GameController(puzzle_4x4_prog))
    grid4 = app4.get_board_grid()
    assert len(grid4) == 4
    assert all(len(row) == 4 for row in grid4)
    assert grid4[0][0].cell == CellId("A1")
    assert grid4[3][3].cell == CellId("D4")


# =============================================================================
# T17: GUI Interactions & Error Handling
# =============================================================================


def test_selection_and_highlighting(puzzle_3x3_prog):
    """Test selecting cells and clues updates highlighting."""
    app = GriductiveApp(GameController(puzzle_3x3_prog))

    # Initial face-up cell A1 has clue c_A1: FACT(Bob / B1, INNOCENT)
    app.select_cell(CellId("A1"))
    assert app.selected_cell == CellId("A1")
    assert app.selected_clue_id == "c_A1"
    assert CellId("B1") in app.highlighted_cells

    # Check cell view data reflects selection & highlight
    a1_data = app.get_cell_view_data(CellId("A1"))
    assert a1_data.is_selected is True
    assert a1_data.is_highlighted is False

    b1_data = app.get_cell_view_data(CellId("B1"))
    assert b1_data.is_selected is False
    assert b1_data.is_highlighted is True

    # Selecting an unrevealed cell clears clue highlights
    app.select_cell(CellId("C3"))
    assert app.selected_cell == CellId("C3")
    assert app.selected_clue_id is None
    assert len(app.highlighted_cells) == 0

    # Clear highlights method
    app.select_clue("c_A1")
    assert len(app.highlighted_cells) == 1
    app.clear_highlights()
    assert len(app.highlighted_cells) == 0
    assert app.selected_clue_id is None


def test_manual_call_without_selection(puzzle_3x3_prog):
    """Calling without selecting a cell returns clean rejection without error."""
    app = GriductiveApp(GameController(puzzle_3x3_prog))
    app.selected_cell = None
    res = app.call_criminal()
    assert res.accepted is False
    assert res.rejection_reason == RejectionReason.INVALID_CELL
    assert "No cell selected" in app.status_message


def test_manual_call_accepted_reveals_card_and_clue(puzzle_3x3_prog):
    """Test that a provable manual call is accepted, flips the card, and reveals clue."""
    app = GriductiveApp(GameController(puzzle_3x3_prog))
    rev_before = app.controller.revision

    # B1 is provably INNOCENT at initial step
    app.select_cell(CellId("B1"))
    res = app.call_innocent()

    assert res.accepted is True
    assert res.revealed_status == Status.INNOCENT
    assert res.revealed_clue is not None
    assert res.revealed_clue.clue_id == "c_B1"
    assert app.controller.revision == rev_before + 1

    # B1 is now revealed in public state and view data
    b1_data = app.get_cell_view_data(CellId("B1"))
    assert b1_data.is_revealed is True
    assert b1_data.status == Status.INNOCENT
    assert b1_data.clue is not None
    assert b1_data.clue.clue_id == "c_B1"
    assert "ACCEPTED" in app.status_message
    assert app.last_rejection_reason is None


def test_manual_call_rejected_not_provable(puzzle_3x3_prog):
    """Test that an unprovable call is rejected with NOT_PROVABLE and preserves state."""
    app = GriductiveApp(GameController(puzzle_3x3_prog))
    rev_before = app.controller.revision
    known_before = dict(app.controller.public_state.known_statuses)

    # C2 is UNKNOWN at step 0
    app.select_cell(CellId("C2"))
    res = app.call_criminal()

    assert res.accepted is False
    assert res.rejection_reason == RejectionReason.NOT_PROVABLE
    assert app.last_rejection_reason == RejectionReason.NOT_PROVABLE
    assert app.controller.revision == rev_before
    assert dict(app.controller.public_state.known_statuses) == known_before

    # Card remains unrevealed
    c2_data = app.get_cell_view_data(CellId("C2"))
    assert c2_data.is_revealed is False
    assert c2_data.status is None
    assert "NOT_PROVABLE" in app.status_message


def test_manual_call_rejected_contradicted(puzzle_3x3_prog):
    """Test that calling the opposite of a proven verdict gives CONTRADICTED."""
    app = GriductiveApp(GameController(puzzle_3x3_prog))
    rev_before = app.controller.revision
    known_before = dict(app.controller.public_state.known_statuses)

    # B1 is proven INNOCENT, so calling CRIMINAL is contradicted
    app.select_cell(CellId("B1"))
    res = app.call_criminal()

    assert res.accepted is False
    assert res.rejection_reason == RejectionReason.CONTRADICTED
    assert app.last_rejection_reason == RejectionReason.CONTRADICTED
    assert app.controller.revision == rev_before
    assert dict(app.controller.public_state.known_statuses) == known_before

    # Card remains unrevealed
    b1_data = app.get_cell_view_data(CellId("B1"))
    assert b1_data.is_revealed is False
    assert "CONTRADICTED" in app.status_message


def test_hint_functionality(puzzle_3x3_prog, puzzle_3x3_stalled):
    """Test Hint suggests forced card without mutating state, or reports stalled."""
    # 1. Progressive puzzle has forced card B1=INNOCENT
    app_prog = GriductiveApp(GameController(puzzle_3x3_prog))
    rev_before = app_prog.controller.revision

    h = app_prog.hint()
    assert h.has_forced_cell is True
    assert h.cell == CellId("B1")
    assert h.verdict == Status.INNOCENT
    assert "c_A1" in h.relevant_clue_ids
    assert app_prog.hinted_cell == CellId("B1")
    assert app_prog.selected_cell == CellId("B1")

    # State must NOT be mutated by Hint!
    assert app_prog.controller.revision == rev_before
    assert CellId("B1") not in app_prog.controller.public_state.revealed_cells

    # 2. Stalled puzzle after step 1 has no forced cards
    app_stalled = GriductiveApp(GameController(puzzle_3x3_stalled))
    app_stalled.auto_solve()  # Advances 1 step, then stalls
    assert not app_stalled.controller.is_solved

    h2 = app_stalled.hint()
    assert h2.has_forced_cell is False
    assert h2.cell is None
    assert "without guessing" in h2.message
    assert app_stalled.hinted_cell is None
    assert app_stalled.selected_cell is None
    assert app_stalled.selected_clue_id is None
    assert app_stalled.highlighted_cells == frozenset()


def test_hint_clears_stale_visual_state(puzzle_3x3_prog):
    """A later no-hint result must clear the prior hint and clue highlights."""
    app = GriductiveApp(GameController(puzzle_3x3_prog))
    first_hint = app.hint()
    assert first_hint.has_forced_cell
    assert app.highlighted_cells

    app.auto_solve()
    no_hint = app.hint()
    assert not no_hint.has_forced_cell
    assert app.hinted_cell is None
    assert app.selected_cell is None
    assert app.selected_clue_id is None
    assert app.highlighted_cells == frozenset()


def test_step_and_auto_solve(puzzle_3x3_prog):
    """Test step-by-step deduction and auto-solve to SOLVED terminal state."""
    app = GriductiveApp(GameController(puzzle_3x3_prog))

    # Single step
    s1 = app.step()
    assert s1 is not None
    assert s1.step_number == 1
    assert s1.target_cell == CellId("B1")
    assert s1.target_verdict == Status.INNOCENT
    assert not app.controller.is_solved

    # Auto solve to completion
    rep = app.auto_solve()
    assert rep.status == AutoSolveStatus.SOLVED
    assert rep.total_steps == 7  # 1 previous + 7 remaining = 8 total
    assert app.controller.is_solved is True
    assert "SOLVED" in app.status_message


def test_restart_resets_board_and_selections(puzzle_3x3_prog):
    """Test restart resets the game back to initial face-up cards."""
    app = GriductiveApp(GameController(puzzle_3x3_prog))
    app.auto_solve()
    assert app.controller.is_solved is True

    # Restart
    app.restart()
    assert not app.controller.is_solved
    assert len(app.controller.public_state.revealed_cells) == 1
    assert CellId("A1") in app.controller.public_state.revealed_cells
    assert app.selected_cell is None
    assert app.hinted_cell is None
    assert len(app.highlighted_cells) == 0
    assert app.last_rejection_reason is None
    assert app.trace_log == ["Puzzle restarted to initial face-up cards."]


def test_load_puzzle_transitions_dimensions(puzzle_3x3_prog, puzzle_4x4_prog):
    """Test loading another puzzle cleanly updates grid size and view."""
    app = GriductiveApp(GameController(puzzle_3x3_prog))
    assert app.controller.grid_size == 3

    app.hint()
    assert len(app.trace_log) > 1
    app.load_puzzle(puzzle_4x4_prog)
    assert app.controller.grid_size == 4
    grid = app.get_board_grid()
    assert len(grid) == 4
    assert len(grid[0]) == 4
    assert app.trace_log == ["Loaded puzzle (4×4) successfully."]


def test_step_reports_inconsistent_public_kb() -> None:
    """Step must distinguish a contradictory public KB from a logical stall."""
    cells = tuple(CellId(value) for value in ("A1", "B1", "A2", "B2"))
    characters = tuple(
        Character(cell, f"Person {index}", "Tester")
        for index, cell in enumerate(cells)
    )
    clues = {
        cells[0]: FactClue("c_A1", cells[0], cells[2], Status.CRIMINAL),
        cells[1]: FactClue("c_B1", cells[1], cells[2], Status.INNOCENT),
        cells[2]: FactClue("c_A2", cells[2], cells[2], Status.INNOCENT),
        cells[3]: FactClue("c_B2", cells[3], cells[3], Status.INNOCENT),
    }
    puzzle = Puzzle(
        grid_size=2,
        characters=characters,
        solution={cell: Status.INNOCENT for cell in cells},
        clues=clues,
        initial_face_up=frozenset({cells[0], cells[1]}),
    )
    app = GriductiveApp(GameController(puzzle))
    revision_before = app.controller.revision
    revealed_before = app.controller.public_state.revealed_cells

    result = app.step()

    assert result is None
    assert app.last_auto_solve_report is not None
    assert app.last_auto_solve_report.status == AutoSolveStatus.INCONSISTENT
    assert "INCONSISTENT" in app.status_message
    assert "STALLED" not in app.status_message
    assert app.controller.revision == revision_before
    assert app.controller.public_state.revealed_cells == revealed_before


# =============================================================================
# Tkinter Widget Rendering (Under Tk display if available or xvfb)
# =============================================================================


def test_tkinter_widget_tree_under_display(puzzle_3x3_prog):
    """Test that Tkinter widgets build and respond to events if display is present."""
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No graphical display available; skipping live Tk widget test.")

    try:
        root.geometry("1000x700")
        app = GriductiveApp(GameController(puzzle_3x3_prog), root=root)

        # Check widget references
        assert len(app._cell_buttons) == 9
        assert app._status_label is not None
        assert app._clues_listbox is not None
        assert app._log_text is not None

        # Select a card
        app.select_cell(CellId("B1"))
        root.update()

        # Call innocent on B1
        res = app.call_innocent()
        assert res.accepted is True
        root.update()

        # Check B1 widget updated
        b1_frame = app._cell_buttons[CellId("B1")]
        w = b1_frame._widgets  # type: ignore[attr-defined]
        assert w["badge"].cget("text") == "INNOCENT"

        # Check revealed clues listbox updated
        assert app._clues_listbox.size() >= 2

        # Step and hint
        app.hint()
        root.update()
        app.step()
        root.update()

    finally:
        root.destroy()
