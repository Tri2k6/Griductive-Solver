"""Comprehensive unit tests for cardinality clue encoding (T07).

Tests Sinz sequential counter AT_MOST, negated-literal AT_LEAST, and EXACTLY
encodings for auxiliary variable count, clause count, exhaustive semantic
equivalence, variable separation, and architectural isolation.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Mapping, Sequence

import pytest

from griductive.solver.cnf import (
    AuxAllocator,
    PrimaryVarMap,
    build_cnf_from_public_state,
    encode_at_least,
    encode_at_most,
    encode_exactly,
)
from griductive.domain.model import (
    AtLeastClue,
    AtMostClue,
    CellId,
    Character,
    ColRegion,
    ExactlyClue,
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
from griductive.domain.semantics import evaluate_cardinality


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
        # Early conflict detection
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
            return True  # No conflict found after full assignment

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
    """Convert CellId→Status map to primary var integer→bool map."""
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
    # Names sorted alphabetically to satisfy PublicState invariant
    characters = [
        Character(cell=cell, name=f"Person_{chr(65 + i)}", profession="Tester")
        for i, cell in enumerate(sorted(all_cells))
    ]
    char_by_cell = {ch.cell: ch for ch in characters}
    clue_by_owner = {clue.owner: clue for clue in revealed_clues}

    # Ensure every clue owner is in known_statuses (required by PublicCard invariant)
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
# 1. Sequential counter auxiliary count
# ---------------------------------------------------------------------------

class TestAuxiliaryCount:
    def test_at_most_interior_allocates_exact_n_times_k_aux(self) -> None:
        """Interior AT_MOST(k) on n cells uses exactly n*k auxiliaries."""
        pmap = PrimaryVarMap(4)
        for n in (2, 3, 4):
            cells = tuple(CellId.from_coords(1, c) for c in range(1, n + 1))
            region = ExplicitRegion(cells)
            for k in range(1, n):
                aux = AuxAllocator(pmap)
                clue = AtMostClue("c1", owner=CellId("A1"), k=k, region=region)
                encode_at_most(clue, pmap, aux, grid_size=4)
                assert aux.num_aux == n * k, (
                    f"Expected {n * k} aux for n={n}, k={k}, got {aux.num_aux}"
                )

    def test_at_most_boundary_zero_allocates_zero_aux(self) -> None:
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        clue = AtMostClue("c1", owner=CellId("A1"), k=0, region=RowRegion(1))
        encode_at_most(clue, pmap, aux, grid_size=3)
        assert aux.num_aux == 0

    def test_at_most_boundary_n_allocates_zero_aux(self) -> None:
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        clue = AtMostClue("c1", owner=CellId("A1"), k=3, region=RowRegion(1))
        encode_at_most(clue, pmap, aux, grid_size=3)
        assert aux.num_aux == 0

    def test_at_least_interior_allocates_exact_n_times_n_minus_k_aux(self) -> None:
        """Interior AT_LEAST(k) on n cells uses exactly n*(n-k) auxiliaries."""
        pmap = PrimaryVarMap(4)
        for n in (2, 3, 4):
            cells = tuple(CellId.from_coords(1, c) for c in range(1, n + 1))
            region = ExplicitRegion(cells)
            for k in range(1, n):
                aux = AuxAllocator(pmap)
                clue = AtLeastClue("c1", owner=CellId("A1"), k=k, region=region)
                encode_at_least(clue, pmap, aux, grid_size=4)
                assert aux.num_aux == n * (n - k)

    def test_at_least_boundary_zero_allocates_zero_aux(self) -> None:
        """AT_LEAST(0) = AT_MOST(n) on negated = tautology = 0 aux."""
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        clue = AtLeastClue("c1", owner=CellId("A1"), k=0, region=RowRegion(1))
        encode_at_least(clue, pmap, aux, grid_size=3)
        assert aux.num_aux == 0

    def test_at_least_boundary_n_allocates_zero_aux(self) -> None:
        """AT_LEAST(n) = AT_MOST(0) on negated = n unit clauses = 0 aux."""
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        clue = AtLeastClue("c1", owner=CellId("A1"), k=3, region=RowRegion(1))
        encode_at_least(clue, pmap, aux, grid_size=3)
        assert aux.num_aux == 0

    def test_exactly_interior_allocates_combined_aux(self) -> None:
        """EXACTLY(k, n=3) uses 3*k + 3*(3-k) = 9 auxiliaries."""
        pmap = PrimaryVarMap(3)
        region = RowRegion(1)  # n = 3
        for k in (1, 2):
            aux = AuxAllocator(pmap)
            clue = ExactlyClue("c1", owner=CellId("A1"), k=k, region=region)
            encode_exactly(clue, pmap, aux, grid_size=3)
            expected = 3 * k + 3 * (3 - k)
            assert aux.num_aux == expected

    def test_exactly_boundary_zero_allocates_zero_aux(self) -> None:
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        clue = ExactlyClue("c1", owner=CellId("A1"), k=0, region=RowRegion(1))
        encode_exactly(clue, pmap, aux, grid_size=3)
        assert aux.num_aux == 0

    def test_exactly_boundary_n_allocates_zero_aux(self) -> None:
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        clue = ExactlyClue("c1", owner=CellId("A1"), k=3, region=RowRegion(1))
        encode_exactly(clue, pmap, aux, grid_size=3)
        assert aux.num_aux == 0


# ---------------------------------------------------------------------------
# 2. Clause count sanity
# ---------------------------------------------------------------------------

class TestClauseCountSanity:
    def test_at_most_boundary_clause_counts(self) -> None:
        pmap = PrimaryVarMap(3)
        region = RowRegion(1)  # n = 3
        aux = AuxAllocator(pmap)

        # k=0: exactly n unit clauses, all negative
        clauses_0 = encode_at_most(AtMostClue("c1", CellId("A1"), 0, region), pmap, aux, 3)
        assert len(clauses_0) == 3
        for cl in clauses_0:
            assert len(cl) == 1
            assert cl[0] < 0

        # k=n: 0 clauses
        clauses_n = encode_at_most(AtMostClue("c2", CellId("A1"), 3, region), pmap, aux, 3)
        assert len(clauses_n) == 0

    def test_at_least_boundary_clause_counts(self) -> None:
        pmap = PrimaryVarMap(3)
        region = RowRegion(1)  # n = 3
        aux = AuxAllocator(pmap)

        # k=0: 0 clauses (tautology: AT_MOST(3) on negated = no constraint)
        clauses_0 = encode_at_least(AtLeastClue("c1", CellId("A1"), 0, region), pmap, aux, 3)
        assert len(clauses_0) == 0

        # k=n: exactly n unit clauses, all positive (all must be criminal)
        clauses_n = encode_at_least(AtLeastClue("c2", CellId("A1"), 3, region), pmap, aux, 3)
        assert len(clauses_n) == 3
        for cl in clauses_n:
            assert len(cl) == 1
            assert cl[0] > 0  # positive literal: criminal

    def test_at_most_interior_clause_count_formula(self) -> None:
        """Interior AT_MOST(k, n) produces 1 + (n-1)*(2k+1) clauses."""
        pmap = PrimaryVarMap(4)
        for n in (2, 3, 4):
            cells = tuple(CellId.from_coords(1, c) for c in range(1, n + 1))
            region = ExplicitRegion(cells)
            for k in range(1, n):
                aux = AuxAllocator(pmap)
                clue = AtMostClue("c", CellId("A1"), k, region)
                clauses = encode_at_most(clue, pmap, aux, 4)
                expected = 1 + (n - 1) * (2 * k + 1)
                assert len(clauses) == expected, (
                    f"n={n}, k={k}: expected {expected} clauses, got {len(clauses)}"
                )

    def test_exactly_boundary_clause_counts(self) -> None:
        pmap = PrimaryVarMap(3)
        region = RowRegion(1)  # n = 3
        aux = AuxAllocator(pmap)

        # EXACTLY(0): same as AT_MOST(0) — all innocent
        cl_0 = encode_exactly(ExactlyClue("c1", CellId("A1"), 0, region), pmap, aux, 3)
        assert len(cl_0) == 3
        for cl in cl_0:
            assert len(cl) == 1
            assert cl[0] < 0

        # EXACTLY(n): same as AT_LEAST(n) — all criminal
        cl_n = encode_exactly(ExactlyClue("c2", CellId("A1"), 3, region), pmap, aux, 3)
        assert len(cl_n) == 3
        for cl in cl_n:
            assert len(cl) == 1
            assert cl[0] > 0

    def test_clause_counts_deterministic_across_repeated_calls(self) -> None:
        pmap = PrimaryVarMap(3)
        region = RowRegion(1)
        clue = AtMostClue("c", CellId("A1"), 1, region)

        aux1 = AuxAllocator(pmap)
        c1 = encode_at_most(clue, pmap, aux1, 3)

        aux2 = AuxAllocator(pmap)
        c2 = encode_at_most(clue, pmap, aux2, 3)

        assert len(c1) == len(c2)
        assert c1 == c2


# ---------------------------------------------------------------------------
# 3. Exhaustive semantics equivalence — AT_MOST
# ---------------------------------------------------------------------------

class TestSemanticsEquivalenceAtMost:
    def test_at_most_3_cells_exhaustive(self) -> None:
        """All 2^3 × 4 (k=0..3) cases match evaluate_cardinality."""
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        cells = [CellId("A1"), CellId("B1"), CellId("C1")]
        region = ExplicitRegion(tuple(cells))
        all_assignments = make_all_assignments(cells)

        for k in range(len(cells) + 1):
            clue = AtMostClue(f"am_{k}", owner=CellId("A1"), k=k, region=region)
            aux = AuxAllocator(pmap)
            clauses = encode_at_most(clue, pmap, aux, grid_size)

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_cardinality(clue, full, grid_size)
                assert cnf_sat == sem_sat, (
                    f"AT_MOST({k}) mismatch: cnf={cnf_sat}, sem={sem_sat}, asgn={partial}"
                )

    def test_at_most_4_cells_exhaustive(self) -> None:
        """All 2^4 × 5 (k=0..4) cases match evaluate_cardinality."""
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        cells = [CellId("A1"), CellId("B1"), CellId("A2"), CellId("B2")]
        region = ExplicitRegion(tuple(cells))
        all_assignments = make_all_assignments(cells)

        for k in range(len(cells) + 1):
            clue = AtMostClue(f"am4_{k}", owner=CellId("A1"), k=k, region=region)
            aux = AuxAllocator(pmap)
            clauses = encode_at_most(clue, pmap, aux, grid_size)

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_cardinality(clue, full, grid_size)
                assert cnf_sat == sem_sat, (
                    f"AT_MOST({k}, 4 cells) mismatch on {partial}"
                )

    def test_at_most_row_region_exhaustive(self) -> None:
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        region = RowRegion(2)  # A2, B2, C2
        cells = list(resolve_region(region, grid_size))
        all_assignments = make_all_assignments(cells)

        for k in range(4):
            clue = AtMostClue(f"row_{k}", owner=CellId("A2"), k=k, region=region)
            aux = AuxAllocator(pmap)
            clauses = encode_at_most(clue, pmap, aux, grid_size)

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_cardinality(clue, full, grid_size)
                assert cnf_sat == sem_sat


# ---------------------------------------------------------------------------
# 4. Exhaustive semantics equivalence — AT_LEAST
# ---------------------------------------------------------------------------

class TestSemanticsEquivalenceAtLeast:
    def test_at_least_3_cells_exhaustive(self) -> None:
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        cells = [CellId("A1"), CellId("B1"), CellId("C1")]
        region = ExplicitRegion(tuple(cells))
        all_assignments = make_all_assignments(cells)

        for k in range(len(cells) + 1):
            clue = AtLeastClue(f"al_{k}", owner=CellId("A1"), k=k, region=region)
            aux = AuxAllocator(pmap)
            clauses = encode_at_least(clue, pmap, aux, grid_size)

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_cardinality(clue, full, grid_size)
                assert cnf_sat == sem_sat, (
                    f"AT_LEAST({k}) mismatch: cnf={cnf_sat}, sem={sem_sat}, asgn={partial}"
                )

    def test_at_least_4_cells_exhaustive(self) -> None:
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        cells = [CellId("A1"), CellId("B1"), CellId("A2"), CellId("B2")]
        region = ExplicitRegion(tuple(cells))
        all_assignments = make_all_assignments(cells)

        for k in range(len(cells) + 1):
            clue = AtLeastClue(f"al4_{k}", owner=CellId("A1"), k=k, region=region)
            aux = AuxAllocator(pmap)
            clauses = encode_at_least(clue, pmap, aux, grid_size)

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_cardinality(clue, full, grid_size)
                assert cnf_sat == sem_sat, (
                    f"AT_LEAST({k}, 4 cells) mismatch on {partial}"
                )

    def test_at_least_col_region_exhaustive(self) -> None:
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        region = ColRegion("B")  # B1, B2, B3
        cells = list(resolve_region(region, grid_size))
        all_assignments = make_all_assignments(cells)

        for k in range(4):
            clue = AtLeastClue(f"col_{k}", owner=CellId("B1"), k=k, region=region)
            aux = AuxAllocator(pmap)
            clauses = encode_at_least(clue, pmap, aux, grid_size)

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_cardinality(clue, full, grid_size)
                assert cnf_sat == sem_sat


# ---------------------------------------------------------------------------
# 5. Exhaustive semantics equivalence — EXACTLY
# ---------------------------------------------------------------------------

class TestSemanticsEquivalenceExactly:
    def test_exactly_3_cells_exhaustive(self) -> None:
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        cells = [CellId("A1"), CellId("B1"), CellId("C1")]
        region = ExplicitRegion(tuple(cells))
        all_assignments = make_all_assignments(cells)

        for k in range(len(cells) + 1):
            clue = ExactlyClue(f"ex_{k}", owner=CellId("A1"), k=k, region=region)
            aux = AuxAllocator(pmap)
            clauses = encode_exactly(clue, pmap, aux, grid_size)

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_cardinality(clue, full, grid_size)
                assert cnf_sat == sem_sat, (
                    f"EXACTLY({k}) mismatch: cnf={cnf_sat}, sem={sem_sat}, asgn={partial}"
                )

    def test_exactly_2_cells_exhaustive(self) -> None:
        grid_size = 2
        pmap = PrimaryVarMap(grid_size)
        cells = [CellId("A1"), CellId("B1")]
        region = ExplicitRegion(tuple(cells))
        all_assignments = make_all_assignments(cells)

        for k in range(len(cells) + 1):
            clue = ExactlyClue(f"ex2_{k}", owner=CellId("A1"), k=k, region=region)
            aux = AuxAllocator(pmap)
            clauses = encode_exactly(clue, pmap, aux, grid_size)

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_cardinality(clue, full, grid_size)
                assert cnf_sat == sem_sat

    def test_exactly_neighbors_region_exhaustive(self) -> None:
        """Corner cell A1 has 3 neighbors in 3×3: B1, A2, B2."""
        grid_size = 3
        pmap = PrimaryVarMap(grid_size)
        region = NeighborsRegion(CellId("A1"))
        cells = list(resolve_region(region, grid_size))
        assert len(cells) == 3
        all_assignments = make_all_assignments(cells)

        for k in range(4):
            clue = ExactlyClue(f"ex_nbr_{k}", owner=CellId("A1"), k=k, region=region)
            aux = AuxAllocator(pmap)
            clauses = encode_exactly(clue, pmap, aux, grid_size)

            for partial in all_assignments:
                full = complete_assignment(partial, grid_size)
                prim = to_primary_assignment(full, pmap)
                cnf_sat = cnf_sat_exists_aux(clauses, prim, pmap.num_primary, aux.num_aux)
                sem_sat = evaluate_cardinality(clue, full, grid_size)
                assert cnf_sat == sem_sat


# ---------------------------------------------------------------------------
# 6. Fresh auxiliary variable separation across two clues
# ---------------------------------------------------------------------------

class TestAuxiliaryVariableSeparation:
    def test_two_at_most_clues_disjoint_aux_ranges(self) -> None:
        pmap = PrimaryVarMap(3)  # primary: 1..9
        aux = AuxAllocator(pmap)

        r1 = ExplicitRegion((CellId("A1"), CellId("B1"), CellId("C1")))
        clue1 = AtMostClue("c1", CellId("A1"), 1, r1)  # 3×1 = 3 aux: 10..12
        clauses1 = encode_at_most(clue1, pmap, aux, 3)
        assert aux.num_aux == 3

        r2 = ExplicitRegion((CellId("A2"), CellId("B2"), CellId("C2")))
        clue2 = AtMostClue("c2", CellId("A2"), 2, r2)  # 3×2 = 6 aux: 13..18
        clauses2 = encode_at_most(clue2, pmap, aux, 3)
        assert aux.num_aux == 9

        aux1_vars = {abs(lit) for cl in clauses1 for lit in cl if abs(lit) > pmap.num_primary}
        aux2_vars = {abs(lit) for cl in clauses2 for lit in cl if abs(lit) > pmap.num_primary}

        assert aux1_vars == {10, 11, 12}
        assert aux2_vars == {13, 14, 15, 16, 17, 18}
        assert aux1_vars.isdisjoint(aux2_vars)

    def test_mixed_clues_disjoint_aux_ranges(self) -> None:
        pmap = PrimaryVarMap(3)  # primary: 1..9
        aux = AuxAllocator(pmap)
        region = RowRegion(1)  # n = 3

        # AT_MOST(1, 3) → 3×1 = 3 aux
        encode_at_most(AtMostClue("c1", CellId("A1"), 1, region), pmap, aux, 3)
        assert aux.num_aux == 3

        # AT_LEAST(1, 3) = AT_MOST(2, negated) → 3×2 = 6 aux
        encode_at_least(AtLeastClue("c2", CellId("A2"), 1, region), pmap, aux, 3)
        assert aux.num_aux == 9

        # EXACTLY(1, 3) = AT_MOST(1) + AT_LEAST(1) → 3×1 + 3×2 = 9 aux
        encode_exactly(ExactlyClue("c3", CellId("A3"), 1, region), pmap, aux, 3)
        assert aux.num_aux == 18  # 3 + 6 + 9 total


# ---------------------------------------------------------------------------
# 7. Literal validity
# ---------------------------------------------------------------------------

class TestLiteralValidity:
    def test_no_zero_literals(self) -> None:
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        region = RowRegion(1)

        for clauses in [
            encode_at_most(AtMostClue("c", CellId("A1"), 1, region), pmap, aux, 3),
            encode_at_least(AtLeastClue("c", CellId("A1"), 1, region), pmap, aux, 3),
            encode_exactly(ExactlyClue("c", CellId("A1"), 1, region), pmap, aux, 3),
            encode_at_most(AtMostClue("c", CellId("A1"), 0, region), pmap, aux, 3),
            encode_at_least(AtLeastClue("c", CellId("A1"), 3, region), pmap, aux, 3),
        ]:
            for cl in clauses:
                assert 0 not in cl, f"Zero literal found in clause {cl}"

    def test_no_duplicate_literals_in_clause(self) -> None:
        pmap = PrimaryVarMap(3)
        region = RowRegion(1)

        for encode_fn, clue in [
            (encode_at_most, AtMostClue("c", CellId("A1"), 1, region)),
            (encode_at_least, AtLeastClue("c", CellId("A1"), 1, region)),
            (encode_exactly, ExactlyClue("c", CellId("A1"), 1, region)),
        ]:
            aux = AuxAllocator(pmap)
            clauses = encode_fn(clue, pmap, aux, 3)
            for cl in clauses:
                assert len(cl) == len(set(cl)), f"Duplicate literal in {cl}"

    def test_all_literal_abs_values_within_declared_range(self) -> None:
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        region = RowRegion(1)
        clue = ExactlyClue("c", CellId("A1"), 1, region)
        clauses = encode_exactly(clue, pmap, aux, 3)

        max_allowed = pmap.num_primary + aux.num_aux
        for cl in clauses:
            for lit in cl:
                assert 1 <= abs(lit) <= max_allowed, (
                    f"Literal {lit} outside range 1..{max_allowed}"
                )


# ---------------------------------------------------------------------------
# 8. Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_negative_k_raises_value_error(self) -> None:
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        region = RowRegion(1)
        with pytest.raises(ValueError, match="out of bounds"):
            encode_at_most(AtMostClue("c", CellId("A1"), -1, region), pmap, aux, 3)
        with pytest.raises(ValueError, match="out of bounds"):
            encode_at_least(AtLeastClue("c", CellId("A1"), -1, region), pmap, aux, 3)
        with pytest.raises(ValueError, match="out of bounds"):
            encode_exactly(ExactlyClue("c", CellId("A1"), -1, region), pmap, aux, 3)

    def test_k_exceeds_region_size_raises_value_error(self) -> None:
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        region = RowRegion(1)  # size 3
        with pytest.raises(ValueError, match="out of bounds"):
            encode_at_most(AtMostClue("c", CellId("A1"), 4, region), pmap, aux, 3)
        with pytest.raises(ValueError, match="out of bounds"):
            encode_at_least(AtLeastClue("c", CellId("A1"), 4, region), pmap, aux, 3)
        with pytest.raises(ValueError, match="out of bounds"):
            encode_exactly(ExactlyClue("c", CellId("A1"), 4, region), pmap, aux, 3)

    def test_bool_k_raises_type_error(self) -> None:
        pmap = PrimaryVarMap(3)
        aux = AuxAllocator(pmap)
        region = RowRegion(1)
        with pytest.raises(TypeError, match="must be an integer"):
            encode_at_most(AtMostClue("c", CellId("A1"), True, region), pmap, aux, 3)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="must be an integer"):
            encode_at_least(AtLeastClue("c", CellId("A1"), False, region), pmap, aux, 3)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="must be an integer"):
            encode_exactly(ExactlyClue("c", CellId("A1"), True, region), pmap, aux, 3)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 9. build_cnf_from_public_state integration
# ---------------------------------------------------------------------------

class TestBuildCNFFromPublicStateCardinality:
    def test_state_with_at_most_clue(self) -> None:
        """AT_MOST(1, row1, n=3): 1 status unit + 7 counter clauses = 8; 3 aux."""
        clue = AtMostClue("am1", CellId("A1"), k=1, region=RowRegion(1))
        state = make_test_public_state(3, [clue])
        cnf = build_cnf_from_public_state(state)
        assert cnf.num_primary == 9
        assert cnf.num_aux == 3
        assert cnf.num_clauses == 8   # 1 status + (1 + 2*(2*1+1)) = 1 + 7

    def test_state_with_at_least_clue(self) -> None:
        """AT_LEAST(1, row1, n=3)=AT_MOST(2,neg): 1 status unit + 11 clauses=12; 6 aux."""
        clue = AtLeastClue("al1", CellId("A1"), k=1, region=RowRegion(1))
        state = make_test_public_state(3, [clue])
        cnf = build_cnf_from_public_state(state)
        assert cnf.num_primary == 9
        assert cnf.num_aux == 6
        assert cnf.num_clauses == 12  # 1 status + (1 + 2*(2*2+1)) = 1 + 11

    def test_state_with_exactly_clue(self) -> None:
        """EXACTLY(1, row1): 1 status + 7 (AT_MOST) + 11 (AT_LEAST) = 19; 9 aux."""
        clue = ExactlyClue("ex1", CellId("A1"), k=1, region=RowRegion(1))
        state = make_test_public_state(3, [clue])
        cnf = build_cnf_from_public_state(state)
        assert cnf.num_primary == 9
        assert cnf.num_aux == 9
        assert cnf.num_clauses == 19  # 1 status + 7 + 11

    def test_parity_clue_encodes_successfully(self) -> None:
        clue = ParityClue("p1", CellId("A1"), parity=Parity.EVEN, region=RowRegion(1))
        state = make_test_public_state(3, [clue])
        cnf = build_cnf_from_public_state(state)
        # 1 known status + 4*(3-1)+1 = 1 + 9 = 10 clauses; 2 aux
        assert cnf.num_primary == 9
        assert cnf.num_aux == 2
        assert cnf.num_clauses == 10


# ---------------------------------------------------------------------------
# 10. Architecture isolation
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
