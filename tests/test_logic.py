"""Comprehensive unit tests for SAT-based entailment classification (T11).

Tests sound refutation-based classification:
- Base consistency check and INCONSISTENT handling
- Forced Criminal classification (refutation of NOT C_i)
- Forced Innocent classification (refutation of C_i)
- Ambiguous UNKNOWN classification (both branches SAT)
- Multiple unresolved characters in deterministic row-major order
- SAT model independence (never inferring a verdict from one model alone)
- Cross-check against an independent brute-force oracle
- Strict public/private isolation (hidden data cannot influence proof)
- Architectural isolation (AST check)
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

import pytest

from griductive.game.engine import GameEngine
from griductive.solver.logic import (
    CellClassification,
    LogicAgent,
    ProofReport,
    ProofService,
    SatQueryRecord,
)
from griductive.domain.model import (
    AtLeastClue,
    AtMostClue,
    CellId,
    Character,
    DifferentClue,
    ExactlyClue,
    FactClue,
    Parity,
    ParityClue,
    PublicCard,
    PublicState,
    Puzzle,
    RowRegion,
    SameClue,
    Status,
    Verdict,
)
from griductive.domain.semantics import evaluate_clue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_test_public_state(
    grid_size: int,
    revealed_clues: Sequence,
    known_statuses: Mapping[CellId, Status] | None = None,
    revision: int = 0,
) -> PublicState:
    """Build a valid PublicState for logic tests."""
    known: dict[CellId, Status] = dict(known_statuses or {})
    all_cells = [
        CellId.from_coords(r, c)
        for r in range(1, grid_size + 1)
        for c in range(1, grid_size + 1)
    ]
    characters = [
        Character(cell=cell, name=f"Person_{chr(65 + i)}", profession="Tester")
        for i, cell in enumerate(sorted(all_cells))
    ]
    char_by_cell = {ch.cell: ch for ch in characters}
    clue_by_owner = {clue.owner: clue for clue in revealed_clues}

    for clue in revealed_clues:
        if clue.owner not in known:
            known[clue.owner] = Status.INNOCENT

    cards = {}
    for cell in all_cells:
        is_rev = cell in known
        cards[cell] = PublicCard(
            cell=cell,
            character=char_by_cell[cell],
            is_revealed=is_rev,
            status=known.get(cell) if is_rev else None,
            clue=clue_by_owner.get(cell) if is_rev else None,
        )

    return PublicState(
        grid_size=grid_size,
        characters=tuple(characters),
        cards=cards,
        known_statuses=known,
        revealed_clues=tuple(sorted(revealed_clues, key=lambda c: c.owner)),
        revealed_cells=frozenset(known.keys()),
        revision=revision,
    )


def independent_brute_force_entailment(
    state: PublicState,
) -> tuple[bool, dict[CellId, Verdict]]:
    """Independent semantic brute-force oracle.

    Enumerates all 2^(N^2) complete assignments, tests each against all revealed
    clues and known statuses using direct semantics, and derives sound verdicts.
    """
    grid_size = state.grid_size
    all_cells = [
        CellId.from_coords(r, c)
        for r in range(1, grid_size + 1)
        for c in range(1, grid_size + 1)
    ]
    unresolved_cells = [c for c in all_cells if c not in state.revealed_cells]

    # Find all models satisfying all revealed clues and known statuses
    satisfying_models: list[dict[CellId, Status]] = []
    total_assignments = 1 << len(all_cells)

    for bits in range(total_assignments):
        assignment: dict[CellId, Status] = {}
        for idx, cell in enumerate(all_cells):
            assignment[cell] = Status.CRIMINAL if ((bits >> idx) & 1) else Status.INNOCENT

        # Check known statuses
        status_ok = True
        for cell, known_status in state.known_statuses.items():
            if assignment[cell] != known_status:
                status_ok = False
                break
        if not status_ok:
            continue

        # Check revealed clues
        clues_ok = True
        for clue in state.revealed_clues:
            if not evaluate_clue(clue, assignment, grid_size):
                clues_ok = False
                break
        if not clues_ok:
            continue

        satisfying_models.append(assignment)

    if not satisfying_models:
        # Base is inconsistent
        return False, {c: Verdict.INCONSISTENT for c in unresolved_cells}

    verdicts: dict[CellId, Verdict] = {}
    for cell in unresolved_cells:
        criminal_count = sum(1 for m in satisfying_models if m[cell] == Status.CRIMINAL)
        if criminal_count == len(satisfying_models):
            verdicts[cell] = Verdict.CRIMINAL
        elif criminal_count == 0:
            verdicts[cell] = Verdict.INNOCENT
        else:
            verdicts[cell] = Verdict.UNKNOWN

    return True, verdicts


# ---------------------------------------------------------------------------
# 1. Forced Criminal Cases
# ---------------------------------------------------------------------------


class TestForcedCriminal:
    def test_fact_clue_forces_criminal(self) -> None:
        """Revealed clue FACT(B1, CRIMINAL) forces unresolved B1 to be CRIMINAL."""
        c = FactClue("f1", owner=CellId("A1"), target=CellId("B1"), status=Status.CRIMINAL)
        state = make_test_public_state(2, [c], {CellId("A1"): Status.INNOCENT})

        report = ProofService.classify_state(state)
        assert report.base_consistent is True
        assert report.classifications[CellId("B1")].verdict == Verdict.CRIMINAL
        # Refutation query on NOT B1 was UNSAT
        b1_cls = report.classifications[CellId("B1")]
        assert len(b1_cls.queries) == 1
        assert b1_cls.queries[0].is_sat is False

    def test_same_clue_with_criminal_forces_criminal(self) -> None:
        """Revealed card A1 is CRIMINAL, with clue SAME(A1, B1) -> B1 forced CRIMINAL."""
        c = SameClue("s1", owner=CellId("A1"), person_a=CellId("A1"), person_b=CellId("B1"))
        state = make_test_public_state(2, [c], {CellId("A1"): Status.CRIMINAL})

        report = ProofService.classify_state(state)
        assert report.base_consistent is True
        assert report.classifications[CellId("B1")].verdict == Verdict.CRIMINAL


# ---------------------------------------------------------------------------
# 2. Forced Innocent Cases
# ---------------------------------------------------------------------------


class TestForcedInnocent:
    def test_fact_clue_forces_innocent(self) -> None:
        """Revealed clue FACT(B1, INNOCENT) forces unresolved B1 to be INNOCENT."""
        c = FactClue("f1", owner=CellId("A1"), target=CellId("B1"), status=Status.INNOCENT)
        state = make_test_public_state(2, [c], {CellId("A1"): Status.CRIMINAL})

        report = ProofService.classify_state(state)
        assert report.base_consistent is True
        assert report.classifications[CellId("B1")].verdict == Verdict.INNOCENT
        b1_cls = report.classifications[CellId("B1")]
        # Query 1 (assume NOT B1 = Innocent) is SAT; Query 2 (assume B1 = Criminal) is UNSAT
        assert len(b1_cls.queries) == 2
        assert b1_cls.queries[0].is_sat is True
        assert b1_cls.queries[1].is_sat is False

    def test_different_clue_forces_innocent(self) -> None:
        """Revealed card A1 is CRIMINAL, with clue DIFFERENT(A1, B1) -> B1 forced INNOCENT."""
        c = DifferentClue("d1", owner=CellId("A1"), person_a=CellId("A1"), person_b=CellId("B1"))
        state = make_test_public_state(2, [c], {CellId("A1"): Status.CRIMINAL})

        report = ProofService.classify_state(state)
        assert report.base_consistent is True
        assert report.classifications[CellId("B1")].verdict == Verdict.INNOCENT


# ---------------------------------------------------------------------------
# 3. Ambiguous UNKNOWN Cases
# ---------------------------------------------------------------------------


class TestAmbiguousUnknown:
    def test_unconstrained_cells_are_unknown(self) -> None:
        """A1 is revealed INNOCENT with self-fact; all unresolved cells (B1, A2, B2) are UNKNOWN."""
        clue = FactClue("f1", CellId("A1"), CellId("A1"), Status.INNOCENT)
        state = make_test_public_state(2, [clue], {CellId("A1"): Status.INNOCENT})

        report = ProofService.classify_state(state)
        assert report.base_consistent is True
        for cell in (CellId("B1"), CellId("A2"), CellId("B2")):
            cls = report.classifications[cell]
            assert cls.verdict == Verdict.UNKNOWN
            # Both queries SAT
            assert len(cls.queries) == 2
            assert cls.queries[0].is_sat is True
            assert cls.queries[1].is_sat is True

        assert len(report.forced_cells) == 0
        assert report.first_forced_cell is None

    def test_completely_empty_public_state_all_cells_unknown(self) -> None:
        """Completely empty state with 0 reveals: all 4 cells are unresolved and UNKNOWN."""
        state = make_test_public_state(2, [], {})
        report = ProofService.classify_state(state)
        assert report.base_consistent is True
        assert len(report.classifications) == 4
        for cell in (CellId("A1"), CellId("B1"), CellId("A2"), CellId("B2")):
            assert report.classifications[cell].verdict == Verdict.UNKNOWN

    def test_single_model_does_not_force_verdict(self) -> None:
        """DPLL finds a satisfying model where B1 is False, but B1 can also be True -> UNKNOWN."""
        # Clue: AT_LEAST(1, RowRegion(1)) on 2x2. A1 is already known INNOCENT.
        # This forces B1 to be CRIMINAL.
        # But for A2, neither status is constrained: A2 must be UNKNOWN.
        c = AtLeastClue("al1", CellId("A1"), k=1, region=RowRegion(1))
        state = make_test_public_state(2, [c], {CellId("A1"): Status.INNOCENT})

        report = ProofService.classify_state(state)
        assert report.classifications[CellId("B1")].verdict == Verdict.CRIMINAL
        assert report.classifications[CellId("A2")].verdict == Verdict.UNKNOWN
        assert report.classifications[CellId("B2")].verdict == Verdict.UNKNOWN


# ---------------------------------------------------------------------------
# 4. Inconsistent KB Cases
# ---------------------------------------------------------------------------


class TestInconsistentKB:
    def test_contradictory_revealed_clues_yield_inconsistent(self) -> None:
        """Two revealed clues contradict each other: FACT(B1, CRIMINAL) and FACT(B1, INNOCENT)."""
        c1 = FactClue("f1", CellId("A1"), CellId("B1"), Status.CRIMINAL)
        c2 = FactClue("f2", CellId("A2"), CellId("B1"), Status.INNOCENT)
        state = make_test_public_state(
            2, [c1, c2], {CellId("A1"): Status.INNOCENT, CellId("A2"): Status.INNOCENT}
        )

        report = ProofService.classify_state(state)
        assert report.base_consistent is False
        assert report.base_query.is_sat is False

        # All unresolved cells must be marked INCONSISTENT
        for cell in (CellId("B1"), CellId("B2")):
            assert report.classifications[cell].verdict == Verdict.INCONSISTENT
            assert len(report.classifications[cell].queries) == 0

        # No forced cells on inconsistent state
        assert len(report.forced_cells) == 0
        # Exactly 1 SAT call executed (stops immediately after base UNSAT)
        assert report.total_sat_calls == 1

    def test_classify_cell_on_inconsistent_state(self) -> None:
        c1 = FactClue("f1", CellId("A1"), CellId("B1"), Status.CRIMINAL)
        c2 = FactClue("f2", CellId("A2"), CellId("B1"), Status.INNOCENT)
        state = make_test_public_state(
            2, [c1, c2], {CellId("A1"): Status.INNOCENT, CellId("A2"): Status.INNOCENT}
        )

        # Unresolved cell B1 must be INCONSISTENT
        cls = ProofService.classify_cell(state, CellId("B1"))
        assert cls.verdict == Verdict.INCONSISTENT
        assert len(cls.queries) == 0

    def test_classify_revealed_cell_on_inconsistent_state_returns_inconsistent(self) -> None:
        """FIX-02 regression test: revealed cells in an inconsistent KB must return INCONSISTENT."""
        c1 = FactClue("f1", CellId("A1"), CellId("B1"), Status.CRIMINAL)
        c2 = FactClue("f2", CellId("A2"), CellId("B1"), Status.INNOCENT)
        state = make_test_public_state(
            2, [c1, c2], {CellId("A1"): Status.INNOCENT, CellId("A2"): Status.INNOCENT}
        )

        # Both revealed cells must be classified as INCONSISTENT because the whole KB is UNSAT
        cls_a1 = ProofService.classify_cell(state, CellId("A1"))
        assert cls_a1.verdict == Verdict.INCONSISTENT
        assert len(cls_a1.queries) == 0

        cls_a2 = ProofService.classify_cell(state, CellId("A2"))
        assert cls_a2.verdict == Verdict.INCONSISTENT
        assert len(cls_a2.queries) == 0

    def test_classify_state_and_cell_semantic_consistency(self) -> None:
        """classify_state and classify_cell agree on inconsistent and consistent public states."""
        c1 = FactClue("f1", CellId("A1"), CellId("B1"), Status.CRIMINAL)
        c2 = FactClue("f2", CellId("A2"), CellId("B1"), Status.INNOCENT)
        inconsistent_state = make_test_public_state(
            2, [c1, c2], {CellId("A1"): Status.INNOCENT, CellId("A2"): Status.INNOCENT}
        )

        report = ProofService.classify_state(inconsistent_state)
        assert report.base_consistent is False
        for cell in report.classifications.keys():
            cell_cls = ProofService.classify_cell(inconsistent_state, cell)
            assert cell_cls.verdict == report.classifications[cell].verdict == Verdict.INCONSISTENT

        # Consistent state check
        consistent_clue = FactClue("f1", CellId("A1"), CellId("B1"), Status.CRIMINAL)
        consistent_state = make_test_public_state(
            2, [consistent_clue], {CellId("A1"): Status.INNOCENT}
        )
        report_consistent = ProofService.classify_state(consistent_state)
        assert report_consistent.base_consistent is True
        for cell in report_consistent.classifications.keys():
            cell_cls = ProofService.classify_cell(consistent_state, cell)
            assert cell_cls.verdict == report_consistent.classifications[cell].verdict
        # Revealed cell on consistent state returns its known status
        cls_rev = ProofService.classify_cell(consistent_state, CellId("A1"))
        assert cls_rev.verdict == Verdict.INNOCENT


# ---------------------------------------------------------------------------
# 5. Deterministic Ordering & Multi-Card
# ---------------------------------------------------------------------------


class TestDeterministicOrdering:
    def test_unresolved_cells_ordered_row_major(self) -> None:
        """Unresolved cards are processed in deterministic row-major order."""
        # 3x3 with only center B2 revealed
        c = FactClue("f", CellId("B2"), CellId("C3"), Status.CRIMINAL)
        state = make_test_public_state(3, [c], {CellId("B2"): Status.INNOCENT})

        report = ProofService.classify_state(state)
        classified_cells = list(report.classifications.keys())
        expected_cells = [
            CellId("A1"), CellId("B1"), CellId("C1"),
            CellId("A2"),               CellId("C2"),
            CellId("A3"), CellId("B3"), CellId("C3"),
        ]
        assert classified_cells == expected_cells

    def test_first_forced_cell_picks_lowest_row_major(self) -> None:
        """When multiple cells are forced, first_forced_cell returns the lowest row-major."""
        # Clues forcing both C1 and A2 to be CRIMINAL
        c1 = FactClue("f_c1", CellId("A1"), CellId("C1"), Status.CRIMINAL)
        c2 = FactClue("f_a2", CellId("B1"), CellId("A2"), Status.CRIMINAL)
        state = make_test_public_state(
            3, [c1, c2], {CellId("A1"): Status.INNOCENT, CellId("B1"): Status.INNOCENT}
        )

        report = ProofService.classify_state(state)
        # C1 is row 1, col 3. A2 is row 2, col 1.
        # In row-major order: C1 comes before A2.
        assert report.first_forced_cell is not None
        assert report.first_forced_cell.cell == CellId("C1")
        assert report.first_forced_cell.verdict == Verdict.CRIMINAL


# ---------------------------------------------------------------------------
# 6. Brute-Force Oracle Cross-Check
# ---------------------------------------------------------------------------


class TestBruteForceCrossCheck:
    @pytest.mark.parametrize(
        "revealed_clues,known_statuses",
        [
            # Case 1: Simple FACT
            (
                [FactClue("f1", CellId("A1"), CellId("B2"), Status.CRIMINAL)],
                {CellId("A1"): Status.INNOCENT},
            ),
            # Case 2: SAME + DIFFERENT chain
            (
                [
                    SameClue("s1", CellId("A1"), CellId("A1"), CellId("B1")),
                    DifferentClue("d1", CellId("A2"), CellId("B1"), CellId("B2")),
                ],
                {CellId("A1"): Status.CRIMINAL, CellId("A2"): Status.INNOCENT},
            ),
            # Case 3: EXACTLY cardinality
            (
                [ExactlyClue("ex1", CellId("A1"), k=2, region=RowRegion(1))],
                {CellId("A1"): Status.CRIMINAL},
            ),
            # Case 4: PARITY
            (
                [ParityClue("p1", CellId("A1"), parity=Parity.ODD, region=RowRegion(1))],
                {CellId("A1"): Status.INNOCENT},
            ),
            # Case 5: Contradiction / INCONSISTENT
            (
                [
                    FactClue("f1", CellId("A1"), CellId("B1"), Status.CRIMINAL),
                    FactClue("f2", CellId("A2"), CellId("B1"), Status.INNOCENT),
                ],
                {CellId("A1"): Status.INNOCENT, CellId("A2"): Status.INNOCENT},
            ),
        ],
    )
    def test_entailment_matches_oracle(
        self, revealed_clues: Sequence, known_statuses: Mapping[CellId, Status]
    ) -> None:
        state = make_test_public_state(2, revealed_clues, known_statuses)

        # Oracle evaluation
        oracle_consistent, oracle_verdicts = independent_brute_force_entailment(state)

        # ProofService evaluation
        report = ProofService.classify_state(state)

        assert report.base_consistent == oracle_consistent
        for cell, expected_verdict in oracle_verdicts.items():
            assert cell in report.classifications
            actual_verdict = report.classifications[cell].verdict
            assert actual_verdict == expected_verdict, (
                f"Verdict mismatch for cell {cell}: expected {expected_verdict}, got {actual_verdict}"
            )


# ---------------------------------------------------------------------------
# 7. Strict Public/Private Isolation
# ---------------------------------------------------------------------------


class TestPublicPrivateIsolation:
    def test_logic_agent_requires_public_state(self) -> None:
        with pytest.raises(TypeError, match="LogicAgent requires PublicState"):
            LogicAgent("not a public state")  # type: ignore[arg-type]

    def test_hidden_solution_cannot_influence_agent_verdicts(self) -> None:
        """Two puzzle engines with different hidden solutions yield identical LogicAgent verdicts."""
        all_cells = [CellId.from_coords(r, c) for r in (1, 2) for c in (1, 2)]
        chars = [Character(cell, f"Name_{chr(65 + i)}", "Job") for i, cell in enumerate(all_cells)]
        face_up_cell = CellId("A1")
        clue_a1 = FactClue("f1", face_up_cell, CellId("B1"), Status.CRIMINAL)

        # Puzzle 1
        p1 = Puzzle(
            2,
            tuple(chars),
            {CellId("A1"): Status.INNOCENT, CellId("B1"): Status.CRIMINAL, CellId("A2"): Status.INNOCENT, CellId("B2"): Status.INNOCENT},
            {
                CellId("A1"): clue_a1,
                CellId("B1"): FactClue("f2_a", CellId("B1"), CellId("B1"), Status.CRIMINAL),
                CellId("A2"): FactClue("f3_a", CellId("A2"), CellId("A2"), Status.INNOCENT),
                CellId("B2"): FactClue("f4_a", CellId("B2"), CellId("B2"), Status.INNOCENT),
            },
            frozenset({face_up_cell}),
        )
        engine1 = GameEngine(p1)

        # Puzzle 2: Different hidden solution for B2
        p2 = Puzzle(
            2,
            tuple(chars),
            {CellId("A1"): Status.INNOCENT, CellId("B1"): Status.CRIMINAL, CellId("A2"): Status.INNOCENT, CellId("B2"): Status.CRIMINAL},
            {
                CellId("A1"): clue_a1,
                CellId("B1"): FactClue("f2_b", CellId("B1"), CellId("B1"), Status.CRIMINAL),
                CellId("A2"): FactClue("f3_b", CellId("A2"), CellId("A2"), Status.INNOCENT),
                CellId("B2"): FactClue("f4_b", CellId("B2"), CellId("B2"), Status.CRIMINAL),
            },
            frozenset({face_up_cell}),
        )
        engine2 = GameEngine(p2)

        agent1 = LogicAgent(engine1.public_view())
        agent2 = LogicAgent(engine2.public_view())

        rep1 = agent1.classify_all()
        rep2 = agent2.classify_all()

        assert rep1.base_consistent == rep2.base_consistent
        assert rep1.total_sat_calls == rep2.total_sat_calls
        for cell in rep1.classifications:
            assert rep1.classifications[cell].verdict == rep2.classifications[cell].verdict


# ---------------------------------------------------------------------------
# 8. Architecture Isolation
# ---------------------------------------------------------------------------


class TestArchitectureIsolation:
    def test_logic_does_not_import_forbidden_modules(self) -> None:
        """logic.py must not import engine, semantics, controller, gui, or validation."""
        logic_path = (
            Path(__file__).resolve().parent.parent / "src" / "griductive" / "solver" / "logic.py"
        )
        tree = ast.parse(logic_path.read_text(encoding="utf-8"))
        forbidden = {
            "engine", "semantics",
            "controller", "gui", "validation",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(f in alias.name for f in forbidden), (
                        f"Forbidden import in logic.py: {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert not any(f in node.module for f in forbidden), (
                        f"Forbidden 'from' import in logic.py: {node.module}"
                    )
