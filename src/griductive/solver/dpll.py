"""Deterministic DPLL SAT solver implemented from scratch.

Features:
- Deterministic unit propagation to a fixed point.
- Conflict detection.
- Deterministic variable selection (lowest-numbered unassigned variable).
- Deterministic branching order (configurable, default: False then True).
- Recursive backtracking search.
- Non-destructive temporary assumptions.
- Total satisfying model generation for all declared variables (1..num_vars).
- Search metrics tracking: decisions, propagations, backtracks, and runtime.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Mapping, Sequence

from griductive.solver.cnf import CNFFormula

if TYPE_CHECKING:
    from griductive.solver.kb import KnowledgeBase


@dataclass(frozen=True)
class DpllMetrics:
    """Metrics recorded during DPLL search.

    Attributes:
        decisions: Number of branching decision steps taken.
        propagations: Number of unit propagations derived from clauses during search
            (excludes caller-supplied initial assumptions).
        backtracks: Number of times a conflict caused backtracking.
        runtime: Wall-clock execution time in seconds.
    """

    decisions: int
    propagations: int
    backtracks: int
    runtime: float


@dataclass(frozen=True)
class SatResult:
    """Outcome of a DPLL SAT search.

    Attributes:
        is_sat: True if satisfiable, False if unsatisfiable.
        model: Total mapping from variable integer (1..num_vars) to bool if SAT;
            None if UNSAT.
        metrics: Search counters and runtime.
    """

    is_sat: bool
    model: Mapping[int, bool] | None
    metrics: DpllMetrics

    def __bool__(self) -> bool:
        return self.is_sat


class _DpllSolver:
    """Internal stateful DPLL search worker."""

    def __init__(
        self,
        num_vars: int,
        clauses: tuple[tuple[int, ...], ...],
        assumptions: Sequence[int],
        branch_preference: bool,
    ) -> None:
        self.num_vars: int = num_vars
        self.clauses: tuple[tuple[int, ...], ...] = clauses
        self.assumptions: tuple[int, ...] = tuple(assumptions)
        self.branch_preference: bool = branch_preference

        # Metrics counters
        self.decisions: int = 0
        self.propagations: int = 0
        self.backtracks: int = 0

    def solve(self) -> tuple[bool, dict[int, bool] | None]:
        """Execute DPLL search. Returns (is_sat, model_or_none)."""
        # Validate assumptions and check literal bounds
        for lit in self.assumptions:
            if isinstance(lit, bool) or not isinstance(lit, int):
                raise TypeError(
                    f"Assumption literal must be an integer (and not bool), got {type(lit).__name__}: {lit!r}"
                )
            var = abs(lit)
            if var < 1 or var > self.num_vars:
                raise ValueError(
                    f"Assumption literal {lit} references out-of-range variable {var} (1..{self.num_vars})"
                )

        # Initial assignment
        assignment: dict[int, bool] = {}

        # Apply assumptions as initial unit assignments
        for lit in self.assumptions:
            var = abs(lit)
            val = lit > 0
            if var in assignment:
                if assignment[var] != val:
                    # Contradictory assumptions: immediate UNSAT
                    return False, None
            else:
                assignment[var] = val
                # Caller-supplied assumptions are not counted as unit propagations.

        # Check for empty clauses in formula immediately
        for clause in self.clauses:
            if len(clause) == 0:
                return False, None

        # Unit propagate initial state (assumptions + base unit clauses)
        success = self._unit_propagate(assignment)
        if not success:
            return False, None

        # Begin recursive search
        return self._search(assignment)

    def _unit_propagate(self, assignment: dict[int, bool]) -> bool:
        """Propagate unit clauses to a fixed point.

        Returns False if a contradiction (conflict clause) is detected,
        True otherwise.
        """
        while True:
            propagated_in_loop = False
            for clause in self.clauses:
                # Evaluate clause status
                # A clause can legally contain duplicate literals.  Count distinct
                # unassigned literals so (x OR x) is treated exactly as the unit
                # clause (x), without changing the immutable source formula.
                unassigned_lits: set[int] = set()
                clause_satisfied = False

                for lit in clause:
                    var = abs(lit)
                    if var in assignment:
                        val = assignment[var]
                        if (lit > 0 and val) or (lit < 0 and not val):
                            clause_satisfied = True
                            break
                    else:
                        unassigned_lits.add(lit)

                if clause_satisfied:
                    continue

                if not unassigned_lits:
                    # All literals in clause are falsified -> conflict
                    return False

                if len(unassigned_lits) == 1:
                    # Unit clause: force assignment of unassigned_lit
                    unassigned_lit = next(iter(unassigned_lits))
                    var = abs(unassigned_lit)
                    val = unassigned_lit > 0
                    assignment[var] = val
                    self.propagations += 1
                    propagated_in_loop = True
                    break  # Restart loop to propagate with new assignment

            if not propagated_in_loop:
                break

        return True

    def _is_all_clauses_satisfied(self, assignment: dict[int, bool]) -> bool:
        """Check if every clause in the formula is satisfied."""
        for clause in self.clauses:
            satisfied = False
            for lit in clause:
                var = abs(lit)
                if var in assignment:
                    val = assignment[var]
                    if (lit > 0 and val) or (lit < 0 and not val):
                        satisfied = True
                        break
            if not satisfied:
                return False
        return True

    def _search(self, assignment: dict[int, bool]) -> tuple[bool, dict[int, bool] | None]:
        """Recursive DPLL branching search."""
        # Check if all clauses are already satisfied
        if self._is_all_clauses_satisfied(assignment):
            # Fill any remaining unassigned variables deterministically
            total_model = dict(assignment)
            for v in range(1, self.num_vars + 1):
                if v not in total_model:
                    total_model[v] = self.branch_preference
            return True, total_model

        # Select the lowest-numbered unassigned variable deterministically
        chosen_var: int | None = None
        for v in range(1, self.num_vars + 1):
            if v not in assignment:
                chosen_var = v
                break

        if chosen_var is None:
            # All variables assigned, verify all clauses satisfied
            if self._is_all_clauses_satisfied(assignment):
                return True, dict(assignment)
            return False, None

        # Fixed truth order branching
        first_val = self.branch_preference
        second_val = not first_val

        # Branch 1
        self.decisions += 1
        branch1_assignment = dict(assignment)
        branch1_assignment[chosen_var] = first_val
        if self._unit_propagate(branch1_assignment):
            sat, model = self._search(branch1_assignment)
            if sat:
                return True, model
        self.backtracks += 1

        # Branch 2
        self.decisions += 1
        branch2_assignment = dict(assignment)
        branch2_assignment[chosen_var] = second_val
        if self._unit_propagate(branch2_assignment):
            sat, model = self._search(branch2_assignment)
            if sat:
                return True, model
        self.backtracks += 1

        return False, None


def solve_dpll(
    cnf: CNFFormula | KnowledgeBase,
    assumptions: Sequence[int] | None = None,
    branch_preference: bool = False,
) -> SatResult:
    """Solve a CNF formula or KnowledgeBase using custom deterministic DPLL.

    Args:
        cnf: Immutable CNFFormula or KnowledgeBase to solve.
        assumptions: Optional sequence of non-zero integer literals treated as
            temporary unit assumptions without mutating the base formula.
            Note: Explicit assumptions are not counted as unit propagations in
            metrics; only assignments derived via clause unit propagation are counted.
        branch_preference: First truth value to try when branching (default False).

    Returns:
        SatResult containing:
        - is_sat: True if a satisfying model exists, False otherwise.
        - model: Complete mapping {1..num_vars -> bool} when SAT; None when UNSAT.
        - metrics: DpllMetrics recording decisions, propagations, backtracks, runtime.
    """
    assump_seq = () if assumptions is None else tuple(assumptions)
    solver = _DpllSolver(
        num_vars=cnf.num_vars,
        clauses=cnf.clauses,
        assumptions=assump_seq,
        branch_preference=branch_preference,
    )

    start_time = time.perf_counter()
    is_sat, raw_model = solver.solve()
    runtime = time.perf_counter() - start_time

    model = MappingProxyType(raw_model) if raw_model is not None else None
    metrics = DpllMetrics(
        decisions=solver.decisions,
        propagations=solver.propagations,
        backtracks=solver.backtracks,
        runtime=runtime,
    )

    return SatResult(is_sat=is_sat, model=model, metrics=metrics)
