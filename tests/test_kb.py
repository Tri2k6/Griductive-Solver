"""Comprehensive unit tests for Public Knowledge Base Construction (T10).

Tests strict public/private isolation, deterministic rebuilds, empty and
partially revealed states, multiple active clues and known verdicts,
counts reporting, and semantic consistency.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

import pytest

from griductive.solver.cnf import AuxAllocator, PrimaryVarMap
from griductive.game.engine import GameEngine
from griductive.solver.kb import KnowledgeBase, KnowledgeBaseBuilder, build_knowledge_base
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
    """Build a minimal valid PublicState for KB tests."""
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


# ---------------------------------------------------------------------------
# 1. Public/Private Isolation Tests
# ---------------------------------------------------------------------------


class TestPublicPrivateIsolation:
    def test_kb_builder_accepts_only_public_state(self) -> None:
        """KB builder accepts PublicState and does not accept a private Puzzle."""
        # Create minimal private puzzle
        all_cells = [CellId.from_coords(r, c) for r in (1, 2) for c in (1, 2)]
        chars = [Character(cell, f"Name_{chr(65 + i)}", "Job") for i, cell in enumerate(all_cells)]
        clues = {c: FactClue(f"f_{c.name}", c, c, Status.CRIMINAL) for c in all_cells}
        sol = {c: Status.CRIMINAL for c in all_cells}
        puzzle = Puzzle(grid_size=2, characters=tuple(chars), solution=sol, clues=clues, initial_face_up=frozenset({all_cells[0]}))

        with pytest.raises(AttributeError):
            build_knowledge_base(puzzle)  # type: ignore[arg-type]

    def test_different_hidden_solutions_yield_identical_kb_for_same_public_state(self) -> None:
        """Changing hidden solutions on unrevealed cells does not change the public KB."""
        all_cells = [CellId.from_coords(r, c) for r in (1, 2) for c in (1, 2)]
        chars = [Character(cell, f"Name_{chr(65 + i)}", "Job") for i, cell in enumerate(all_cells)]
        face_up_cell = CellId("A1")
        clue_a1 = FactClue("f1", face_up_cell, CellId("B1"), Status.CRIMINAL)

        # Puzzle 1: face_up is INNOCENT, hidden B1 is CRIMINAL, B2 is INNOCENT
        sol1 = {
            CellId("A1"): Status.INNOCENT,
            CellId("B1"): Status.CRIMINAL,
            CellId("A2"): Status.INNOCENT,
            CellId("B2"): Status.INNOCENT,
        }
        clues1 = {
            CellId("A1"): clue_a1,
            CellId("B1"): FactClue("f2_a", CellId("B1"), CellId("B1"), Status.CRIMINAL),
            CellId("A2"): FactClue("f3_a", CellId("A2"), CellId("A2"), Status.INNOCENT),
            CellId("B2"): FactClue("f4_a", CellId("B2"), CellId("B2"), Status.INNOCENT),
        }
        p1 = Puzzle(2, tuple(chars), sol1, clues1, frozenset({face_up_cell}))
        engine1 = GameEngine(p1)
        public1 = engine1.public_view()

        # Puzzle 2: face_up is SAME (INNOCENT), but HIDDEN solution for B2 is CRIMINAL, different hidden clues
        sol2 = {
            CellId("A1"): Status.INNOCENT,
            CellId("B1"): Status.CRIMINAL,
            CellId("A2"): Status.INNOCENT,
            CellId("B2"): Status.CRIMINAL,  # Differs from puzzle 1
        }
        clues2 = {
            CellId("A1"): clue_a1,
            CellId("B1"): FactClue("f2_b", CellId("B1"), CellId("B1"), Status.CRIMINAL),
            CellId("A2"): FactClue("f3_b", CellId("A2"), CellId("A2"), Status.INNOCENT),
            CellId("B2"): FactClue("f4_b", CellId("B2"), CellId("B2"), Status.CRIMINAL),  # Differs
        }
        p2 = Puzzle(2, tuple(chars), sol2, clues2, frozenset({face_up_cell}))
        engine2 = GameEngine(p2)
        public2 = engine2.public_view()

        kb1 = build_knowledge_base(public1)
        kb2 = build_knowledge_base(public2)

        # Knowledge bases must be completely identical
        assert kb1.clauses == kb2.clauses
        assert kb1.num_primary == kb2.num_primary
        assert kb1.num_aux == kb2.num_aux
        assert kb1.num_clauses == kb2.num_clauses
        assert kb1.active_clue_ids == kb2.active_clue_ids
        assert kb1.known_statuses == kb2.known_statuses


# ---------------------------------------------------------------------------
# 2. Deterministic Rebuild Tests
# ---------------------------------------------------------------------------


class TestDeterministicRebuild:
    def test_repeated_builds_produce_identical_kb(self) -> None:
        clue1 = FactClue("f1", CellId("A1"), CellId("B1"), Status.CRIMINAL)
        clue2 = SameClue("s1", CellId("B1"), CellId("A1"), CellId("A2"))
        state = make_test_public_state(2, [clue1, clue2], {CellId("A1"): Status.INNOCENT, CellId("B1"): Status.CRIMINAL})

        kb_first = build_knowledge_base(state)
        for _ in range(5):
            kb_next = build_knowledge_base(state)
            assert kb_first.clauses == kb_next.clauses
            assert kb_first.num_clauses == kb_next.num_clauses
            assert kb_first.num_primary == kb_next.num_primary
            assert kb_first.num_aux == kb_next.num_aux
            assert kb_first.active_clue_ids == kb_next.active_clue_ids
            assert kb_first.revision == kb_next.revision


# ---------------------------------------------------------------------------
# 3. Empty and Partially Revealed States
# ---------------------------------------------------------------------------


class TestEmptyAndPartialStates:
    def test_empty_public_state_no_reveals(self) -> None:
        """When 0 cards are revealed, KB has 0 clauses, N^2 primary vars, 0 aux vars."""
        state = make_test_public_state(3, [], {})
        kb = build_knowledge_base(state)

        assert kb.num_clauses == 0
        assert kb.num_primary == 9
        assert kb.num_aux == 0
        assert kb.num_vars == 9
        assert kb.active_clue_ids == ()
        assert len(kb.known_statuses) == 0

    def test_single_card_revealed_with_fact_clue(self) -> None:
        """1 card revealed with status INNOCENT and clue FACT(B1, CRIMINAL).

        Clauses: 1 unit for A1=INNOCENT (-1,), 1 unit for B1=CRIMINAL (+2,).
        Total clauses: 2. Aux: 0.
        """
        clue = FactClue("f1", CellId("A1"), CellId("B1"), Status.CRIMINAL)
        state = make_test_public_state(2, [clue], {CellId("A1"): Status.INNOCENT}, revision=1)
        kb = build_knowledge_base(state)

        assert kb.revision == 1
        assert kb.num_clauses == 2
        assert (-1,) in kb.clauses
        assert (2,) in kb.clauses
        assert kb.num_aux == 0
        assert kb.active_clue_ids == ("f1",)


# ---------------------------------------------------------------------------
# 4. Multiple Active Clues & Verdicts
# ---------------------------------------------------------------------------


class TestMultipleActiveClues:
    def test_mixed_core_and_extension_clues(self) -> None:
        """Mix of SAME, AT_MOST, and PARITY clues."""
        c1 = SameClue("same_1", CellId("A1"), CellId("A1"), CellId("B1"))
        c2 = AtMostClue("am_1", CellId("A2"), k=1, region=RowRegion(1))  # row 1 (A1, B1, C1 on 3x3)
        c3 = ParityClue("par_1", CellId("A3"), parity=Parity.EVEN, region=RowRegion(2))

        statuses = {
            CellId("A1"): Status.INNOCENT,
            CellId("A2"): Status.CRIMINAL,
            CellId("A3"): Status.INNOCENT,
        }
        state = make_test_public_state(3, [c1, c2, c3], statuses, revision=3)
        kb = build_knowledge_base(state)

        assert kb.revision == 3
        assert kb.active_clue_ids == ("same_1", "am_1", "par_1")
        assert kb.num_primary == 9

        # Known statuses: 3 units
        # SAME: 2 clauses
        # AT_MOST(1, size 3): 1 + (3-1)*(2*1+1) = 7 clauses (3 aux)
        # PARITY(EVEN, size 3): 4*(3-1) + 1 = 9 clauses (2 aux)
        # Total clauses: 3 + 2 + 7 + 9 = 21 clauses
        assert kb.num_clauses == 21
        assert kb.num_aux == 3 + 2  # 5 aux
        assert kb.num_vars == 9 + 5  # 14 vars


# ---------------------------------------------------------------------------
# 5. Semantic Consistency
# ---------------------------------------------------------------------------


class TestSemanticConsistency:
    def test_kb_satisfaction_matches_semantics(self) -> None:
        """For complete assignments, KB is satisfied iff all revealed clues and statuses hold."""
        grid_size = 2
        pmap = PrimaryVarMap(grid_size)
        c1 = FactClue("f1", CellId("A1"), CellId("B1"), Status.CRIMINAL)
        c2 = DifferentClue("d1", CellId("A2"), CellId("A1"), CellId("B2"))
        statuses = {CellId("A1"): Status.INNOCENT, CellId("A2"): Status.CRIMINAL}

        state = make_test_public_state(grid_size, [c1, c2], statuses)
        kb = build_knowledge_base(state)

        # Test all 16 complete assignments of 2x2
        cells = [CellId("A1"), CellId("B1"), CellId("A2"), CellId("B2")]
        for bits in range(16):
            asgn: dict[CellId, Status] = {}
            for i, c in enumerate(cells):
                asgn[c] = Status.CRIMINAL if ((bits >> i) & 1) else Status.INNOCENT

            # Direct semantics evaluation
            sem_a1_ok = (asgn[CellId("A1")] == Status.INNOCENT)
            sem_a2_ok = (asgn[CellId("A2")] == Status.CRIMINAL)
            sem_c1_ok = evaluate_clue(c1, asgn, grid_size)
            sem_c2_ok = evaluate_clue(c2, asgn, grid_size)
            expected_sat = sem_a1_ok and sem_a2_ok and sem_c1_ok and sem_c2_ok

            # CNF clauses evaluation (0 aux vars for FACT and DIFFERENT)
            var_asgn = {pmap.cell_to_var(c): (s == Status.CRIMINAL) for c, s in asgn.items()}
            cnf_sat = all(
                any((lit > 0 and var_asgn[abs(lit)]) or (lit < 0 and not var_asgn[abs(lit)]) for lit in cl)
                for cl in kb.clauses
            )
            assert cnf_sat == expected_sat


# ---------------------------------------------------------------------------
# 6. Architecture Isolation
# ---------------------------------------------------------------------------


class TestArchitectureIsolation:
    def test_kb_does_not_import_forbidden_modules(self) -> None:
        """kb.py must not import engine, semantics, dpll, logic, controller, gui, or validation."""
        kb_path = (
            Path(__file__).resolve().parent.parent / "src" / "griductive" / "solver" / "kb.py"
        )
        tree = ast.parse(kb_path.read_text(encoding="utf-8"))
        forbidden = {
            "engine", "semantics", "dpll", "logic",
            "controller", "gui", "validation",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(f in alias.name for f in forbidden), (
                        f"Forbidden import in kb.py: {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert not any(f in node.module for f in forbidden), (
                        f"Forbidden 'from' import in kb.py: {node.module}"
                    )
