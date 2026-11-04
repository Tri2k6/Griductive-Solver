"""Unit and integration tests for offline puzzle validation (T14).

Covers:
- Direct semantic truth checking against ground truth solution without CNF/DPLL.
- Detection of false clues.
- Offline solution uniqueness checking via DPLL and primary-variable blocking clauses.
- Zero solutions (contradictory clues).
- Multiple solutions (under-constrained clues).
- Exactly one unique solution.
- Separate no-guess playability simulation from initial face-up cards.
- Distinguishing unique puzzles that stall progressively from fully playable ones.
- Architecture isolation: live logic agent and core solver do not import validation.
"""

from pathlib import Path

import pytest

from griductive.game.io import load_puzzle_from_json
from griductive.domain.model import (
    CellId,
    Character,
    Clue,
    FactClue,
    Puzzle,
    SameClue,
    Status,
)
from griductive.analysis.validation import (
    PlayabilityResult,
    UniquenessResult,
    ValidationReport,
    check_clues_truth,
    check_playability,
    check_solution_uniqueness,
    validate_puzzle,
)


@pytest.fixture
def valid_3x3_puzzle() -> Puzzle:
    fixture_path = Path("tests/fixtures/puzzle_3x3_valid.json")
    return load_puzzle_from_json(fixture_path)


def make_test_puzzle(
    grid_size: int,
    solution: dict[CellId, Status],
    clues: dict[CellId, Clue],
    initial_face_up: list[CellId],
) -> Puzzle:
    """Helper to assemble a minimal Puzzle value object for validation tests."""
    chars = []
    idx = 1
    for r in range(1, grid_size + 1):
        for c in range(1, grid_size + 1):
            cell = CellId.from_coords(r, c)
            name = f"Char_{idx:02d}"
            chars.append(Character(cell=cell, name=name, profession="Citizen"))
            idx += 1
    return Puzzle(
        grid_size=grid_size,
        characters=tuple(sorted(chars, key=lambda ch: ch.name)),
        solution=solution,
        clues=clues,
        initial_face_up=tuple(initial_face_up),
    )


# ---------------------------------------------------------------------------
# 1. Semantic Truth Check
# ---------------------------------------------------------------------------


class TestSemanticTruthCheck:
    def test_all_clues_true_in_valid_fixture(self, valid_3x3_puzzle: Puzzle) -> None:
        all_true, false_clues = check_clues_truth(valid_3x3_puzzle)
        assert all_true is True
        assert false_clues == ()

    def test_detects_false_clues(self) -> None:
        """A puzzle with a clue contradicting its private solution fails truth check."""
        sol = {
            CellId("A1"): Status.CRIMINAL,
            CellId("B1"): Status.INNOCENT,
            CellId("A2"): Status.CRIMINAL,
            CellId("B2"): Status.INNOCENT,
        }
        # False clue: claims Bob (B1) is CRIMINAL, but solution says B1 is INNOCENT
        c_a1 = FactClue("c_false", CellId("A1"), CellId("B1"), Status.CRIMINAL)
        c_b1 = FactClue("c_b1", CellId("B1"), CellId("A2"), Status.CRIMINAL)
        c_a2 = FactClue("c_a2", CellId("A2"), CellId("B2"), Status.INNOCENT)
        c_b2 = FactClue("c_b2", CellId("B2"), CellId("A1"), Status.CRIMINAL)
        clues = {
            CellId("A1"): c_a1,
            CellId("B1"): c_b1,
            CellId("A2"): c_a2,
            CellId("B2"): c_b2,
        }
        puzzle = make_test_puzzle(2, sol, clues, [CellId("A1")])

        all_true, false_clues = check_clues_truth(puzzle)
        assert all_true is False
        assert "c_false" in false_clues
        assert len(false_clues) == 1


# ---------------------------------------------------------------------------
# 2. Complete-Clue Uniqueness Check
# ---------------------------------------------------------------------------


class TestSolutionUniqueness:
    def test_valid_3x3_has_exactly_one_solution(
        self, valid_3x3_puzzle: Puzzle
    ) -> None:
        """Across all 9 clues, the valid 3x3 fixture has exactly one unique solution."""
        res, count, sol1, sol2 = check_solution_uniqueness(valid_3x3_puzzle)
        assert res == UniquenessResult.UNIQUE
        assert count == 1
        assert sol1 is not None
        assert sol2 is None
        # sol1 matches the puzzle's ground truth solution
        assert sol1 == dict(valid_3x3_puzzle.solution)

    def test_contradictory_clues_yield_zero_solutions(self) -> None:
        """Contradictory clues in the puzzle formula result in ZERO solutions (UNSAT)."""
        sol = {
            CellId("A1"): Status.CRIMINAL,
            CellId("B1"): Status.INNOCENT,
            CellId("A2"): Status.CRIMINAL,
            CellId("B2"): Status.INNOCENT,
        }
        # c1 and c2 contradict each other regarding B1
        c1 = FactClue("c1", CellId("A1"), CellId("B1"), Status.CRIMINAL)
        c2 = FactClue("c2", CellId("B1"), CellId("B1"), Status.INNOCENT)
        c3 = FactClue("c3", CellId("A2"), CellId("A2"), Status.CRIMINAL)
        c4 = FactClue("c4", CellId("B2"), CellId("B2"), Status.INNOCENT)
        clues = {CellId("A1"): c1, CellId("B1"): c2, CellId("A2"): c3, CellId("B2"): c4}
        puzzle = make_test_puzzle(2, sol, clues, [CellId("A1")])

        res, count, sol1, sol2 = check_solution_uniqueness(puzzle)
        assert res == UniquenessResult.ZERO
        assert count == 0
        assert sol1 is None
        assert sol2 is None

    def test_underconstrained_puzzle_yields_multiple_solutions(self) -> None:
        """A puzzle with under-constrained clues admits MULTIPLE distinct solutions."""
        # 2x2 where all clues only relate A1 and B1; A2 and B2 are totally free
        sol = {
            CellId("A1"): Status.CRIMINAL,
            CellId("B1"): Status.CRIMINAL,
            CellId("A2"): Status.INNOCENT,
            CellId("B2"): Status.INNOCENT,
        }
        c1 = SameClue("c1", CellId("A1"), CellId("A1"), CellId("B1"))
        c2 = SameClue("c2", CellId("B1"), CellId("A1"), CellId("B1"))
        c3 = SameClue("c3", CellId("A2"), CellId("A1"), CellId("B1"))
        c4 = SameClue("c4", CellId("B2"), CellId("A1"), CellId("B1"))
        clues = {CellId("A1"): c1, CellId("B1"): c2, CellId("A2"): c3, CellId("B2"): c4}
        # Initial face-up: none
        puzzle = make_test_puzzle(2, sol, clues, [])

        res, count, sol1, sol2 = check_solution_uniqueness(puzzle)
        assert res == UniquenessResult.MULTIPLE
        assert count == 2
        assert sol1 is not None
        assert sol2 is not None
        # The two solutions must be distinct primary variable assignments
        assert sol1 != sol2

    def test_hidden_solution_not_injected_into_uniqueness(self) -> None:
        """Uniqueness must only use initial face-up cards, not hidden face-down statuses."""
        # If hidden solution were injected, an ambiguous puzzle would falsely report UNIQUE.
        sol = {
            CellId("A1"): Status.CRIMINAL,
            CellId("B1"): Status.INNOCENT,
            CellId("A2"): Status.CRIMINAL,
            CellId("B2"): Status.INNOCENT,
        }
        # Clues that constrain nothing: all cells are unconstrained
        c1 = SameClue("c1", CellId("A1"), CellId("A1"), CellId("A1"))  # A1 == A1 tautology
        c2 = SameClue("c2", CellId("B1"), CellId("B1"), CellId("B1"))
        c3 = SameClue("c3", CellId("A2"), CellId("A2"), CellId("A2"))
        c4 = SameClue("c4", CellId("B2"), CellId("B2"), CellId("B2"))
        clues = {CellId("A1"): c1, CellId("B1"): c2, CellId("A2"): c3, CellId("B2"): c4}
        # Initial face-up: only A1
        puzzle = make_test_puzzle(2, sol, clues, [CellId("A1")])

        res, count, sol1, sol2 = check_solution_uniqueness(puzzle)
        # B1, A2, B2 are completely free, so there must be multiple solutions!
        assert res == UniquenessResult.MULTIPLE
        assert count == 2


# ---------------------------------------------------------------------------
# 3. No-Guess Playability Simulation
# ---------------------------------------------------------------------------


class TestNoGuessPlayability:
    def test_progressive_puzzle_is_solvable_no_guess(self) -> None:
        """A progressive puzzle correctly reports SOLVABLE_NO_GUESS."""
        sol = {
            CellId("A1"): Status.CRIMINAL,
            CellId("B1"): Status.INNOCENT,
            CellId("A2"): Status.CRIMINAL,
            CellId("B2"): Status.INNOCENT,
        }
        c_a1 = FactClue("c_a1", CellId("A1"), CellId("B1"), Status.INNOCENT)
        c_b1 = FactClue("c_b1", CellId("B1"), CellId("A2"), Status.CRIMINAL)
        c_a2 = FactClue("c_a2", CellId("A2"), CellId("B2"), Status.INNOCENT)
        c_b2 = FactClue("c_b2", CellId("B2"), CellId("A1"), Status.CRIMINAL)
        clues = {
            CellId("A1"): c_a1,
            CellId("B1"): c_b1,
            CellId("A2"): c_a2,
            CellId("B2"): c_b2,
        }
        puzzle = make_test_puzzle(2, sol, clues, [CellId("A1")])

        res, steps = check_playability(puzzle)
        assert res == PlayabilityResult.SOLVABLE_NO_GUESS
        assert steps == 3

    def test_unique_puzzle_that_stalls_is_reported_as_stalled(
        self, valid_3x3_puzzle: Puzzle
    ) -> None:
        """puzzle_3x3_valid is UNIQUE under all clues, but stalls progressively from {A1, B2}."""
        res, steps = check_playability(valid_3x3_puzzle)
        assert res == PlayabilityResult.STALLED
        assert steps == 1  # Successfully revealed B1 before stalling


# ---------------------------------------------------------------------------
# 4. Comprehensive Validation Report
# ---------------------------------------------------------------------------


class TestCompleteValidationReport:
    def test_validate_puzzle_report_on_unique_stalled_puzzle(
        self, valid_3x3_puzzle: Puzzle
    ) -> None:
        """Valid 3x3 fixture produces a clean ValidationReport distinguishing uniqueness from playability."""
        report = validate_puzzle(valid_3x3_puzzle)

        assert isinstance(report, ValidationReport)
        assert report.is_valid is True
        assert report.clues_truth is True
        assert report.false_clue_ids == ()
        assert report.uniqueness == UniquenessResult.UNIQUE
        assert report.solution_count == 1
        assert report.is_playable_no_guess is False
        assert report.playability == PlayabilityResult.STALLED
        assert report.playability_steps == 1
        assert len(report.messages) == 3

    def test_validate_puzzle_report_on_progressive_puzzle(self) -> None:
        """Fully progressive puzzle reports is_valid=True and is_playable_no_guess=True."""
        sol = {
            CellId("A1"): Status.CRIMINAL,
            CellId("B1"): Status.INNOCENT,
            CellId("A2"): Status.CRIMINAL,
            CellId("B2"): Status.INNOCENT,
        }
        c_a1 = FactClue("c_a1", CellId("A1"), CellId("B1"), Status.INNOCENT)
        c_b1 = FactClue("c_b1", CellId("B1"), CellId("A2"), Status.CRIMINAL)
        c_a2 = FactClue("c_a2", CellId("A2"), CellId("B2"), Status.INNOCENT)
        c_b2 = FactClue("c_b2", CellId("B2"), CellId("A1"), Status.CRIMINAL)
        clues = {
            CellId("A1"): c_a1,
            CellId("B1"): c_b1,
            CellId("A2"): c_a2,
            CellId("B2"): c_b2,
        }
        puzzle = make_test_puzzle(2, sol, clues, [CellId("A1")])

        report = validate_puzzle(puzzle)
        assert report.is_valid is True
        assert report.clues_truth is True
        assert report.uniqueness == UniquenessResult.UNIQUE
        assert report.is_playable_no_guess is True
        assert report.playability == PlayabilityResult.SOLVABLE_NO_GUESS
        assert report.playability_steps == 3

    def test_validate_puzzle_on_false_clues_skips_playability_safely(self) -> None:
        """FIX-02: validate_puzzle skips progressive playability when clues are false without crashing."""
        sol = {
            CellId("A1"): Status.CRIMINAL,
            CellId("B1"): Status.INNOCENT,
            CellId("A2"): Status.CRIMINAL,
            CellId("B2"): Status.INNOCENT,
        }
        # Face-up A1 has false clue forcing B1 to be CRIMINAL (conflicts with private truth)
        c_false = FactClue("c_false", CellId("A1"), CellId("B1"), Status.CRIMINAL)
        c2 = FactClue("c2", CellId("B1"), CellId("A2"), Status.CRIMINAL)
        c3 = FactClue("c3", CellId("A2"), CellId("B2"), Status.INNOCENT)
        c4 = FactClue("c4", CellId("B2"), CellId("A1"), Status.CRIMINAL)
        clues = {
            CellId("A1"): c_false,
            CellId("B1"): c2,
            CellId("A2"): c3,
            CellId("B2"): c4,
        }
        puzzle = make_test_puzzle(2, sol, clues, [CellId("A1")])

        # Must NOT crash with unhandled engine reveal exception
        report = validate_puzzle(puzzle)
        assert report.is_valid is False
        assert report.clues_truth is False
        assert "c_false" in report.false_clue_ids
        assert report.playability == PlayabilityResult.SKIPPED
        assert report.playability_steps == 0
        assert report.is_playable_no_guess is False
        assert any("skipped" in m.lower() for m in report.messages)

    def test_check_playability_directly_on_false_clues_handled_safely(self) -> None:
        """FIX-02: Direct check_playability on false clues handles reveal contradiction safely."""
        sol = {
            CellId("A1"): Status.CRIMINAL,
            CellId("B1"): Status.INNOCENT,
            CellId("A2"): Status.CRIMINAL,
            CellId("B2"): Status.INNOCENT,
        }
        c_false = FactClue("c_false", CellId("A1"), CellId("B1"), Status.CRIMINAL)
        c2 = FactClue("c2", CellId("B1"), CellId("A2"), Status.CRIMINAL)
        c3 = FactClue("c3", CellId("A2"), CellId("B2"), Status.INNOCENT)
        c4 = FactClue("c4", CellId("B2"), CellId("A1"), Status.CRIMINAL)
        clues = {
            CellId("A1"): c_false,
            CellId("B1"): c2,
            CellId("A2"): c3,
            CellId("B2"): c4,
        }
        puzzle = make_test_puzzle(2, sol, clues, [CellId("A1")])

        # Calling check_playability directly must not crash with uncaught ValueError
        res, steps = check_playability(puzzle)
        assert res == PlayabilityResult.INCONSISTENT
        assert steps == 0

    def test_initially_solved_puzzle_marked_as_solvable_no_guess(self) -> None:
        """FIX-06: An initially solved puzzle (all cards face-up) reports SOLVABLE_NO_GUESS with 0 steps."""
        sol = {
            CellId("A1"): Status.CRIMINAL,
            CellId("B1"): Status.INNOCENT,
            CellId("A2"): Status.CRIMINAL,
            CellId("B2"): Status.INNOCENT,
        }
        c1 = FactClue("c1", CellId("A1"), CellId("B1"), Status.INNOCENT)
        c2 = FactClue("c2", CellId("B1"), CellId("A2"), Status.CRIMINAL)
        c3 = FactClue("c3", CellId("A2"), CellId("B2"), Status.INNOCENT)
        c4 = FactClue("c4", CellId("B2"), CellId("A1"), Status.CRIMINAL)
        clues = {CellId("A1"): c1, CellId("B1"): c2, CellId("A2"): c3, CellId("B2"): c4}
        all_cells = [CellId("A1"), CellId("B1"), CellId("A2"), CellId("B2")]
        puzzle = make_test_puzzle(2, sol, clues, all_cells)

        res, steps = check_playability(puzzle)
        assert res == PlayabilityResult.SOLVABLE_NO_GUESS
        assert steps == 0

        report = validate_puzzle(puzzle)
        assert report.is_valid is True
        assert report.is_playable_no_guess is True
        assert report.playability == PlayabilityResult.SOLVABLE_NO_GUESS
        assert report.playability_steps == 0
        assert any("initially solved" in m for m in report.messages)


# ---------------------------------------------------------------------------
# 5. Architecture Isolation
# ---------------------------------------------------------------------------


class TestArchitectureIsolation:
    def test_live_agent_and_solver_do_not_import_validation(self) -> None:
        """logic.py, cnf.py, and dpll.py must not import validation."""
        import ast

        root_src = Path(__file__).resolve().parent.parent / "src" / "griductive" / "solver"
        for mod_name in ["logic.py", "cnf.py", "dpll.py", "kb.py"]:
            mod_path = root_src / mod_name
            tree = ast.parse(mod_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert "validation" not in alias.name, (
                            f"Forbidden import of validation in {mod_name}: {alias.name}"
                        )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        assert "validation" not in node.module, (
                            f"Forbidden 'from' import of validation in {mod_name}: {node.module}"
                        )
