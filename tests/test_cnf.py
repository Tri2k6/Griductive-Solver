"""Comprehensive unit tests for CNF primitives and binary clue encoding (T06)."""

import ast
from pathlib import Path
from typing import Mapping

import pytest

from griductive.solver.cnf import (
    AuxAllocator,
    CNFFormula,
    PrimaryVarMap,
    build_cnf_from_public_state,
    encode_different,
    encode_fact,
    encode_known_status,
    encode_same,
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
    RowRegion,
    SameClue,
    Status,
)
from griductive.domain.semantics import evaluate_different, evaluate_fact, evaluate_same


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_clause_satisfied(clause: tuple[int, ...], assignment: Mapping[int, bool]) -> bool:
    """Check if a single clause is satisfied under a variable truth assignment."""
    for lit in clause:
        var = abs(lit)
        val = assignment[var]
        if (lit > 0 and val) or (lit < 0 and not val):
            return True
    return False


def is_cnf_satisfied(
    clauses: tuple[tuple[int, ...], ...], assignment: Mapping[int, bool]
) -> bool:
    """Check if all clauses in a CNF formula are satisfied."""
    return all(is_clause_satisfied(c, assignment) for c in clauses)


# ---------------------------------------------------------------------------
# PrimaryVarMap
# ---------------------------------------------------------------------------

class TestPrimaryVarMap:
    def test_row_major_order_2x2(self) -> None:
        pmap = PrimaryVarMap(2)
        assert pmap.grid_size == 2
        assert pmap.num_primary == 4
        # Row 1: A1=col1, B1=col2
        assert pmap.cell_to_var(CellId("A1")) == 1
        assert pmap.cell_to_var(CellId("B1")) == 2
        # Row 2: A2=col1, B2=col2
        assert pmap.cell_to_var(CellId("A2")) == 3
        assert pmap.cell_to_var(CellId("B2")) == 4

    def test_roundtrip_all_cells_3x3(self) -> None:
        pmap = PrimaryVarMap(3)
        assert pmap.num_primary == 9
        for idx in range(9):
            var = idx + 1
            cell = pmap.var_to_cell(var)
            assert pmap.cell_to_var(cell) == var

    def test_roundtrip_all_cells_4x4(self) -> None:
        pmap = PrimaryVarMap(4)
        assert pmap.num_primary == 16
        for idx in range(16):
            var = idx + 1
            cell = pmap.var_to_cell(var)
            assert pmap.cell_to_var(cell) == var

    def test_primary_vars_in_range(self) -> None:
        pmap = PrimaryVarMap(3)
        for idx in range(9):
            cell = CellId.from_index(idx, 3)
            var = pmap.cell_to_var(cell)
            assert 1 <= var <= pmap.num_primary

    def test_bounds_errors(self) -> None:
        pmap = PrimaryVarMap(3)
        with pytest.raises(ValueError, match="out of range"):
            pmap.var_to_cell(0)
        with pytest.raises(ValueError, match="out of range"):
            pmap.var_to_cell(10)
        with pytest.raises(ValueError, match="not valid"):
            pmap.cell_to_var(CellId("D1"))

    def test_invalid_grid_size(self) -> None:
        with pytest.raises(ValueError, match="grid_size must be >= 1"):
            PrimaryVarMap(0)

    def test_equality(self) -> None:
        assert PrimaryVarMap(3) == PrimaryVarMap(3)
        assert PrimaryVarMap(3) != PrimaryVarMap(4)
        assert PrimaryVarMap(3) != "not a map"


# ---------------------------------------------------------------------------
# AuxAllocator
# ---------------------------------------------------------------------------

class TestAuxAllocator:
    def test_starts_strictly_above_primary(self) -> None:
        pmap = PrimaryVarMap(3)  # num_primary = 9
        aux = AuxAllocator(pmap)
        assert aux.num_aux == 0
        v1 = aux.fresh()
        assert v1 == 10
        assert aux.num_aux == 1
        v2 = aux.fresh()
        assert v2 == 11
        assert aux.num_aux == 2

    def test_no_overlap_with_primary(self) -> None:
        pmap = PrimaryVarMap(2)  # primary: 1..4
        aux = AuxAllocator(pmap)
        generated = {aux.fresh() for _ in range(5)}
        primary = set(range(1, pmap.num_primary + 1))
        assert generated.isdisjoint(primary)

    def test_all_fresh_values_unique(self) -> None:
        aux = AuxAllocator(4)
        vals = [aux.fresh() for _ in range(100)]
        assert len(vals) == len(set(vals))

    def test_direct_integer_base(self) -> None:
        aux = AuxAllocator(16)
        assert aux.num_aux == 0
        assert aux.fresh() == 17
        assert aux.num_aux == 1

    def test_invalid_initialization(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            AuxAllocator(-1)
        with pytest.raises(TypeError, match="must be int or PrimaryVarMap"):
            AuxAllocator("invalid")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CNFFormula
# ---------------------------------------------------------------------------

class TestCNFFormula:
    def test_properties_and_counts(self) -> None:
        pmap = PrimaryVarMap(2)
        clauses = ((1, -2), (3,))
        formula = CNFFormula(clauses=clauses, primary_map=pmap, num_aux=2)
        assert formula.num_primary == 4
        assert formula.num_aux == 2
        assert formula.num_vars == 6
        assert formula.num_clauses == 2
        assert formula.clauses == ((1, -2), (3,))

    def test_rejects_zero_literal(self) -> None:
        pmap = PrimaryVarMap(2)
        with pytest.raises(ValueError, match="Clause cannot contain literal 0"):
            CNFFormula(clauses=((1, 0),), primary_map=pmap)

    def test_rejects_boolean_literals(self) -> None:
        """CNFFormula must reject booleans (True/False) as literals."""
        pmap = PrimaryVarMap(2)
        with pytest.raises(TypeError, match="Literal must be an integer"):
            CNFFormula(clauses=((True,),), primary_map=pmap)
        with pytest.raises(TypeError, match="Literal must be an integer"):
            CNFFormula(clauses=((False,),), primary_map=pmap)
        with pytest.raises(TypeError, match="Literal must be an integer"):
            CNFFormula(clauses=((1, True),), primary_map=pmap)

    def test_rejects_non_integer_literals(self) -> None:
        """CNFFormula must reject floats, strings, or other non-integers."""
        pmap = PrimaryVarMap(2)
        with pytest.raises(TypeError, match="Literal must be an integer"):
            CNFFormula(clauses=((1.9,),), primary_map=pmap)
        with pytest.raises(TypeError, match="Literal must be an integer"):
            CNFFormula(clauses=(("1",),), primary_map=pmap)

    def test_rejects_literal_exceeding_num_vars(self) -> None:
        """CNFFormula must reject variable IDs outside the declared range."""
        pmap = PrimaryVarMap(2)  # 4 primary vars
        # Without aux vars, max valid var ID is 4
        with pytest.raises(ValueError, match="exceeds declared total variables"):
            CNFFormula(clauses=((5,),), primary_map=pmap, num_aux=0)
        with pytest.raises(ValueError, match="exceeds declared total variables"):
            CNFFormula(clauses=((-5,),), primary_map=pmap, num_aux=0)

        # With 2 aux vars, total is 6; 5 and 6 are allowed, 7 is rejected
        f = CNFFormula(clauses=((5,), (-6,)), primary_map=pmap, num_aux=2)
        assert f.num_vars == 6
        with pytest.raises(ValueError, match="exceeds declared total variables"):
            CNFFormula(clauses=((7,),), primary_map=pmap, num_aux=2)

    def test_rejects_non_integer_num_aux(self) -> None:
        """num_aux must be an integer, rejecting booleans and floats."""
        pmap = PrimaryVarMap(2)
        with pytest.raises(TypeError, match="num_aux must be an integer"):
            CNFFormula(clauses=((1,),), primary_map=pmap, num_aux=True)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="num_aux must be an integer"):
            CNFFormula(clauses=((1,),), primary_map=pmap, num_aux=1.5)  # type: ignore[arg-type]

    def test_rejects_negative_num_aux(self) -> None:
        pmap = PrimaryVarMap(2)
        with pytest.raises(ValueError, match="num_aux cannot be negative"):
            CNFFormula(clauses=((1,),), primary_map=pmap, num_aux=-1)

    def test_empty_clauses(self) -> None:
        pmap = PrimaryVarMap(2)
        formula = CNFFormula(clauses=(), primary_map=pmap, num_aux=0)
        assert formula.num_clauses == 0
        assert formula.num_vars == 4

    def test_immutability(self) -> None:
        pmap = PrimaryVarMap(2)
        formula = CNFFormula(clauses=((1,),), primary_map=pmap, num_aux=0)
        with pytest.raises((AttributeError, TypeError)):
            formula.num_aux = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Binary encoder exhaustive tests (against independent semantics)
# ---------------------------------------------------------------------------

@pytest.fixture
def all_2x2_assignments() -> list[dict[CellId, Status]]:
    """All 16 binary assignments for a 2×2 grid in row-major order."""
    cells = [CellId("A1"), CellId("B1"), CellId("A2"), CellId("B2")]
    assignments = []
    for bits in range(16):
        asgn: dict[CellId, Status] = {}
        for i, cell in enumerate(cells):
            asgn[cell] = Status.CRIMINAL if ((bits >> i) & 1) else Status.INNOCENT
        assignments.append(asgn)
    return assignments


class TestEncoderSemanticsEquivalence:
    """Exhaustively verify CNF satisfaction matches independent semantics on all 2^4 assignments."""

    def _var_assignment(
        self, asgn: dict[CellId, Status], pmap: PrimaryVarMap
    ) -> dict[int, bool]:
        return {pmap.cell_to_var(c): (s == Status.CRIMINAL) for c, s in asgn.items()}

    def test_encode_fact_criminal_exhaustive(
        self, all_2x2_assignments: list[dict[CellId, Status]]
    ) -> None:
        pmap = PrimaryVarMap(2)
        for target in [CellId("A1"), CellId("B1"), CellId("A2"), CellId("B2")]:
            clue = FactClue("f1", owner=CellId("A1"), target=target, status=Status.CRIMINAL)
            clauses = encode_fact(clue, pmap)
            assert len(clauses) == 1
            assert len(clauses[0]) == 1
            for asgn in all_2x2_assignments:
                cnf_sat = is_cnf_satisfied(clauses, self._var_assignment(asgn, pmap))
                sem_sat = evaluate_fact(clue, asgn)
                assert cnf_sat == sem_sat, f"Mismatch for target={target}, asgn={asgn}"

    def test_encode_fact_innocent_exhaustive(
        self, all_2x2_assignments: list[dict[CellId, Status]]
    ) -> None:
        pmap = PrimaryVarMap(2)
        for target in [CellId("A1"), CellId("B1"), CellId("A2"), CellId("B2")]:
            clue = FactClue("f1", owner=CellId("A1"), target=target, status=Status.INNOCENT)
            clauses = encode_fact(clue, pmap)
            assert len(clauses) == 1
            assert len(clauses[0]) == 1
            for asgn in all_2x2_assignments:
                cnf_sat = is_cnf_satisfied(clauses, self._var_assignment(asgn, pmap))
                sem_sat = evaluate_fact(clue, asgn)
                assert cnf_sat == sem_sat

    def test_encode_same_exhaustive(
        self, all_2x2_assignments: list[dict[CellId, Status]]
    ) -> None:
        pmap = PrimaryVarMap(2)
        # Test all distinct pairs
        cells = [CellId("A1"), CellId("B1"), CellId("A2"), CellId("B2")]
        pairs = [(a, b) for i, a in enumerate(cells) for b in cells[i + 1:]]
        for pa, pb in pairs:
            clue = SameClue("s1", owner=pa, person_a=pa, person_b=pb)
            clauses = encode_same(clue, pmap)
            assert len(clauses) == 2
            va = pmap.cell_to_var(pa)
            vb = pmap.cell_to_var(pb)
            assert (-va, vb) in clauses
            assert (va, -vb) in clauses
            for asgn in all_2x2_assignments:
                cnf_sat = is_cnf_satisfied(clauses, self._var_assignment(asgn, pmap))
                sem_sat = evaluate_same(clue, asgn)
                assert cnf_sat == sem_sat

    def test_encode_different_exhaustive(
        self, all_2x2_assignments: list[dict[CellId, Status]]
    ) -> None:
        pmap = PrimaryVarMap(2)
        cells = [CellId("A1"), CellId("B1"), CellId("A2"), CellId("B2")]
        pairs = [(a, b) for i, a in enumerate(cells) for b in cells[i + 1:]]
        for pa, pb in pairs:
            clue = DifferentClue("d1", owner=pa, person_a=pa, person_b=pb)
            clauses = encode_different(clue, pmap)
            assert len(clauses) == 2
            va = pmap.cell_to_var(pa)
            vb = pmap.cell_to_var(pb)
            assert (va, vb) in clauses
            assert (-va, -vb) in clauses
            for asgn in all_2x2_assignments:
                cnf_sat = is_cnf_satisfied(clauses, self._var_assignment(asgn, pmap))
                sem_sat = evaluate_different(clue, asgn)
                assert cnf_sat == sem_sat


# ---------------------------------------------------------------------------
# encode_known_status
# ---------------------------------------------------------------------------

class TestEncodeKnownStatus:
    def test_criminal_produces_positive_unit(self) -> None:
        pmap = PrimaryVarMap(2)
        clauses = encode_known_status(CellId("A1"), Status.CRIMINAL, pmap)
        assert clauses == ((1,),)

    def test_innocent_produces_negative_unit(self) -> None:
        pmap = PrimaryVarMap(2)
        clauses = encode_known_status(CellId("A1"), Status.INNOCENT, pmap)
        assert clauses == ((-1,),)

    def test_b2_in_2x2(self) -> None:
        pmap = PrimaryVarMap(2)
        clauses = encode_known_status(CellId("B2"), Status.CRIMINAL, pmap)
        assert clauses == ((4,),)
        clauses2 = encode_known_status(CellId("B2"), Status.INNOCENT, pmap)
        assert clauses2 == ((-4,),)


# ---------------------------------------------------------------------------
# No zero or duplicate literals
# ---------------------------------------------------------------------------

class TestLiteralValidity:
    def test_no_zero_literals(self) -> None:
        pmap = PrimaryVarMap(2)
        for clauses in [
            encode_fact(FactClue("f", CellId("A1"), CellId("A1"), Status.CRIMINAL), pmap),
            encode_fact(FactClue("f", CellId("A1"), CellId("B1"), Status.INNOCENT), pmap),
            encode_same(SameClue("s", CellId("A1"), CellId("A1"), CellId("B1")), pmap),
            encode_different(DifferentClue("d", CellId("A1"), CellId("A1"), CellId("B1")), pmap),
        ]:
            for clause in clauses:
                assert 0 not in clause, f"Zero literal found in clause {clause}"

    def test_no_duplicate_literals(self) -> None:
        pmap = PrimaryVarMap(2)
        for clauses in [
            encode_same(SameClue("s", CellId("A1"), CellId("A1"), CellId("B1")), pmap),
            encode_different(DifferentClue("d", CellId("A1"), CellId("A1"), CellId("B1")), pmap),
        ]:
            for clause in clauses:
                assert len(clause) == len(set(clause)), f"Duplicate literal in clause {clause}"


# ---------------------------------------------------------------------------
# build_cnf_from_public_state
# ---------------------------------------------------------------------------

def _make_simple_state(
    grid_size: int,
    known_statuses: dict[CellId, Status],
    revealed_clues: tuple,
) -> PublicState:
    """Build a minimal valid PublicState for testing."""
    all_cells = [
        CellId.from_coords(r, c)
        for r in range(1, grid_size + 1)
        for c in range(1, grid_size + 1)
    ]
    # Names must be alphabetically sorted
    characters = [
        Character(cell=cell, name=f"Name_{chr(65 + i)}", profession="Worker")
        for i, cell in enumerate(sorted(all_cells))
    ]
    char_by_cell = {ch.cell: ch for ch in characters}

    clue_by_owner = {clue.owner: clue for clue in revealed_clues}
    cards = {}
    for cell in all_cells:
        is_rev = cell in known_statuses
        cards[cell] = PublicCard(
            cell=cell,
            character=char_by_cell[cell],
            is_revealed=is_rev,
            status=known_statuses.get(cell) if is_rev else None,
            clue=clue_by_owner.get(cell) if is_rev else None,
        )

    return PublicState(
        grid_size=grid_size,
        characters=tuple(characters),
        cards=cards,
        known_statuses=known_statuses,
        revealed_clues=tuple(sorted(revealed_clues, key=lambda c: c.owner)),
        revealed_cells=frozenset(known_statuses.keys()),
        revision=0,
    )


class TestBuildCNFFromPublicState:
    def test_empty_state_produces_no_clauses(self) -> None:
        state = _make_simple_state(2, {}, ())
        cnf = build_cnf_from_public_state(state)
        assert cnf.num_clauses == 0
        assert cnf.num_primary == 4
        assert cnf.num_aux == 0

    def test_known_status_only(self) -> None:
        # A revealed card requires a clue; use a FACT clue that is a no-op target
        # but keep known_statuses to test the unit-clause path separately from clue encoding.
        # We supply a FACT clue whose encoding will add one additional unit clause.
        # The test below uses build_cnf_from_public_state directly with a hand-crafted state
        # that has a known status whose clue is part of the revealed set.
        f_clue = FactClue("f1", CellId("A1"), CellId("A1"), Status.INNOCENT)
        state = _make_simple_state(2, {CellId("A1"): Status.INNOCENT}, (f_clue,))
        cnf = build_cnf_from_public_state(state)
        # 1 unit for A1 known INNOCENT + 1 unit from FACT(A1, INNOCENT)
        assert cnf.num_clauses == 2
        assert (-1,) in cnf.clauses
        assert cnf.num_aux == 0

    def test_known_status_unit_clause_directly(self) -> None:
        """encode_known_status is tested directly — not via build_cnf — for the no-clue path."""
        pmap = PrimaryVarMap(2)
        clauses = encode_known_status(CellId("A1"), Status.INNOCENT, pmap)
        assert clauses == ((-1,),)

    def test_fact_clue_plus_known_status(self) -> None:
        f_clue = FactClue("f1", CellId("A1"), CellId("B1"), Status.CRIMINAL)
        state = _make_simple_state(
            2,
            {CellId("A1"): Status.INNOCENT},
            (f_clue,),
        )
        cnf = build_cnf_from_public_state(state)
        # 1 unit for A1 INNOCENT + 1 unit for B1 CRIMINAL
        assert cnf.num_clauses == 2
        assert cnf.num_primary == 4
        assert cnf.num_aux == 0
        assert (-1,) in cnf.clauses   # A1 innocent
        assert (2,) in cnf.clauses    # B1 criminal

    def test_same_clue_produces_two_clauses(self) -> None:
        s_clue = SameClue("s1", CellId("A1"), CellId("A1"), CellId("B1"))
        state = _make_simple_state(2, {CellId("A1"): Status.CRIMINAL}, (s_clue,))
        cnf = build_cnf_from_public_state(state)
        # 1 known status unit + 2 SAME clauses
        assert cnf.num_clauses == 3
        assert (1,) in cnf.clauses
        assert cnf.num_aux == 0

    def test_different_clue_produces_two_clauses(self) -> None:
        d_clue = DifferentClue("d1", CellId("A1"), CellId("A1"), CellId("B1"))
        state = _make_simple_state(2, {CellId("A1"): Status.INNOCENT}, (d_clue,))
        cnf = build_cnf_from_public_state(state)
        assert cnf.num_clauses == 3  # 1 known + 2 diff
        assert cnf.num_aux == 0

    def test_encodes_exactly_clue(self) -> None:
        """T07: ExactlyClue is now encoded — verify it succeeds and produces auxiliaries."""
        clue = ExactlyClue("e1", CellId("A1"), k=1, region=RowRegion(1))
        all_cells = [CellId.from_coords(r, c) for r in (1, 2) for c in (1, 2)]
        characters = [
            Character(cell=cell, name=f"Name_{chr(65 + i)}", profession="Job")
            for i, cell in enumerate(sorted(all_cells))
        ]
        char_by_cell = {ch.cell: ch for ch in characters}
        cards = {
            cell: PublicCard(
                cell=cell,
                character=char_by_cell[cell],
                is_revealed=(cell == CellId("A1")),
                status=Status.CRIMINAL if cell == CellId("A1") else None,
                clue=clue if cell == CellId("A1") else None,
            )
            for cell in all_cells
        }
        state = PublicState(
            grid_size=2,
            characters=tuple(characters),
            cards=cards,
            known_statuses={CellId("A1"): Status.CRIMINAL},
            revealed_clues=(clue,),
            revealed_cells=frozenset({CellId("A1")}),
            revision=0,
        )
        cnf = build_cnf_from_public_state(state)
        assert cnf.num_primary == 4
        assert cnf.num_aux > 0  # Sequential counter uses auxiliaries

    def test_encodes_at_least_clue(self) -> None:
        """T07: AtLeastClue is now encoded — verify it succeeds and produces auxiliaries."""
        clue = AtLeastClue("al1", CellId("A1"), k=1, region=RowRegion(1))
        all_cells = [CellId.from_coords(r, c) for r in (1, 2) for c in (1, 2)]
        characters = [
            Character(cell=cell, name=f"Name_{chr(65 + i)}", profession="Job")
            for i, cell in enumerate(sorted(all_cells))
        ]
        char_by_cell = {ch.cell: ch for ch in characters}
        cards = {
            cell: PublicCard(
                cell=cell,
                character=char_by_cell[cell],
                is_revealed=(cell == CellId("A1")),
                status=Status.CRIMINAL if cell == CellId("A1") else None,
                clue=clue if cell == CellId("A1") else None,
            )
            for cell in all_cells
        }
        state = PublicState(
            grid_size=2,
            characters=tuple(characters),
            cards=cards,
            known_statuses={CellId("A1"): Status.CRIMINAL},
            revealed_clues=(clue,),
            revealed_cells=frozenset({CellId("A1")}),
            revision=0,
        )
        cnf = build_cnf_from_public_state(state)
        assert cnf.num_primary == 4
        assert cnf.num_aux > 0  # Sequential counter uses auxiliaries

    def test_encodes_parity_clue(self) -> None:
        """T08: ParityClue is encoded — verify it succeeds and produces clauses."""
        clue = ParityClue("p1", CellId("A1"), parity=Parity.EVEN, region=RowRegion(1))
        all_cells = [CellId.from_coords(r, c) for r in (1, 2) for c in (1, 2)]
        characters = [
            Character(cell=cell, name=f"Name_{chr(65 + i)}", profession="Job")
            for i, cell in enumerate(sorted(all_cells))
        ]
        char_by_cell = {ch.cell: ch for ch in characters}
        cards = {
            cell: PublicCard(
                cell=cell,
                character=char_by_cell[cell],
                is_revealed=(cell == CellId("A1")),
                status=Status.CRIMINAL if cell == CellId("A1") else None,
                clue=clue if cell == CellId("A1") else None,
            )
            for cell in all_cells
        }
        state = PublicState(
            grid_size=2,
            characters=tuple(characters),
            cards=cards,
            known_statuses={CellId("A1"): Status.CRIMINAL},
            revealed_clues=(clue,),
            revealed_cells=frozenset({CellId("A1")}),
            revision=0,
        )
        cnf = build_cnf_from_public_state(state)
        assert cnf.num_primary == 4
        assert cnf.num_aux == 1  # n=2, n-1=1 aux
        assert cnf.num_clauses == 6  # 1 status + 5 parity


# ---------------------------------------------------------------------------
# Architecture isolation check
# ---------------------------------------------------------------------------

class TestArchitectureIsolation:
    def test_cnf_does_not_import_forbidden_modules(self) -> None:
        """cnf.py must not import engine, semantics, dpll, logic, controller, gui, or validation."""
        cnf_path = (
            Path(__file__).resolve().parent.parent / "src" / "griductive" / "solver" / "cnf.py"
        )
        tree = ast.parse(cnf_path.read_text(encoding="utf-8"))
        forbidden = {
            "engine", "semantics", "dpll", "logic",
            "controller", "gui", "validation",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(f in alias.name for f in forbidden), (
                        f"Forbidden import in cnf.py: {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert not any(f in node.module for f in forbidden), (
                        f"Forbidden 'from' import in cnf.py: {node.module}"
                    )

    def test_aux_primary_ranges_are_disjoint(self) -> None:
        """Auxiliary variable integers must not overlap with any primary variable integer."""
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        primary_range = set(range(1, pmap.num_primary + 1))
        for _ in range(20):
            v = aux.fresh()
            assert v not in primary_range, f"Auxiliary var {v} overlaps with primary range"
