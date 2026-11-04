"""Comprehensive unit tests for PARITY and COMMON_NEIGHBORS clue encoding (T08).

Tests Tseitin XOR chain PARITY encoding, COMMON_NEIGHBORS region integration,
auxiliary variable count, clause count, exhaustive semantic equivalence across
all assignments, variable separation, and architectural isolation.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Mapping, Sequence

import pytest

from griductive.solver.cnf import (
    AuxAllocator,
    CNFFormula,
    PrimaryVarMap,
    build_cnf_from_public_state,
    encode_at_most,
    encode_parity,
)
from griductive.domain.model import (
    AtMostClue,
    CellId,
    Character,
    ColRegion,
    CommonNeighborsRegion,
    ExplicitRegion,
    NeighborsRegion,
    Parity,
    ParityClue,
    PublicCard,
    PublicState,
    RowRegion,
    Status,
)
from griductive.domain.regions import resolve_region
from griductive.domain.semantics import evaluate_cardinality, evaluate_parity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def cnf_sat_exists_aux(
    clauses: tuple[tuple[int, ...], ...],
    primary_assignment: Mapping[int, bool],
    num_primary: int,
    num_aux: int,
) -> bool:
    """Return True if there exists an auxiliary assignment satisfying all clauses.

    Simplifies clauses under the primary assignment, then uses backtracking
    search over the auxiliary variables that appear in still-unsatisfied clauses.
    """
    if not clauses:
        return True

    reduced: list[tuple[int, ...]] = []
    for clause in clauses:
        clause_sat = False
        aux_lits: list[int] = []
        for lit in clause:
            var = abs(lit)
            if var in primary_assignment:
                val = primary_assignment[var]
                if (lit > 0 and val) or (lit < 0 and not val):
                    clause_sat = True
                    break
            else:
                aux_lits.append(lit)
        if clause_sat:
            continue
        if not aux_lits:
            return False  # Clause falsified by primary assignment alone
        reduced.append(tuple(aux_lits))

    if not reduced:
        return True  # All clauses satisfied by primary assignment alone

    aux_vars = sorted({abs(lit) for clause in reduced for lit in clause})

    def solve(idx: int, current: dict[int, bool]) -> bool:
        for cl in reduced:
            all_assigned = all(abs(lit) in current for lit in cl)
            if all_assigned:
                sat = any(
                    (lit > 0 and current[abs(lit)]) or (lit < 0 and not current[abs(lit)])
                    for lit in cl
                )
                if not sat:
                    return False

        if idx == len(aux_vars):
            return True

        var = aux_vars[idx]
        for val in (False, True):
            current[var] = val
            if solve(idx + 1, current):
                del current[var]
                return True
            del current[var]
        return False

    return solve(0, {})


def make_all_assignments(cells: Sequence[CellId]) -> list[dict[CellId, Status]]:
    """Generate all 2^len(cells) truth assignments for a sequence of cells."""
    assignments: list[dict[CellId, Status]] = []
    for bits in range(1 << len(cells)):
        asgn: dict[CellId, Status] = {}
        for idx, cell in enumerate(cells):
            asgn[cell] = Status.CRIMINAL if ((bits >> idx) & 1) else Status.INNOCENT
        assignments.append(asgn)
    return assignments


def complete_assignment(
    partial: Mapping[CellId, Status],
    grid_size: int,
    default: Status = Status.INNOCENT,
) -> dict[CellId, Status]:
    """Expand a partial assignment to cover every cell in the grid."""
    full: dict[CellId, Status] = {}
    for r in range(1, grid_size + 1):
        for c in range(1, grid_size + 1):
            cell = CellId.from_coords(r, c)
            full[cell] = partial.get(cell, default)
    return full


def to_primary_assignment(
    assignment: Mapping[CellId, Status],
    pmap: PrimaryVarMap,
) -> dict[int, bool]:
    """Convert CellId->Status map to primary var integer->bool map."""
    return {
        pmap.cell_to_var(cell): (status == Status.CRIMINAL)
        for cell, status in assignment.items()
    }


def make_test_public_state(
    grid_size: int,
    revealed_clues: Sequence,
    known_statuses: Mapping[CellId, Status] | None = None,
) -> PublicState:
    """Build a minimal valid PublicState for integration tests."""
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
        revision=0,
    )


# ---------------------------------------------------------------------------
# 1. Empty region (n = 0)
# ---------------------------------------------------------------------------


class TestEmptyRegion:
    def test_empty_region_even_parity_produces_zero_clauses_and_zero_aux(self) -> None:
        """PARITY(empty, EVEN) is a tautology (0 % 2 == 0): 0 clauses, 0 aux."""
        grid_size = 4
        pmap = PrimaryVarMap(grid_size)
        aux = AuxAllocator(pmap)
        # On 4x4, A1 (top-left) and D4 (bottom-right) have disjoint 8-neighbor sets
        region = CommonNeighborsRegion(CellId("A1"), CellId("D4"))
        assert len(resolve_region(region, grid_size)) == 0

        clue = ParityClue("p_even", CellId("A1"), parity=Parity.EVEN, region=region)
        clauses = encode_parity(clue, pmap, aux, grid_size)

        assert len(clauses) == 0
        assert aux.num_aux == 0

    def test_empty_region_odd_parity_produces_empty_clause_and_zero_aux(self) -> None:
        """PARITY(empty, ODD) is UNSAT (0 % 2 == 1 is false): 1 empty clause (), 0 aux."""
        grid_size = 4
        pmap = PrimaryVarMap(grid_size)
        aux = AuxAllocator(pmap)
        region = CommonNeighborsRegion(CellId("A1"), CellId("D4"))
        assert len(resolve_region(region, grid_size)) == 0

        clue = ParityClue("p_odd", CellId("A1"), parity=Parity.ODD, region=region)
        clauses = encode_parity(clue, pmap, aux, grid_size)

        assert len(clauses) == 1
        assert clauses[0] == ()
        assert aux.num_aux == 0

    def test_empty_region_semantics_match(self) -> None:
        """Both EVEN and ODD match evaluate_parity on empty regions."""
        grid_size = 4
        pmap = PrimaryVarMap(grid_size)
        region = CommonNeighborsRegion(CellId("A1"), CellId("D4"))

        clue_even = ParityClue("pe", CellId("A1"), Parity.EVEN, region)
        clue_odd = ParityClue("po", CellId("A1"), Parity.ODD, region)

        aux_e = AuxAllocator(pmap)
        clauses_even = encode_parity(clue_even, pmap, aux_e, grid_size)

        aux_o = AuxAllocator(pmap)
        clauses_odd = encode_parity(clue_odd, pmap, aux_o, grid_size)

        for default_status in (Status.INNOCENT, Status.CRIMINAL):
            full = complete_assignment({}, grid_size, default=default_status)
            prim = to_primary_assignment(full, pmap)

            cnf_sat_e = cnf_sat_exists_aux(clauses_even, prim, pmap.num_primary, aux_e.num_aux)
            sem_e = evaluate_parity(clue_even, full, grid_size)
            assert cnf_sat_e is True
            assert sem_e is True
            assert cnf_sat_e == sem_e

            cnf_sat_o = cnf_sat_exists_aux(clauses_odd, prim, pmap.num_primary, aux_o.num_aux)
            sem_o = evaluate_parity(clue_odd, full, grid_size)
            assert cnf_sat_o is False
            assert sem_o is False
            assert cnf_sat_o == sem_o


# ---------------------------------------------------------------------------
# 2. Single cell (n = 1)
# ---------------------------------------------------------------------------


class TestSingleCell:
    def test_single_cell_even_unit_clause_and_zero_aux(self) -> None:
        """n=1, EVEN forces innocent: 1 negative unit clause, 0 aux."""
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        aux = AuxAllocator(pmap)
        target = CellId("A1")
        region = ExplicitRegion((target,))
        var_a1 = pmap.cell_to_var(target)

        clue = ParityClue("p1_even", CellId("A1"), Parity.EVEN, region)
        clauses = encode_parity(clue, pmap, aux, grid_size)

        assert aux.num_aux == 0
        assert len(clauses) == 1
        assert clauses[0] == (-var_a1,)

    def test_single_cell_odd_unit_clause_and_zero_aux(self) -> None:
        """n=1, ODD forces criminal: 1 positive unit clause, 0 aux."""
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        aux = AuxAllocator(pmap)
        target = CellId("B2")
        region = ExplicitRegion((target,))
        var_b2 = pmap.cell_to_var(target)

        clue = ParityClue("p1_odd", CellId("B2"), Parity.ODD, region)
        clauses = encode_parity(clue, pmap, aux, grid_size)

        assert aux.num_aux == 0
        assert len(clauses) == 1
        assert clauses[0] == (var_b2,)

    def test_single_cell_exhaustive_semantics_match(self) -> None:
        grid_size = 2
        pmap = PrimaryVarMap(grid_size)
        cells = [CellId("A1")]
        region = ExplicitRegion(tuple(cells))
        all_assignments = make_all_assignments(cells)

        for parity in (Parity.EVEN, Parity.ODD):
            clue = ParityClue(f"p_{parity}", CellId("A1"), parity, region)
            aux = AuxAllocator(pmap)
            clauses = encode_parity(clue, pmap, aux, grid_size)

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_parity(clue, full, grid_size)
                assert cnf_sat == sem_sat

    def test_single_cell_via_common_neighbors_3x3(self) -> None:
        """On 3x3, opposite corners A1 and C3 have exactly 1 common neighbor (B2)."""
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        region = CommonNeighborsRegion(CellId("A1"), CellId("C3"))
        resolved = resolve_region(region, grid_size)
        assert resolved == (CellId("B2"),)

        aux = AuxAllocator(pmap)
        clue = ParityClue("p_cn1", CellId("A1"), Parity.EVEN, region)
        clauses = encode_parity(clue, pmap, aux, grid_size)
        assert aux.num_aux == 0
        assert len(clauses) == 1
        assert clauses[0] == (-pmap.cell_to_var(CellId("B2")),)


# ---------------------------------------------------------------------------
# 3. Auxiliary variable count for n >= 2
# ---------------------------------------------------------------------------


class TestAuxiliaryCount:
    def test_parity_allocates_exact_n_minus_1_aux(self) -> None:
        """Tseitin XOR chain on n cells uses exactly n - 1 auxiliaries."""
        grid_size = 4
        pmap = PrimaryVarMap(grid_size)
        for n in (2, 3, 4, 5):
            cells = tuple(CellId.from_index(i, grid_size) for i in range(n))
            region = ExplicitRegion(cells)
            for parity in (Parity.EVEN, Parity.ODD):
                aux = AuxAllocator(pmap)
                clue = ParityClue(f"p_{n}_{parity}", CellId("A1"), parity, region)
                encode_parity(clue, pmap, aux, grid_size)
                assert aux.num_aux == n - 1, (
                    f"Expected {n - 1} aux for n={n}, got {aux.num_aux}"
                )


# ---------------------------------------------------------------------------
# 4. Clause count sanity for n >= 2
# ---------------------------------------------------------------------------


class TestClauseCount:
    def test_parity_clause_count_formula_4n_minus_3(self) -> None:
        """Tseitin XOR chain produces 4*(n-1) gate clauses + 1 parity unit = 4n - 3 clauses."""
        grid_size = 4
        pmap = PrimaryVarMap(grid_size)
        for n in (2, 3, 4, 5):
            cells = tuple(CellId.from_index(i, grid_size) for i in range(n))
            region = ExplicitRegion(cells)
            for parity in (Parity.EVEN, Parity.ODD):
                aux = AuxAllocator(pmap)
                clue = ParityClue(f"p_{n}_{parity}", CellId("A1"), parity, region)
                clauses = encode_parity(clue, pmap, aux, grid_size)
                expected = 4 * (n - 1) + 1
                assert len(clauses) == expected, (
                    f"Expected {expected} clauses for n={n}, got {len(clauses)}"
                )

    def test_clause_counts_even_vs_odd_are_identical(self) -> None:
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        region = RowRegion(1)  # n = 3
        clue_e = ParityClue("pe", CellId("A1"), Parity.EVEN, region)
        clue_o = ParityClue("po", CellId("A1"), Parity.ODD, region)

        aux_e = AuxAllocator(pmap)
        cl_e = encode_parity(clue_e, pmap, aux_e, grid_size)

        aux_o = AuxAllocator(pmap)
        cl_o = encode_parity(clue_o, pmap, aux_o, grid_size)

        assert len(cl_e) == len(cl_o) == 9  # 4*(3-1) + 1 = 9

    def test_clause_generation_is_deterministic(self) -> None:
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        region = RowRegion(1)
        clue = ParityClue("p", CellId("A1"), Parity.EVEN, region)

        aux1 = AuxAllocator(pmap)
        c1 = encode_parity(clue, pmap, aux1, grid_size)

        aux2 = AuxAllocator(pmap)
        c2 = encode_parity(clue, pmap, aux2, grid_size)

        assert c1 == c2


# ---------------------------------------------------------------------------
# 5. Exhaustive semantics equivalence
# ---------------------------------------------------------------------------


class TestSemanticsEquivalence:
    def test_parity_2_cells_exhaustive(self) -> None:
        """All 2^2 truth assignments match evaluate_parity for both EVEN and ODD."""
        grid_size = 2
        pmap = PrimaryVarMap(grid_size)
        cells = [CellId("A1"), CellId("B1")]
        region = ExplicitRegion(tuple(cells))
        all_assignments = make_all_assignments(cells)

        for parity in (Parity.EVEN, Parity.ODD):
            clue = ParityClue(f"p2_{parity}", CellId("A1"), parity, region)
            aux = AuxAllocator(pmap)
            clauses = encode_parity(clue, pmap, aux, grid_size)

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_parity(clue, full, grid_size)
                assert cnf_sat == sem_sat, (
                    f"Mismatch on {partial} for {parity}: cnf={cnf_sat}, sem={sem_sat}"
                )

    def test_parity_3_cells_exhaustive(self) -> None:
        """All 2^3 truth assignments match evaluate_parity for both EVEN and ODD."""
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        cells = [CellId("A1"), CellId("B1"), CellId("C1")]
        region = ExplicitRegion(tuple(cells))
        all_assignments = make_all_assignments(cells)

        for parity in (Parity.EVEN, Parity.ODD):
            clue = ParityClue(f"p3_{parity}", CellId("A1"), parity, region)
            aux = AuxAllocator(pmap)
            clauses = encode_parity(clue, pmap, aux, grid_size)

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_parity(clue, full, grid_size)
                assert cnf_sat == sem_sat, (
                    f"Mismatch on {partial} for {parity}: cnf={cnf_sat}, sem={sem_sat}"
                )

    def test_parity_4_cells_exhaustive(self) -> None:
        """All 2^4 truth assignments match evaluate_parity for both EVEN and ODD."""
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        cells = [CellId("A1"), CellId("B1"), CellId("A2"), CellId("B2")]
        region = ExplicitRegion(tuple(cells))
        all_assignments = make_all_assignments(cells)

        for parity in (Parity.EVEN, Parity.ODD):
            clue = ParityClue(f"p4_{parity}", CellId("A1"), parity, region)
            aux = AuxAllocator(pmap)
            clauses = encode_parity(clue, pmap, aux, grid_size)

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_parity(clue, full, grid_size)
                assert cnf_sat == sem_sat, (
                    f"Mismatch on {partial} for {parity}: cnf={cnf_sat}, sem={sem_sat}"
                )

    def test_parity_row_region_exhaustive(self) -> None:
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        region = RowRegion(2)  # A2, B2, C2
        cells = list(resolve_region(region, grid_size))
        all_assignments = make_all_assignments(cells)

        for parity in (Parity.EVEN, Parity.ODD):
            clue = ParityClue(f"row_{parity}", CellId("A2"), parity, region)
            aux = AuxAllocator(pmap)
            clauses = encode_parity(clue, pmap, aux, grid_size)

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_parity(clue, full, grid_size)
                assert cnf_sat == sem_sat

    def test_parity_col_region_exhaustive(self) -> None:
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        region = ColRegion("B")  # B1, B2, B3
        cells = list(resolve_region(region, grid_size))
        all_assignments = make_all_assignments(cells)

        for parity in (Parity.EVEN, Parity.ODD):
            clue = ParityClue(f"col_{parity}", CellId("B1"), parity, region)
            aux = AuxAllocator(pmap)
            clauses = encode_parity(clue, pmap, aux, grid_size)

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_parity(clue, full, grid_size)
                assert cnf_sat == sem_sat

    def test_parity_neighbors_region_exhaustive(self) -> None:
        """Corner cell A1 has 3 neighbors: B1, A2, B2."""
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        region = NeighborsRegion(CellId("A1"))
        cells = list(resolve_region(region, grid_size))
        assert len(cells) == 3
        all_assignments = make_all_assignments(cells)

        for parity in (Parity.EVEN, Parity.ODD):
            clue = ParityClue(f"nbr_{parity}", CellId("A1"), parity, region)
            aux = AuxAllocator(pmap)
            clauses = encode_parity(clue, pmap, aux, grid_size)

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_parity(clue, full, grid_size)
                assert cnf_sat == sem_sat


# ---------------------------------------------------------------------------
# 6. COMMON_NEIGHBORS region integration
# ---------------------------------------------------------------------------


class TestCommonNeighborsRegion:
    def test_common_neighbors_with_at_most_empty_intersection(self) -> None:
        """On 4x4, A1 and D4 have 0 common neighbors -> AT_MOST(0) produces 0 clauses."""
        grid_size = 4
        pmap = PrimaryVarMap(grid_size)
        aux = AuxAllocator(pmap)
        region = CommonNeighborsRegion(CellId("A1"), CellId("D4"))
        assert len(resolve_region(region, grid_size)) == 0

        clue = AtMostClue("am_cn_empty", CellId("A1"), k=0, region=region)
        clauses = encode_at_most(clue, pmap, aux, grid_size)
        assert len(clauses) == 0
        assert aux.num_aux == 0

    def test_common_neighbors_with_at_most_non_empty(self) -> None:
        """On 3x3, A1 and C1 share 2 common neighbors (B1, B2)."""
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        aux = AuxAllocator(pmap)
        region = CommonNeighborsRegion(CellId("A1"), CellId("C1"))
        common = resolve_region(region, grid_size)
        assert common == (CellId("B1"), CellId("B2"))

        clue = AtMostClue("am_cn", CellId("A1"), k=1, region=region)
        clauses = encode_at_most(clue, pmap, aux, grid_size)
        assert aux.num_aux == 2
        assert len(clauses) == 4

        all_assignments = make_all_assignments(list(common))
        for partial in all_assignments:
            full = complete_assignment(partial, grid_size)
            prim = to_primary_assignment(full, pmap)
            cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
            sem_sat = evaluate_cardinality(clue, full, grid_size)
            assert cnf_sat == sem_sat

    def test_common_neighbors_with_parity_size_2(self) -> None:
        """On 3x3, A1 and C1 share 2 common neighbors (B1, B2)."""
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        region = CommonNeighborsRegion(CellId("A1"), CellId("C1"))
        common = list(resolve_region(region, grid_size))
        all_assignments = make_all_assignments(common)

        for parity in (Parity.EVEN, Parity.ODD):
            aux = AuxAllocator(pmap)
            clue = ParityClue(f"p_cn_{parity}", CellId("A1"), parity, region)
            clauses = encode_parity(clue, pmap, aux, grid_size)

            assert aux.num_aux == 1  # n - 1 = 1
            assert len(clauses) == 5  # 4*(2-1) + 1 = 5

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_parity(clue, full, grid_size)
                assert cnf_sat == sem_sat

    def test_common_neighbors_with_parity_size_3(self) -> None:
        """On 4x4, B2 (row 2, col 2) and B4 (row 4, col 2) share A3, B3, C3 (size 3)."""
        grid_size = 4
        pmap = PrimaryVarMap(grid_size)
        region = CommonNeighborsRegion(CellId("B2"), CellId("B4"))
        common = list(resolve_region(region, grid_size))
        assert common == [CellId("A3"), CellId("B3"), CellId("C3")]
        all_assignments = make_all_assignments(common)

        for parity in (Parity.EVEN, Parity.ODD):
            aux = AuxAllocator(pmap)
            clue = ParityClue(f"p_cn3_{parity}", CellId("B2"), parity, region)
            clauses = encode_parity(clue, pmap, aux, grid_size)

            assert aux.num_aux == 2  # n - 1 = 2
            assert len(clauses) == 9  # 4*(3-1) + 1 = 9

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_parity(clue, full, grid_size)
                assert cnf_sat == sem_sat


# ---------------------------------------------------------------------------
# 7. Auxiliary variable separation across clues
# ---------------------------------------------------------------------------


class TestAuxiliaryVariableSeparation:
    def test_two_parity_clues_disjoint_aux_ranges(self) -> None:
        pmap = PrimaryVarMap(3)  # primary: 1..9
        aux = AuxAllocator(pmap)

        r1 = ExplicitRegion((CellId("A1"), CellId("B1"), CellId("C1")))
        clue1 = ParityClue("p1", CellId("A1"), Parity.EVEN, r1)  # 2 aux: 10..11
        clauses1 = encode_parity(clue1, pmap, aux, 3)
        assert aux.num_aux == 2

        r2 = ExplicitRegion((CellId("A2"), CellId("B2"), CellId("C2"), CellId("A3")))
        clue2 = ParityClue("p2", CellId("A2"), Parity.ODD, r2)  # 3 aux: 12..14
        clauses2 = encode_parity(clue2, pmap, aux, 3)
        assert aux.num_aux == 5

        aux1_vars = {abs(lit) for cl in clauses1 for lit in cl if abs(lit) > pmap.num_primary}
        aux2_vars = {abs(lit) for cl in clauses2 for lit in cl if abs(lit) > pmap.num_primary}

        assert aux1_vars == {10, 11}
        assert aux2_vars == {12, 13, 14}
        assert aux1_vars.isdisjoint(aux2_vars)

    def test_mixed_parity_and_cardinality_disjoint_aux_ranges(self) -> None:
        pmap = PrimaryVarMap(3)  # primary: 1..9
        aux = AuxAllocator(pmap)
        region = RowRegion(1)  # n = 3

        # AT_MOST(1, 3) -> 3*1 = 3 aux (10..12)
        encode_at_most(AtMostClue("c1", CellId("A1"), 1, region), pmap, aux, 3)
        assert aux.num_aux == 3

        # PARITY(EVEN, 3) -> 3 - 1 = 2 aux (13..14)
        encode_parity(ParityClue("c2", CellId("A2"), Parity.EVEN, region), pmap, aux, 3)
        assert aux.num_aux == 5

    def test_aux_vars_strictly_above_primary_range(self) -> None:
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        region = RowRegion(1)
        clue = ParityClue("p", CellId("A1"), Parity.EVEN, region)
        clauses = encode_parity(clue, pmap, aux, 3)

        for cl in clauses:
            for lit in cl:
                var = abs(lit)
                if var > pmap.num_primary:
                    assert var in (10, 11)


# ---------------------------------------------------------------------------
# 8. Literal validity
# ---------------------------------------------------------------------------


class TestLiteralValidity:
    def test_no_zero_literals(self) -> None:
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        region = RowRegion(1)

        for parity in (Parity.EVEN, Parity.ODD):
            clauses = encode_parity(ParityClue("p", CellId("A1"), parity, region), pmap, aux, 3)
            for cl in clauses:
                assert 0 not in cl

    def test_no_duplicate_literals_in_clause(self) -> None:
        pmap = PrimaryVarMap(3)
        region = RowRegion(1)

        for parity in (Parity.EVEN, Parity.ODD):
            aux = AuxAllocator(pmap)
            clauses = encode_parity(ParityClue("p", CellId("A1"), parity, region), pmap, aux, 3)
            for cl in clauses:
                assert len(cl) == len(set(cl)), f"Duplicate literal in {cl}"

    def test_all_literal_abs_values_within_declared_range(self) -> None:
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        region = RowRegion(1)
        clue = ParityClue("p", CellId("A1"), Parity.EVEN, region)
        clauses = encode_parity(clue, pmap, aux, 3)

        max_allowed = pmap.num_primary + aux.num_aux
        for cl in clauses:
            for lit in cl:
                assert 1 <= abs(lit) <= max_allowed


# ---------------------------------------------------------------------------
# 9. Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_invalid_parity_type_raises_type_error(self) -> None:
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        region = RowRegion(1)
        with pytest.raises(TypeError, match="must be a Parity enum"):
            encode_parity(
                ParityClue("p", CellId("A1"), parity="EVEN", region=region),  # type: ignore[arg-type]
                pmap,
                aux,
                3,
            )

    def test_invalid_grid_size_raises_value_error(self) -> None:
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        region = RowRegion(1)
        with pytest.raises(ValueError, match="grid_size must be >= 1"):
            encode_parity(
                ParityClue("p", CellId("A1"), Parity.EVEN, region),
                pmap,
                aux,
                grid_size=0,
            )

    def test_out_of_bounds_cell_raises_value_error(self) -> None:
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        region = RowRegion(5)  # row 5 out of bounds for 3x3
        with pytest.raises(ValueError, match="out of bounds"):
            encode_parity(
                ParityClue("p", CellId("A1"), Parity.EVEN, region),
                pmap,
                aux,
                grid_size=3,
            )


# ---------------------------------------------------------------------------
# 10. Architecture isolation check
# ---------------------------------------------------------------------------


class TestArchitectureIsolation:
    def test_cnf_does_not_import_forbidden_modules(self) -> None:
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
