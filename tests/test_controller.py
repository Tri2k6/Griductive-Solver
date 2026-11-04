"""Unit and integration tests for GameController (T12 & T13).

Covers:
- Manual verdict calls (provable accepted, unprovable NOT_PROVABLE, contradicted CONTRADICTED).
- Inconsistent KB rejection and already-revealed / invalid cell handling.
- Immutability on rejection (state and revision strictly preserved).
- Step-by-step deterministic deduction loop (T13).
- Full Auto Solve to completion on valid progressive puzzles.
- Stalled and inconsistent termination without guessing.
- Non-mutating hints with relevant clue identification.
"""

from pathlib import Path

import pytest

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
from griductive.game.io import load_puzzle_from_json
from griductive.solver.logic import Verdict
from griductive.domain.model import (
    CellId,
    Character,
    FactClue,
    PublicState,
    Puzzle,
    Status,
)


@pytest.fixture
def valid_3x3_puzzle() -> Puzzle:
    fixture_path = Path("tests/fixtures/puzzle_3x3_valid.json")
    return load_puzzle_from_json(fixture_path)


def make_minimal_puzzle(
    grid_size: int,
    solution: dict[CellId, Status],
    clues: dict[CellId, Clue],
    initial_face_up: list[CellId],
) -> Puzzle:
    """Helper to create small testing puzzles."""
    chars = []
    idx = 1
    for r in range(1, grid_size + 1):
        for c in range(1, grid_size + 1):
            cell = CellId.from_coords(r, c)
            name = f"Person_{idx:02d}"
            chars.append(Character(cell=cell, name=name, profession="Citizen"))
            idx += 1
    return Puzzle(
        grid_size=grid_size,
        characters=tuple(sorted(chars, key=lambda ch: ch.name)),
        solution=solution,
        clues=clues,
        initial_face_up=tuple(initial_face_up),
    )


@pytest.fixture
def progressive_2x2_puzzle() -> Puzzle:
    """A 2x2 puzzle that progressively solves to completion in 3 steps from A1."""
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
    return make_minimal_puzzle(2, sol, clues, [CellId("A1")])


# ---------------------------------------------------------------------------
# T12 — Manual Verdict Calls
# ---------------------------------------------------------------------------


class TestManualCalls:
    def test_init_with_puzzle_or_engine(self, valid_3x3_puzzle: Puzzle) -> None:
        c1 = GameController(valid_3x3_puzzle)
        assert c1.grid_size == 3
        assert c1.revision == 0

        engine = GameEngine(valid_3x3_puzzle)
        c2 = GameController(engine)
        assert c2.public_state == engine.public_state
        assert not hasattr(c2, "engine")

        with pytest.raises(TypeError):
            GameController("not an engine")  # type: ignore[arg-type]

    def test_accepted_provable_call(self, valid_3x3_puzzle: Puzzle) -> None:
        """B1 is proven INNOCENT by A1's FactClue; calling INNOCENT must be accepted."""
        controller = GameController(valid_3x3_puzzle)
        assert controller.revision == 0
        assert CellId("B1") not in controller.public_state.revealed_cells

        res = controller.make_call(CellId("B1"), Status.INNOCENT)

        assert res.accepted is True
        assert res.cell == CellId("B1")
        assert res.proposed_status == Status.INNOCENT
        assert res.revealed_status == Status.INNOCENT
        assert res.revealed_clue is not None
        assert res.rejection_reason is None
        assert res.state_revision == 1
        assert controller.revision == 1
        assert CellId("B1") in controller.public_state.revealed_cells

    def test_accepted_call_via_string_arguments(self, valid_3x3_puzzle: Puzzle) -> None:
        """make_call accepts string cell coordinates and string verdict names."""
        controller = GameController(valid_3x3_puzzle)
        res = controller.make_call("B1", "INNOCENT")
        assert res.accepted is True
        assert res.cell == CellId("B1")
        assert res.revealed_status == Status.INNOCENT

    def test_rejected_unprovable_call_returns_not_provable(
        self, valid_3x3_puzzle: Puzzle
    ) -> None:
        """C1 is not entailed at step 0 (ambiguous); must reject with NOT_PROVABLE."""
        controller = GameController(valid_3x3_puzzle)
        initial_revision = controller.revision
        initial_revealed = set(controller.public_state.revealed_cells)

        res = controller.make_call(CellId("C1"), Status.CRIMINAL)

        assert res.accepted is False
        assert res.rejection_reason == RejectionReason.NOT_PROVABLE
        assert res.revealed_status is None
        assert res.revealed_clue is None
        # Immutability: revision and revealed cells remain unchanged
        assert controller.revision == initial_revision
        assert set(controller.public_state.revealed_cells) == initial_revealed

    def test_unknown_card_has_no_supported_public_reveal_path(
        self, valid_3x3_puzzle: Puzzle
    ) -> None:
        """A correct hidden guess cannot bypass public SAT proof through the controller."""
        controller = GameController(valid_3x3_puzzle)
        state_before = controller.public_state

        assert not hasattr(controller, "engine")
        # C1 is secretly CRIMINAL but UNKNOWN from the initial public KB.
        result = controller.make_call(CellId("C1"), Status.CRIMINAL)

        assert result.accepted is False
        assert result.rejection_reason == RejectionReason.NOT_PROVABLE
        assert controller.revision == state_before.revision
        assert controller.public_state == state_before

    def test_rejected_opposite_verdict_returns_contradicted(
        self, valid_3x3_puzzle: Puzzle
    ) -> None:
        """B1 is proven INNOCENT; calling CRIMINAL must reject with CONTRADICTED."""
        controller = GameController(valid_3x3_puzzle)
        initial_revision = controller.revision
        initial_revealed = set(controller.public_state.revealed_cells)

        res = controller.make_call(CellId("B1"), Status.CRIMINAL)

        assert res.accepted is False
        assert res.rejection_reason == RejectionReason.CONTRADICTED
        assert res.revealed_status is None
        assert res.revealed_clue is None
        # Immutability: revision and revealed cells remain unchanged
        assert controller.revision == initial_revision
        assert set(controller.public_state.revealed_cells) == initial_revealed

    def test_rejected_already_revealed_cell(self, valid_3x3_puzzle: Puzzle) -> None:
        """A1 is face-up initially; calling A1 must reject with ALREADY_REVEALED."""
        controller = GameController(valid_3x3_puzzle)
        res = controller.make_call(CellId("A1"), Status.CRIMINAL)

        assert res.accepted is False
        assert res.rejection_reason == RejectionReason.ALREADY_REVEALED
        assert controller.revision == 0

    def test_rejected_invalid_cell(self, valid_3x3_puzzle: Puzzle) -> None:
        """Calling out-of-bounds or malformed cells rejects with INVALID_CELL."""
        controller = GameController(valid_3x3_puzzle)

        res_oob = controller.make_call(CellId("D1"), Status.CRIMINAL)
        assert res_oob.accepted is False
        assert res_oob.rejection_reason == RejectionReason.INVALID_CELL

        res_malformed = controller.make_call("invalid_coord", Status.CRIMINAL)
        assert res_malformed.accepted is False
        assert res_malformed.rejection_reason == RejectionReason.INVALID_CELL

    def test_rejected_inconsistent_kb(self) -> None:
        """When the base public KB is contradictory, all calls must be rejected with INCONSISTENT."""
        # 2x2 with contradictory revealed clues
        c1 = FactClue("c1", CellId("A1"), CellId("B1"), Status.CRIMINAL)
        c2 = FactClue("c2", CellId("A2"), CellId("B1"), Status.INNOCENT)
        # Dummy filler clues for B1, B2
        c3 = FactClue("c3", CellId("B1"), CellId("B2"), Status.INNOCENT)
        c4 = FactClue("c4", CellId("B2"), CellId("A1"), Status.INNOCENT)
        sol = {
            CellId("A1"): Status.INNOCENT,
            CellId("A2"): Status.INNOCENT,
            CellId("B1"): Status.CRIMINAL,
            CellId("B2"): Status.INNOCENT,
        }
        clues = {CellId("A1"): c1, CellId("A2"): c2, CellId("B1"): c3, CellId("B2"): c4}
        puzzle = make_minimal_puzzle(2, sol, clues, [CellId("A1"), CellId("A2")])

        controller = GameController(puzzle)
        res = controller.make_call(CellId("B1"), Status.CRIMINAL)

        assert res.accepted is False
        assert res.rejection_reason == RejectionReason.INCONSISTENT
        assert controller.revision == 0

    def test_restart_resets_public_state(self, valid_3x3_puzzle: Puzzle) -> None:
        """restart() resets the board to initial face-up cards."""
        controller = GameController(valid_3x3_puzzle)
        res = controller.make_call("B1", "INNOCENT")
        assert res.accepted is True
        assert controller.revision == 1

        state = controller.restart()
        assert controller.revision == 0
        assert state.revision == 0
        assert CellId("B1") not in state.revealed_cells
        assert state.revealed_cells == frozenset({CellId("A1"), CellId("B2")})


# ---------------------------------------------------------------------------
# T13 — Deduction Loop, Auto Solve, and Hints
# ---------------------------------------------------------------------------


class TestDeductionLoopAndTrace:
    def test_single_step_execution(self, valid_3x3_puzzle: Puzzle) -> None:
        """step() selects the first forced cell in row-major order and records trace."""
        controller = GameController(valid_3x3_puzzle)
        assert controller.revision == 0

        step1 = controller.step()
        assert step1 is not None
        assert isinstance(step1, DeductionStep)
        assert step1.step_number == 1
        assert step1.target_cell == CellId("B1")
        assert step1.target_verdict == Status.INNOCENT
        assert step1.revealed_status == Status.INNOCENT
        assert step1.revealed_clue is not None
        assert step1.revealed_clue_id == "c_B1"
        assert "c_A1" in step1.active_clue_ids
        assert step1.state_revision_before == 0
        assert step1.state_revision_after == 1
        assert controller.revision == 1

    def test_auto_solve_full_run_on_progressive_puzzle(
        self, progressive_2x2_puzzle: Puzzle
    ) -> None:
        """auto_solve() solves a progressive puzzle without guessing to completion."""
        controller = GameController(progressive_2x2_puzzle)
        assert not controller.is_solved
        assert controller.revision == 0

        report = controller.auto_solve()

        assert isinstance(report, AutoSolveReport)
        assert report.status == AutoSolveStatus.SOLVED
        assert controller.is_solved is True
        # 4 total cards, 1 started face-up -> 3 steps to solve
        assert report.total_steps == 3
        assert len(report.steps) == 3
        assert report.total_sat_calls > 0
        assert report.aggregate_metrics.runtime >= 0.0

        # Verify step numbers and revisions are strictly sequential 1..3
        for idx, step in enumerate(report.steps, start=1):
            assert step.step_number == idx
            assert step.state_revision_after == idx

    def test_auto_solve_on_already_solved_puzzle(
        self, progressive_2x2_puzzle: Puzzle
    ) -> None:
        """Calling auto_solve() on an already solved puzzle returns ALREADY_SOLVED."""
        controller = GameController(progressive_2x2_puzzle)
        first_report = controller.auto_solve()
        assert first_report.status == AutoSolveStatus.SOLVED
        assert controller.is_solved is True

        second_report = controller.auto_solve()
        assert second_report.status == AutoSolveStatus.ALREADY_SOLVED
        assert second_report.total_steps == 0
        assert len(second_report.steps) == 0

    def test_valid_3x3_opening_reveals_b1_then_stalls_without_guessing(
        self, valid_3x3_puzzle: Puzzle
    ) -> None:
        """fixture puzzle_3x3_valid has unique complete solution, but initial face-up stalls after B1."""
        controller = GameController(valid_3x3_puzzle)
        report = controller.auto_solve()
        # Takes 1 step (B1) then stalls honestly without guessing
        assert report.status == AutoSolveStatus.STALLED
        assert report.total_steps == 1
        assert report.steps[0].target_cell == CellId("B1")
        assert controller.is_solved is False

    def test_auto_solve_stops_at_stalled_without_guessing(self) -> None:
        """When no card is forced, auto_solve() must terminate at STALLED."""
        # 2x2 with no clues forcing anything (SAME clue between unrevealed cells)
        c1 = FactClue("c1", CellId("A1"), CellId("A1"), Status.INNOCENT)  # self-fact
        c2 = FactClue("c2", CellId("A2"), CellId("A2"), Status.INNOCENT)
        c3 = FactClue("c3", CellId("B1"), CellId("B1"), Status.INNOCENT)
        c4 = FactClue("c4", CellId("B2"), CellId("B2"), Status.INNOCENT)
        sol = {
            CellId("A1"): Status.INNOCENT,
            CellId("A2"): Status.INNOCENT,
            CellId("B1"): Status.INNOCENT,
            CellId("B2"): Status.INNOCENT,
        }
        clues = {CellId("A1"): c1, CellId("A2"): c2, CellId("B1"): c3, CellId("B2"): c4}
        # Only A1 face-up: A1 reveals c1 (self-fact), which doesn't constrain A2, B1, B2
        puzzle = make_minimal_puzzle(2, sol, clues, [CellId("A1")])

        controller = GameController(puzzle)
        report = controller.auto_solve()

        assert report.status == AutoSolveStatus.STALLED
        assert controller.is_solved is False
        assert len(report.steps) == 0  # No cards were forced

    def test_auto_solve_stops_at_inconsistent(self) -> None:
        """When public KB is inconsistent, auto_solve() stops at INCONSISTENT."""
        c1 = FactClue("c1", CellId("A1"), CellId("B1"), Status.CRIMINAL)
        c2 = FactClue("c2", CellId("A2"), CellId("B1"), Status.INNOCENT)
        c3 = FactClue("c3", CellId("B1"), CellId("B2"), Status.INNOCENT)
        c4 = FactClue("c4", CellId("B2"), CellId("A1"), Status.INNOCENT)
        sol = {
            CellId("A1"): Status.INNOCENT,
            CellId("A2"): Status.INNOCENT,
            CellId("B1"): Status.CRIMINAL,
            CellId("B2"): Status.INNOCENT,
        }
        clues = {CellId("A1"): c1, CellId("A2"): c2, CellId("B1"): c3, CellId("B2"): c4}
        puzzle = make_minimal_puzzle(2, sol, clues, [CellId("A1"), CellId("A2")])

        controller = GameController(puzzle)
        report = controller.auto_solve()

        assert report.status == AutoSolveStatus.INCONSISTENT
        assert len(report.steps) == 0

    def test_hint_identifies_forced_card_and_relevant_clue(
        self, valid_3x3_puzzle: Puzzle
    ) -> None:
        """hint() identifies B1 as INNOCENT and cites c_A1 without mutating game state."""
        controller = GameController(valid_3x3_puzzle)
        initial_revision = controller.revision
        initial_revealed = set(controller.public_state.revealed_cells)

        hint = controller.hint()

        assert isinstance(hint, Hint)
        assert hint.has_forced_cell is True
        assert hint.cell == CellId("B1")
        assert hint.verdict == Status.INNOCENT
        assert "c_A1" in hint.relevant_clue_ids
        assert hint.base_consistent is True

        # Non-mutating guarantee:
        assert controller.revision == initial_revision
        assert set(controller.public_state.revealed_cells) == initial_revealed

    def test_hint_on_solved_puzzle(self, progressive_2x2_puzzle: Puzzle) -> None:
        """hint() on a solved puzzle reports solved."""
        controller = GameController(progressive_2x2_puzzle)
        rep = controller.auto_solve()
        assert rep.status == AutoSolveStatus.SOLVED

        hint = controller.hint()
        assert hint.has_forced_cell is False
        assert "already completely solved" in hint.message.lower()

    def test_hint_on_stalled_puzzle(self) -> None:
        """hint() on a stalled puzzle reports no character status can be proven."""
        c1 = FactClue("c1", CellId("A1"), CellId("A1"), Status.INNOCENT)
        c2 = FactClue("c2", CellId("A2"), CellId("A2"), Status.INNOCENT)
        c3 = FactClue("c3", CellId("B1"), CellId("B1"), Status.INNOCENT)
        c4 = FactClue("c4", CellId("B2"), CellId("B2"), Status.INNOCENT)
        sol = {
            CellId("A1"): Status.INNOCENT,
            CellId("A2"): Status.INNOCENT,
            CellId("B1"): Status.INNOCENT,
            CellId("B2"): Status.INNOCENT,
        }
        clues = {CellId("A1"): c1, CellId("A2"): c2, CellId("B1"): c3, CellId("B2"): c4}
        puzzle = make_minimal_puzzle(2, sol, clues, [CellId("A1")])

        controller = GameController(puzzle)
        hint = controller.hint()

        assert hint.has_forced_cell is False
        assert "without guessing" in hint.message.lower()


# ---------------------------------------------------------------------------
# Codex Audit Regression Tests (FIX-01, FIX-03, FIX-04, FIX-05)
# ---------------------------------------------------------------------------


class TestHintRedundantRegionalClues:
    def test_hint_with_redundant_regional_clues_does_not_crash(self) -> None:
        """FIX-01: Hint must handle redundant regional clues using resolve_region(region, grid_size)."""
        from griductive.domain.model import ExactlyClue, ExplicitRegion, RowRegion

        # 2x2 grid:
        # A1=CRIMINAL (face-up), A2=INNOCENT (face-up)
        # B1 is forced CRIMINAL by TWO redundant regional clues:
        # Clue 1 on A1: Row 1 has exactly 2 criminals -> forces B1=CRIMINAL
        # Clue 2 on A2: Region (B1, A2) has exactly 1 criminal -> since A2=INNOCENT, forces B1=CRIMINAL
        sol = {
            CellId("A1"): Status.CRIMINAL,
            CellId("B1"): Status.CRIMINAL,
            CellId("A2"): Status.INNOCENT,
            CellId("B2"): Status.INNOCENT,
        }
        c1 = ExactlyClue("c_reg1", CellId("A1"), 2, RowRegion(1))
        c2 = ExactlyClue("c_reg2", CellId("A2"), 1, ExplicitRegion((CellId("B1"), CellId("A2"))))
        c3 = FactClue("c_dummy1", CellId("B1"), CellId("B1"), Status.CRIMINAL)
        c4 = FactClue("c_dummy2", CellId("B2"), CellId("B2"), Status.INNOCENT)

        clues = {
            CellId("A1"): c1,
            CellId("A2"): c2,
            CellId("B1"): c3,
            CellId("B2"): c4,
        }
        puzzle = make_minimal_puzzle(2, sol, clues, [CellId("A1"), CellId("A2")])

        controller = GameController(puzzle)
        initial_revision = controller.revision
        initial_revealed = set(controller.public_state.revealed_cells)

        # Neither clue is strictly necessary alone (deletion of either leaves the other),
        # so structural reference fallback is exercised. Must not crash with TypeError!
        hint = controller.hint()

        assert hint.has_forced_cell is True
        assert hint.cell == CellId("B1")
        assert hint.verdict == Status.CRIMINAL
        assert "c_reg1" in hint.relevant_clue_ids
        assert "c_reg2" in hint.relevant_clue_ids
        # Immutability preserved
        assert controller.revision == initial_revision
        assert set(controller.public_state.revealed_cells) == initial_revealed


class TestHiddenStatusLeakPrevention:
    def test_controller_never_leaks_hidden_solution_status(self) -> None:
        """FIX-03: When an invalid puzzle causes a deduction conflict, private status is not disclosed."""
        # Malformed puzzle: A1 has a false clue claiming B1 is CRIMINAL, but solution says B1 is INNOCENT
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
        puzzle = make_minimal_puzzle(2, sol, clues, [CellId("A1")])

        controller = GameController(puzzle)
        initial_revision = controller.revision
        initial_revealed = set(controller.public_state.revealed_cells)

        # 1. Manual call: public logic entails CRIMINAL, but engine rejects because secret status is INNOCENT
        res = controller.make_call(CellId("B1"), Status.CRIMINAL)
        assert res.accepted is False
        assert res.rejection_reason == RejectionReason.CONTRADICTED
        # The secret status "INNOCENT" must NOT be leaked in the rejection message!
        assert "INNOCENT" not in res.message
        assert controller.revision == initial_revision
        assert set(controller.public_state.revealed_cells) == initial_revealed

        # 2. step() handles internal reveal failure safely without leaking or crashing
        step_res = controller.step()
        assert step_res is None
        assert controller.revision == initial_revision

        # 3. auto_solve() stops safely without leaking private status
        report = controller.auto_solve()
        assert report.status == AutoSolveStatus.INCONSISTENT
        assert "INNOCENT" not in report.message
        assert controller.revision == initial_revision


class TestCompleteDeductionTrace:
    def test_step_trace_captures_all_sat_evidence_and_metrics(
        self, progressive_2x2_puzzle: Puzzle
    ) -> None:
        """FIX-04: DeductionStep captures base query, all examined cell queries, and reconciled metrics."""
        controller = GameController(progressive_2x2_puzzle)
        step = controller.step()
        assert step is not None

        # Base query captured
        assert step.base_query is not None
        assert step.base_query.assumptions == ()
        assert step.base_query.is_sat is True

        # Complete queries list includes base query + unresolved cell queries
        assert len(step.all_queries) >= 1 + len(step.classification.queries)
        assert step.all_queries[0] == step.base_query

        # Step SAT calls count matches all queries
        assert step.step_sat_calls == len(step.all_queries)

        # Step metrics aggregate all queries in the wave
        expected_decisions = sum(q.metrics.decisions for q in step.all_queries)
        expected_propagations = sum(q.metrics.propagations for q in step.all_queries)
        expected_backtracks = sum(q.metrics.backtracks for q in step.all_queries)
        assert step.step_metrics.decisions == expected_decisions
        assert step.step_metrics.propagations == expected_propagations
        assert step.step_metrics.backtracks == expected_backtracks

        # Complete classification evidence
        assert step.all_classifications is not None
        assert step.target_cell in step.all_classifications

    def test_auto_solve_metrics_reconcile_with_steps_and_terminal_checks(
        self, progressive_2x2_puzzle: Puzzle, valid_3x3_puzzle: Puzzle
    ) -> None:
        """FIX-04: AutoSolveReport metrics reconcile exactly across solved and stalled runs."""
        # 1. Solved run
        c_solved = GameController(progressive_2x2_puzzle)
        rep_solved = c_solved.auto_solve()
        assert rep_solved.status == AutoSolveStatus.SOLVED

        sum_sat_calls = sum(s.step_sat_calls for s in rep_solved.steps)
        sum_decisions = sum(s.step_metrics.decisions for s in rep_solved.steps)
        sum_propagations = sum(s.step_metrics.propagations for s in rep_solved.steps)
        sum_backtracks = sum(s.step_metrics.backtracks for s in rep_solved.steps)

        assert rep_solved.total_sat_calls == sum_sat_calls + rep_solved.terminal_sat_calls
        term_dec = rep_solved.terminal_metrics.decisions if rep_solved.terminal_metrics else 0
        term_prop = rep_solved.terminal_metrics.propagations if rep_solved.terminal_metrics else 0
        term_back = rep_solved.terminal_metrics.backtracks if rep_solved.terminal_metrics else 0

        assert rep_solved.aggregate_metrics.decisions == sum_decisions + term_dec
        assert rep_solved.aggregate_metrics.propagations == sum_propagations + term_prop
        assert rep_solved.aggregate_metrics.backtracks == sum_backtracks + term_back

        # 2. Stalled run
        c_stalled = GameController(valid_3x3_puzzle)
        rep_stalled = c_stalled.auto_solve()
        assert rep_stalled.status == AutoSolveStatus.STALLED
        assert rep_stalled.terminal_sat_calls > 0
        assert rep_stalled.terminal_metrics is not None

        sum_sat_stalled = sum(s.step_sat_calls for s in rep_stalled.steps)
        assert (
            rep_stalled.total_sat_calls
            == sum_sat_stalled + rep_stalled.terminal_sat_calls
        )
        assert (
            rep_stalled.aggregate_metrics.decisions
            == sum(s.step_metrics.decisions for s in rep_stalled.steps)
            + rep_stalled.terminal_metrics.decisions
        )


class TestMaxStepsStepLimitReached:
    def test_max_steps_reports_step_limit_reached_when_moves_remain(
        self, progressive_2x2_puzzle: Puzzle
    ) -> None:
        """FIX-05: Reaching max_steps must report STEP_LIMIT_REACHED, not STALLED."""
        controller = GameController(progressive_2x2_puzzle)
        report = controller.auto_solve(max_steps=1)

        assert report.status == AutoSolveStatus.STEP_LIMIT_REACHED
        assert report.total_steps == 1
        assert len(report.steps) == 1
        assert "maximum step limit" in report.message.lower()

        # Another forced move definitely remains
        hint = controller.hint()
        assert hint.has_forced_cell is True

    def test_max_steps_zero_and_negative(
        self, progressive_2x2_puzzle: Puzzle
    ) -> None:
        """FIX-05: max_steps <= 0 stops immediately without guessing or running steps."""
        c0 = GameController(progressive_2x2_puzzle)
        rep0 = c0.auto_solve(max_steps=0)
        assert rep0.status == AutoSolveStatus.STEP_LIMIT_REACHED
        assert rep0.total_steps == 0
        assert rep0.total_sat_calls == 0

        c_neg = GameController(progressive_2x2_puzzle)
        rep_neg = c_neg.auto_solve(max_steps=-1)
        assert rep_neg.status == AutoSolveStatus.STEP_LIMIT_REACHED
        assert rep_neg.total_steps == 0
        assert rep_neg.total_sat_calls == 0


# ---------------------------------------------------------------------------
# Architecture Isolation
# ---------------------------------------------------------------------------


class TestArchitectureIsolation:
    def test_controller_does_not_import_forbidden_modules(self) -> None:
        """controller.py must not import validation or gui."""
        import ast

        ctrl_path = (
            Path(__file__).resolve().parent.parent / "src" / "griductive" / "game" / "controller.py"
        )
        tree = ast.parse(ctrl_path.read_text(encoding="utf-8"))
        forbidden = {"validation", "gui"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(f in alias.name for f in forbidden), (
                        f"Forbidden import in controller.py: {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert not any(f in node.module for f in forbidden), (
                        f"Forbidden 'from' import in controller.py: {node.module}"
                    )
