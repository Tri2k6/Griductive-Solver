"""SAT-based entailment classification and logical proof service (T11).

Operates exclusively on immutable PublicState snapshots. Performs sound
refutation-based SAT entailment using the custom DPLL solver to classify all
unresolved cards as CRIMINAL, INNOCENT, UNKNOWN, or INCONSISTENT.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from griductive.domain.model import CellId, PublicState, Status, Verdict
from griductive.solver.dpll import DpllMetrics, solve_dpll
from griductive.solver.kb import KnowledgeBase, build_knowledge_base


@dataclass(frozen=True)
class SatQueryRecord:
    """Record of a single SAT assumption query during entailment proof.

    Attributes:
        assumptions: Signed literal integers assumed for the query.
        is_sat: True if satisfiable under the assumptions, False if UNSAT.
        metrics: Search metrics for this individual query.
    """

    assumptions: tuple[int, ...]
    is_sat: bool
    metrics: DpllMetrics


@dataclass(frozen=True)
class CellClassification:
    """Classification outcome and proof evidence for a specific cell.

    Attributes:
        cell: Target cell coordinate.
        verdict: Verdict classification (CRIMINAL, INNOCENT, UNKNOWN, or INCONSISTENT).
        queries: Evidence queries executed to establish this verdict.
        primary_var: 1-indexed primary variable integer representing this cell.
    """

    cell: CellId
    verdict: Verdict
    queries: tuple[SatQueryRecord, ...]
    primary_var: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "queries", tuple(self.queries))


@dataclass(frozen=True)
class ProofReport:
    """Complete entailment proof report across all unresolved cards in a PublicState.

    Attributes:
        state_revision: Revision number of the PublicState classified.
        base_consistent: True if the public knowledge base is satisfiable, False if inconsistent.
        base_query: The base KB consistency query.
        classifications: Deterministic mapping of unresolved CellIds to their CellClassification.
        total_sat_calls: Total number of DPLL solver calls executed.
        aggregate_metrics: Sum of metrics (decisions, propagations, backtracks, runtime) across all queries.
    """

    state_revision: int
    base_consistent: bool
    base_query: SatQueryRecord
    classifications: Mapping[CellId, CellClassification]
    total_sat_calls: int
    aggregate_metrics: DpllMetrics

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "classifications", MappingProxyType(dict(self.classifications))
        )

    @property
    def forced_cells(self) -> tuple[CellClassification, ...]:
        """All unresolved cells whose status is logically entailed, in deterministic row-major order."""
        return tuple(
            c
            for c in self.classifications.values()
            if c.verdict in (Verdict.CRIMINAL, Verdict.INNOCENT)
        )

    @property
    def first_forced_cell(self) -> CellClassification | None:
        """First forced cell in deterministic row-major order, or None if none are forced."""
        forced = self.forced_cells
        return forced[0] if forced else None


class ProofService:
    """Proof service providing sound refutation-based SAT entailment on public state."""

    @staticmethod
    def classify_state(state: PublicState) -> ProofReport:
        """Classify every unresolved character in state via sound SAT entailment.

        1. Check whether KB_t is satisfiable.
        2. If KB_t is UNSAT, return INCONSISTENT for all unresolved cells.
        3. For each unresolved cell i (in row-major order):
           - If KB_t AND NOT C_i is UNSAT -> classify CRIMINAL.
           - Else if KB_t AND C_i is UNSAT -> classify INNOCENT.
           - Else (both branches satisfiable) -> classify UNKNOWN.
        """
        kb = build_knowledge_base(state)
        pmap = kb.primary_map

        # Step 1: Base consistency check
        base_res = solve_dpll(kb.formula, assumptions=())
        base_query = SatQueryRecord(
            assumptions=(),
            is_sat=base_res.is_sat,
            metrics=base_res.metrics,
        )

        total_decisions = base_res.metrics.decisions
        total_propagations = base_res.metrics.propagations
        total_backtracks = base_res.metrics.backtracks
        total_runtime = base_res.metrics.runtime
        sat_calls = 1

        # Determine unresolved cells in deterministic row-major order
        all_cells = [
            CellId.from_coords(r, c)
            for r in range(1, state.grid_size + 1)
            for c in range(1, state.grid_size + 1)
        ]
        unresolved_cells = [
            cell for cell in all_cells if cell not in state.revealed_cells
        ]

        classifications: dict[CellId, CellClassification] = {}

        # Step 2: If base is UNSAT, mark all unresolved cells as INCONSISTENT
        if not base_res.is_sat:
            for cell in unresolved_cells:
                var = pmap.cell_to_var(cell)
                classifications[cell] = CellClassification(
                    cell=cell,
                    verdict=Verdict.INCONSISTENT,
                    queries=(),
                    primary_var=var,
                )
        else:
            # Step 3: Base is SAT; test each unresolved cell via refutation
            for cell in unresolved_cells:
                var = pmap.cell_to_var(cell)
                queries: list[SatQueryRecord] = []

                # Query 1: Assume NOT C_i (-var)
                res_neg = solve_dpll(kb.formula, assumptions=(-var,))
                q1 = SatQueryRecord(
                    assumptions=(-var,),
                    is_sat=res_neg.is_sat,
                    metrics=res_neg.metrics,
                )
                queries.append(q1)
                total_decisions += res_neg.metrics.decisions
                total_propagations += res_neg.metrics.propagations
                total_backtracks += res_neg.metrics.backtracks
                total_runtime += res_neg.metrics.runtime
                sat_calls += 1

                if not res_neg.is_sat:
                    # KB ∧ ¬C_i is UNSAT -> C_i is forced CRIMINAL
                    verdict = Verdict.CRIMINAL
                else:
                    # Query 2: Assume C_i (+var)
                    res_pos = solve_dpll(kb.formula, assumptions=(var,))
                    q2 = SatQueryRecord(
                        assumptions=(var,),
                        is_sat=res_pos.is_sat,
                        metrics=res_pos.metrics,
                    )
                    queries.append(q2)
                    total_decisions += res_pos.metrics.decisions
                    total_propagations += res_pos.metrics.propagations
                    total_backtracks += res_pos.metrics.backtracks
                    total_runtime += res_pos.metrics.runtime
                    sat_calls += 1

                    if not res_pos.is_sat:
                        # KB ∧ C_i is UNSAT -> C_i is forced INNOCENT
                        verdict = Verdict.INNOCENT
                    else:
                        # Both SAT -> UNKNOWN
                        verdict = Verdict.UNKNOWN

                classifications[cell] = CellClassification(
                    cell=cell,
                    verdict=verdict,
                    queries=tuple(queries),
                    primary_var=var,
                )

        aggregate_metrics = DpllMetrics(
            decisions=total_decisions,
            propagations=total_propagations,
            backtracks=total_backtracks,
            runtime=total_runtime,
        )

        return ProofReport(
            state_revision=state.revision,
            base_consistent=base_res.is_sat,
            base_query=base_query,
            classifications=classifications,
            total_sat_calls=sat_calls,
            aggregate_metrics=aggregate_metrics,
        )

    @staticmethod
    def classify_cell(state: PublicState, cell: CellId) -> CellClassification:
        """Classify a single target cell under the current public state.

        Used to evaluate manual calls or targeted queries.
        Always verifies base-KB consistency first: if the base KB is unsatisfiable,
        returns INCONSISTENT even if the cell is already revealed.
        """
        if not cell.is_valid_for(state.grid_size):
            raise ValueError(f"Cell {cell} out of bounds for grid_size {state.grid_size}")

        kb = build_knowledge_base(state)
        pmap = kb.primary_map
        var = pmap.cell_to_var(cell)

        # Check base consistency first
        base_res = solve_dpll(kb.formula, assumptions=())
        if not base_res.is_sat:
            return CellClassification(
                cell=cell,
                verdict=Verdict.INCONSISTENT,
                queries=(),
                primary_var=var,
            )

        # If base is consistent and cell is already revealed, return known status directly
        if cell in state.revealed_cells:
            status = state.known_statuses[cell]
            verdict = Verdict.CRIMINAL if status == Status.CRIMINAL else Verdict.INNOCENT
            return CellClassification(
                cell=cell,
                verdict=verdict,
                queries=(),
                primary_var=var,
            )

        # Query 1: assume ¬C_i
        res_neg = solve_dpll(kb.formula, assumptions=(-var,))
        q1 = SatQueryRecord(assumptions=(-var,), is_sat=res_neg.is_sat, metrics=res_neg.metrics)

        if not res_neg.is_sat:
            return CellClassification(
                cell=cell,
                verdict=Verdict.CRIMINAL,
                queries=(q1,),
                primary_var=var,
            )

        # Query 2: assume C_i
        res_pos = solve_dpll(kb.formula, assumptions=(var,))
        q2 = SatQueryRecord(assumptions=(var,), is_sat=res_pos.is_sat, metrics=res_pos.metrics)

        if not res_pos.is_sat:
            return CellClassification(
                cell=cell,
                verdict=Verdict.INNOCENT,
                queries=(q1, q2),
                primary_var=var,
            )

        return CellClassification(
            cell=cell,
            verdict=Verdict.UNKNOWN,
            queries=(q1, q2),
            primary_var=var,
        )


class LogicAgent:
    """Public deductive agent holding only a PublicState snapshot.

    Has no access to GameEngine, private Puzzle, hidden solution, or unrevealed clues.
    """

    def __init__(self, public_state: PublicState) -> None:
        """Initialize the agent with an immutable PublicState snapshot."""
        if not isinstance(public_state, PublicState):
            raise TypeError(
                f"LogicAgent requires PublicState, got {type(public_state).__name__}"
            )
        self._state: PublicState = public_state

    @property
    def public_state(self) -> PublicState:
        """Current public state snapshot."""
        return self._state

    def classify_all(self) -> ProofReport:
        """Classify all unresolved cards using the public proof service."""
        return ProofService.classify_state(self._state)

    def classify_cell(self, cell: CellId) -> CellClassification:
        """Classify a single cell using the public proof service."""
        return ProofService.classify_cell(self._state, cell)

    def hint(self) -> CellClassification | None:
        """Find the first logically forced unresolved card in deterministic row-major order, or None."""
        report = self.classify_all()
        return report.first_forced_cell
