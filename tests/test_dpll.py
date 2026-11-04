"""Comprehensive tests for custom deterministic DPLL SAT solver (T09).

Tests unit propagation, conflict detection, deterministic variable selection,
recursive branching, backtracking, temporary assumptions, total model completion,
search metrics (decisions, propagations, backtracks, runtime), and cross-checks
against an independent brute-force SAT oracle.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

import pytest

from griductive.solver.cnf import (
    AuxAllocator,
    CNFFormula,
    PrimaryVarMap,
    build_cnf_from_public_state,
    encode_fact,
    encode_same,
)
from griductive.solver.dpll import DpllMetrics, SatResult, solve_dpll
from griductive.domain.model import (
    CellId,
    Character,
    FactClue,
    PublicCard,
    PublicState,
    SameClue,
    Status,
)


# ---------------------------------------------------------------------------
# Independent Brute-Force Oracle
# ---------------------------------------------------------------------------


def brute_force_oracle(
    num_vars: int,
    clauses: Sequence[Sequence[int]],
    assumptions: Sequence[int] = (),
) -> tuple[bool, dict[int, bool] | None]:
    """Independent exhaustive brute-force SAT solver for ground-truth cross-checks."""
    # Check for empty clause
    for cl in clauses:
        if len(cl) == 0:
            return False, None

    all_clauses = list(clauses) + [[lit] for lit in assumptions]

    for bits in range(1 << num_vars):
        assignment = {
            v: bool((bits >> (v - 1)) & 1)
            for v in range(1, num_vars + 1)
        }
        all_satisfied = True
        for cl in all_clauses:
            clause_sat = False
            for lit in cl:
                var = abs(lit)
                val = assignment[var]
                if (lit > 0 and val) or (lit < 0 and not val):
                    clause_sat = True
                    break
            if not clause_sat:
                all_satisfied = False
                break
        if all_satisfied:
            return True, assignment

    return False, None


def verify_model_satisfies(
    clauses: Sequence[Sequence[int]],
    model: Mapping[int, bool],
    assumptions: Sequence[int] = (),
) -> bool:
    """Verify that a model satisfies every clause and every assumption."""
    all_clauses = list(clauses) + [[lit] for lit in assumptions]
    for cl in all_clauses:
        sat = False
        for lit in cl:
            var = abs(lit)
            if var not in model:
                return False
            val = model[var]
            if (lit > 0 and val) or (lit < 0 and not val):
                sat = True
                break
        if not sat:
            return False
    return True


# ---------------------------------------------------------------------------
# 1. Unit Propagation & Chains
# ---------------------------------------------------------------------------


class TestUnitPropagation:
    def test_single_positive_unit_clause(self) -> None:
        pmap = PrimaryVarMap(1)  # 1 var
        cnf = CNFFormula(clauses=((1,),), primary_map=pmap)
        res = solve_dpll(cnf)

        assert res.is_sat is True
        assert res.model is not None
        assert res.model[1] is True
        assert res.metrics.propagations >= 1
        assert res.metrics.decisions == 0

    def test_single_negative_unit_clause(self) -> None:
        pmap = PrimaryVarMap(1)
        cnf = CNFFormula(clauses=((-1,),), primary_map=pmap)
        res = solve_dpll(cnf)

        assert res.is_sat is True
        assert res.model is not None
        assert res.model[1] is False
        assert res.metrics.propagations >= 1

    def test_propagation_chain(self) -> None:
        """(1,) forces 1=True -> (-1, 2) forces 2=True -> (-2, 3) forces 3=True."""
        pmap = PrimaryVarMap(2)  # 4 vars
        clauses = (
            (1,),
            (-1, 2),
            (-2, 3),
        )
        cnf = CNFFormula(clauses=clauses, primary_map=pmap)
        res = solve_dpll(cnf)

        assert res.is_sat is True
        assert res.model is not None
        assert res.model[1] is True
        assert res.model[2] is True
        assert res.model[3] is True
        # 4 is unconstrained, gets filled deterministically
        assert 4 in res.model
        assert res.metrics.propagations >= 3
        assert res.metrics.decisions == 0

    def test_unit_clause_conflict_immediate_unsat(self) -> None:
        """(1,) and (-1,) produce immediate contradiction."""
        pmap = PrimaryVarMap(1)
        cnf = CNFFormula(clauses=((1,), (-1,)), primary_map=pmap)
        res = solve_dpll(cnf)

        assert res.is_sat is False
        assert res.model is None


# ---------------------------------------------------------------------------
# 2. Branching & Backtracking
# ---------------------------------------------------------------------------


class TestBranchingAndBacktracking:
    def test_branching_needed_simple_or(self) -> None:
        """(1, 2): no unit clauses initially, branching is required."""
        pmap = PrimaryVarMap(2)
        cnf = CNFFormula(clauses=((1, 2),), primary_map=pmap)
        res = solve_dpll(cnf, branch_preference=False)

        assert res.is_sat is True
        assert res.model is not None
        assert verify_model_satisfies(cnf.clauses, res.model)
        assert res.metrics.decisions >= 1

    def test_backtracking_on_infeasible_branch(self) -> None:
        """Formula where var 1=False leads to conflict, so solver backtracks to 1=True.

        Clauses: (1, 2), (1, -2) -> If 1=False, 2 must be True and False (conflict).
        """
        pmap = PrimaryVarMap(2)  # 4 vars
        clauses = ((1, 2), (1, -2))
        cnf = CNFFormula(clauses=clauses, primary_map=pmap)

        # branch_preference=False tries 1=False first, which conflicts and backtracks
        res = solve_dpll(cnf, branch_preference=False)

        assert res.is_sat is True
        assert res.model is not None
        assert res.model[1] is True
        assert res.metrics.backtracks >= 1
        assert verify_model_satisfies(cnf.clauses, res.model)

    def test_unsat_formula_with_multiple_backtracks(self) -> None:
        """Classic 2-variable UNSAT formula: all 4 combinations forbidden."""
        pmap = PrimaryVarMap(2)  # 4 vars, but only 2 constrained
        clauses = (
            (1, 2),
            (1, -2),
            (-1, 2),
            (-1, -2),
        )
        cnf = CNFFormula(clauses=clauses, primary_map=pmap)
        res = solve_dpll(cnf)

        assert res.is_sat is False
        assert res.model is None
        assert res.metrics.backtracks >= 2


# ---------------------------------------------------------------------------
# 3. Cross-Check Against Independent Brute-Force Oracle
# ---------------------------------------------------------------------------


class TestBruteForceOracleCrossCheck:
    @pytest.mark.parametrize(
        "clauses,num_vars",
        [
            # Single clause
            (((1, -2),), 2),
            # All 4 combinations of 2 variables
            (((1, 2), (1, -2), (-1, 2)), 2),
            (((1, 2), (1, -2), (-1, 2), (-1, -2)), 2),
            # 3 variables, various satisfiable patterns
            (((1, 2, 3), (-1, -2), (-2, -3)), 3),
            (((1, 2), (-1, 3), (-2, -3), (2, -3)), 3),
            # 3 variables UNSAT
            (
                (
                    (1, 2),
                    (1, -2),
                    (-1, 3),
                    (-1, -3),
                    (-2, 3),
                    (-2, -3),
                ),
                3,
            ),
            # 4 variables 2-SAT chain
            (((-1, 2), (-2, 3), (-3, 4), (-4, -1), (1,)), 4),
            # 4 variables independent components
            (((1, 2), (-1, -2), (3, 4), (-3, -4)), 4),
        ],
    )
    def test_dpll_matches_brute_force(
        self, clauses: tuple[tuple[int, ...], ...], num_vars: int
    ) -> None:
        oracle_sat, oracle_model = brute_force_oracle(num_vars, clauses)

        # Create dummy CNFFormula
        # PrimaryVarMap requires grid_size >= 1, so choose smallest grid_size where N^2 >= num_vars
        grid_size = 2 if num_vars <= 4 else 3
        pmap = PrimaryVarMap(grid_size)
        num_aux = max(0, num_vars - pmap.num_primary)
        cnf = CNFFormula(clauses=clauses, primary_map=pmap, num_aux=num_aux)

        res = solve_dpll(cnf)

        assert res.is_sat == oracle_sat, f"Mismatch for clauses {clauses}"
        if res.is_sat:
            assert res.model is not None
            assert verify_model_satisfies(clauses, res.model)
            # Total model check
            for v in range(1, cnf.num_vars + 1):
                assert v in res.model


# ---------------------------------------------------------------------------
# 4. Temporary Assumptions
# ---------------------------------------------------------------------------


class TestTemporaryAssumptions:
    def test_assumption_restricts_sat_space(self) -> None:
        """Formula (1, 2): SAT without assumptions; assuming (-1, -2) yields UNSAT."""
        pmap = PrimaryVarMap(2)
        cnf = CNFFormula(clauses=((1, 2),), primary_map=pmap)

        # Base formula is SAT
        res_base = solve_dpll(cnf)
        assert res_base.is_sat is True

        # Assumption (-1, -2) makes it UNSAT
        res_unsat = solve_dpll(cnf, assumptions=[-1, -2])
        assert res_unsat.is_sat is False

        # Verify base CNF was not modified
        assert cnf.clauses == ((1, 2),)
        res_base2 = solve_dpll(cnf)
        assert res_base2.is_sat is True

    def test_multiple_queries_with_different_assumptions(self) -> None:
        """Check entailment pattern: (1 -> 2), assumption 1 proves 2."""
        pmap = PrimaryVarMap(2)
        # 1 -> 2  is  (-1, 2)
        cnf = CNFFormula(clauses=((-1, 2),), primary_map=pmap)

        # Assume 1 and -2 -> UNSAT (proves that 1 entails 2)
        res = solve_dpll(cnf, assumptions=[1, -2])
        assert res.is_sat is False

        # Assume 1 and 2 -> SAT
        res_sat = solve_dpll(cnf, assumptions=[1, 2])
        assert res_sat.is_sat is True
        assert res_sat.model[1] is True
        assert res_sat.model[2] is True

    def test_contradictory_assumptions_immediate_unsat(self) -> None:
        pmap = PrimaryVarMap(2)
        cnf = CNFFormula(clauses=((1, 2),), primary_map=pmap)
        res = solve_dpll(cnf, assumptions=[1, -1])

        assert res.is_sat is False
        assert res.model is None

    def test_out_of_bounds_assumption_raises_value_error(self) -> None:
        pmap = PrimaryVarMap(2)  # 4 vars
        cnf = CNFFormula(clauses=((1,),), primary_map=pmap)

        with pytest.raises(ValueError, match="out-of-range"):
            solve_dpll(cnf, assumptions=[10])

        with pytest.raises(ValueError, match="out-of-range"):
            solve_dpll(cnf, assumptions=[0])

    def test_assumptions_excluded_from_propagation_count(self) -> None:
        """FIX-03: Assumptions must not be counted as unit propagations."""
        pmap = PrimaryVarMap(2)
        # (1, 2) has no unit clauses
        cnf = CNFFormula(clauses=((1, 2),), primary_map=pmap)

        # Solving with assumption [1]: satisfies (1, 2) directly, no clause unit propagation
        res = solve_dpll(cnf, assumptions=[1])
        assert res.is_sat is True
        assert res.metrics.propagations == 0
        assert res.metrics.decisions == 0

        # (-1, 2): assuming [1] forces var 2 via clause unit propagation
        cnf2 = CNFFormula(clauses=((-1, 2),), primary_map=pmap)
        res2 = solve_dpll(cnf2, assumptions=[1])
        assert res2.is_sat is True
        # Assumption [1] does not count, but the unit propagation of 2 DOES count
        assert res2.metrics.propagations == 1

    def test_assumption_type_validation(self) -> None:
        """Assumption literals must be integers and not booleans or floats."""
        pmap = PrimaryVarMap(2)
        cnf = CNFFormula(clauses=((1, 2),), primary_map=pmap)

        with pytest.raises(TypeError, match="Assumption literal must be an integer"):
            solve_dpll(cnf, assumptions=[True])  # type: ignore[list-item]

        with pytest.raises(TypeError, match="Assumption literal must be an integer"):
            solve_dpll(cnf, assumptions=[False])  # type: ignore[list-item]

        with pytest.raises(TypeError, match="Assumption literal must be an integer"):
            solve_dpll(cnf, assumptions=[1.5])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# 5. Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_duplicate_literals_are_unit_and_preserve_assumption_behavior(self) -> None:
        """(x OR x) must propagate as the same unit constraint as (x)."""
        pmap = PrimaryVarMap(1)
        duplicate_unit = CNFFormula(clauses=((1, 1),), primary_map=pmap)

        sat_result = solve_dpll(duplicate_unit)
        assert sat_result.is_sat is True
        assert sat_result.model is not None
        assert sat_result.model[1] is True
        assert sat_result.metrics.decisions == 0
        assert sat_result.metrics.propagations == 1
        assert sat_result.metrics.backtracks == 0

        conflicting = CNFFormula(
            clauses=((1, 1), (-1, -1)), primary_map=pmap
        )
        conflict_result = solve_dpll(conflicting)
        assert conflict_result.is_sat is False
        assert conflict_result.metrics.decisions == 0
        assert conflict_result.metrics.propagations == 1

        assumed_conflict = solve_dpll(duplicate_unit, assumptions=(-1,))
        assert assumed_conflict.is_sat is False
        assert assumed_conflict.metrics.propagations == 0
        # Assumptions must remain temporary and not alter the source formula.
        assert duplicate_unit.clauses == ((1, 1),)

    def test_empty_cnf_zero_clauses(self) -> None:
        """Empty formula (0 clauses) is trivially SAT."""
        pmap = PrimaryVarMap(2)  # 4 vars
        cnf = CNFFormula(clauses=(), primary_map=pmap)
        res = solve_dpll(cnf)

        assert res.is_sat is True
        assert res.model is not None
        assert len(res.model) == 4
        # All unconstrained vars default to False
        for v in range(1, 5):
            assert res.model[v] is False
        assert res.metrics.decisions == 0
        assert res.metrics.propagations == 0
        assert res.metrics.backtracks == 0

    def test_empty_clause_in_formula_immediate_unsat(self) -> None:
        """Formula containing () is immediately UNSAT."""
        pmap = PrimaryVarMap(1)
        cnf = CNFFormula(clauses=((),), primary_map=pmap)
        res = solve_dpll(cnf)

        assert res.is_sat is False
        assert res.model is None

    def test_unconstrained_variables_filled_deterministically(self) -> None:
        """Formula only constrains var 2. Vars 1, 3, 4 must be filled deterministically."""
        pmap = PrimaryVarMap(2)  # 4 vars
        cnf = CNFFormula(clauses=((2,),), primary_map=pmap)

        res_false = solve_dpll(cnf, branch_preference=False)
        assert res_false.is_sat is True
        assert res_false.model[2] is True
        assert res_false.model[1] is False
        assert res_false.model[3] is False
        assert res_false.model[4] is False

        res_true = solve_dpll(cnf, branch_preference=True)
        assert res_true.is_sat is True
        assert res_true.model[2] is True
        assert res_true.model[1] is True
        assert res_true.model[3] is True
        assert res_true.model[4] is True

    def test_model_is_immutable_proxy(self) -> None:
        pmap = PrimaryVarMap(1)
        cnf = CNFFormula(clauses=((1,),), primary_map=pmap)
        res = solve_dpll(cnf)

        assert isinstance(res.model, MappingProxyType)
        with pytest.raises(TypeError):
            res.model[1] = False  # type: ignore[index]

    def test_bool_conversion_of_sat_result(self) -> None:
        pmap = PrimaryVarMap(1)
        res_sat = solve_dpll(CNFFormula(clauses=((1,),), primary_map=pmap))
        assert bool(res_sat) is True

        res_unsat = solve_dpll(CNFFormula(clauses=((1,), (-1,)), primary_map=pmap))
        assert bool(res_unsat) is False


# ---------------------------------------------------------------------------
# 6. Real Griductive Formula Integration
# ---------------------------------------------------------------------------


class TestGriductiveIntegration:
    def test_solve_public_state_cnf(self) -> None:
        """Build CNF from a PublicState with FACT and SAME clues and solve it."""
        all_cells = [CellId.from_coords(r, c) for r in (1, 2) for c in (1, 2)]
        characters = [
            Character(cell=cell, name=f"Char_{chr(65 + i)}", profession="Tester")
            for i, cell in enumerate(sorted(all_cells))
        ]
        char_by_cell = {ch.cell: ch for ch in characters}

        # Clues:
        # A1 is INNOCENT (known status)
        # Clue on A1: SAME(A1, B1) -> B1 is also INNOCENT
        # Clue on B1: FACT(A2, CRIMINAL) -> A2 is CRIMINAL
        c1 = SameClue("s1", owner=CellId("A1"), person_a=CellId("A1"), person_b=CellId("B1"))
        c2 = FactClue("f1", owner=CellId("B1"), target=CellId("A2"), status=Status.CRIMINAL)

        cards = {}
        for cell in all_cells:
            if cell in (CellId("A1"), CellId("B1")):
                status = Status.INNOCENT if cell == CellId("A1") else Status.INNOCENT
                clue = c1 if cell == CellId("A1") else c2
                cards[cell] = PublicCard(cell, char_by_cell[cell], is_revealed=True, status=status, clue=clue)
            else:
                cards[cell] = PublicCard(cell, char_by_cell[cell], is_revealed=False)

        state = PublicState(
            grid_size=2,
            characters=tuple(characters),
            cards=cards,
            known_statuses={CellId("A1"): Status.INNOCENT, CellId("B1"): Status.INNOCENT},
            revealed_clues=(c1, c2),
            revealed_cells=frozenset({CellId("A1"), CellId("B1")}),
            revision=1,
        )

        cnf = build_cnf_from_public_state(state)
        res = solve_dpll(cnf)

        assert res.is_sat is True
        assert res.model is not None
        # A1 is INNOCENT -> var 1 is False
        assert res.model[1] is False
        # B1 is INNOCENT -> var 2 is False
        assert res.model[2] is False
        # A2 is CRIMINAL -> var 3 is True
        assert res.model[3] is True


# ---------------------------------------------------------------------------
# 7. Architecture Isolation
# ---------------------------------------------------------------------------


class TestArchitectureIsolation:
    def test_dpll_does_not_import_forbidden_modules(self) -> None:
        """dpll.py must not import engine, semantics, logic, controller, gui, or validation."""
        dpll_path = (
            Path(__file__).resolve().parent.parent / "src" / "griductive" / "solver" / "dpll.py"
        )
        tree = ast.parse(dpll_path.read_text(encoding="utf-8"))
        forbidden = {
            "engine", "semantics", "logic",
            "controller", "gui", "validation",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(f in alias.name for f in forbidden), (
                        f"Forbidden import in dpll.py: {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert not any(f in node.module for f in forbidden), (
                        f"Forbidden 'from' import in dpll.py: {node.module}"
                    )
