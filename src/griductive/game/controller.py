"""Game controller coordinating gameplay, manual verdict calls, hints, and auto-solve."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from griductive.domain.model import (
    AtLeastClue,
    AtMostClue,
    CellId,
    Clue,
    DifferentClue,
    ExactlyClue,
    FactClue,
    ParityClue,
    PublicState,
    Puzzle,
    SameClue,
    Status,
)
from griductive.solver.cnf import (
    AuxAllocator,
    CNFFormula,
    PrimaryVarMap,
    encode_at_least,
    encode_at_most,
    encode_different,
    encode_exactly,
    encode_fact,
    encode_known_status,
    encode_parity,
    encode_same,
)
from griductive.solver.dpll import DpllMetrics, solve_dpll
from griductive.solver.logic import (
    CellClassification,
    LogicAgent,
    ProofReport,
    ProofService,
    SatQueryRecord,
    Verdict,
)
from griductive.game.engine import GameEngine


class RejectionReason(str, Enum):
    """Reason why a manual verdict call was rejected."""

    NOT_PROVABLE = "NOT_PROVABLE"          # Verdict is not logically forced (both statuses possible / UNKNOWN)
    CONTRADICTED = "CONTRADICTED"          # Opposite verdict is logically forced by public KB
    INCONSISTENT = "INCONSISTENT"          # Base public knowledge base is unsatisfiable
    ALREADY_REVEALED = "ALREADY_REVEALED"  # Target cell has already been revealed
    INVALID_CELL = "INVALID_CELL"          # Coordinate is malformed or out of bounds


class AutoSolveStatus(str, Enum):
    """Termination status of the auto-solve deduction loop."""

    SOLVED = "SOLVED"                      # All characters on the board have been revealed
    STALLED = "STALLED"                    # No unresolved characters are logically forced without guessing
    INCONSISTENT = "INCONSISTENT"          # The public knowledge base is unsatisfiable
    ALREADY_SOLVED = "ALREADY_SOLVED"      # Already solved prior to loop execution
    STEP_LIMIT_REACHED = "STEP_LIMIT_REACHED"  # Deduction halted because max_steps was reached


@dataclass(frozen=True)
class CallResult:
    """Outcome of a manual verdict call."""

    accepted: bool
    cell: CellId | None
    proposed_status: Status | None
    rejection_reason: RejectionReason | None = None
    classification: CellClassification | None = None
    revealed_status: Status | None = None
    revealed_clue: Clue | None = None
    state_revision: int = 0
    message: str = ""

    def __bool__(self) -> bool:
        return self.accepted


@dataclass(frozen=True)
class DeductionStep:
    """Record of a single deduction step in the reveal loop."""

    step_number: int
    active_clue_ids: tuple[str, ...]
    target_cell: CellId
    target_verdict: Status
    classification: CellClassification
    revealed_status: Status
    revealed_clue: Clue
    revealed_clue_id: str
    step_metrics: DpllMetrics
    state_revision_before: int
    state_revision_after: int
    base_query: SatQueryRecord | None = None
    all_queries: tuple[SatQueryRecord, ...] = ()
    step_sat_calls: int = 0
    all_classifications: Mapping[CellId, CellClassification] | None = None


@dataclass(frozen=True)
class AutoSolveReport:
    """Complete summary of an auto-solve run."""

    status: AutoSolveStatus
    steps: tuple[DeductionStep, ...]
    total_steps: int
    total_sat_calls: int
    aggregate_metrics: DpllMetrics
    final_public_state: PublicState
    message: str
    terminal_sat_calls: int = 0
    terminal_metrics: DpllMetrics | None = None


@dataclass(frozen=True)
class Hint:
    """Non-mutating guidance derived from current public state."""

    has_forced_cell: bool
    cell: CellId | None
    verdict: Status | None
    classification: CellClassification | None
    relevant_clue_ids: tuple[str, ...]
    base_consistent: bool
    message: str


def find_relevant_clue_ids(
    state: PublicState,
    cell: CellId,
    verdict: Verdict,
) -> tuple[str, ...]:
    """Return a sufficient, deletion-minimal set of public clue IDs.

    Remove a clue only if the remaining clues plus known statuses still prove
    the verdict by UNSAT under its opposite. This handles redundant evidence
    without selecting a clue merely because it mentions the target. Several
    highlighted clues may be needed together; none is claimed sufficient alone.
    """
    if not state.revealed_clues:
        return ()

    pmap = PrimaryVarMap(state.grid_size)
    var = pmap.cell_to_var(cell)

    removed: set[str] = set()
    for omitted_clue in state.revealed_clues:
        aux = AuxAllocator(pmap)
        clauses: list[tuple[int, ...]] = []
        for c in sorted(state.known_statuses.keys()):
            clauses.extend(encode_known_status(c, state.known_statuses[c], pmap))

        for clue in state.revealed_clues:
            if clue.clue_id == omitted_clue.clue_id or clue.clue_id in removed:
                continue
            if isinstance(clue, FactClue):
                clauses.extend(encode_fact(clue, pmap, aux))
            elif isinstance(clue, SameClue):
                clauses.extend(encode_same(clue, pmap, aux))
            elif isinstance(clue, DifferentClue):
                clauses.extend(encode_different(clue, pmap, aux))
            elif isinstance(clue, AtMostClue):
                clauses.extend(encode_at_most(clue, pmap, aux, state.grid_size))
            elif isinstance(clue, AtLeastClue):
                clauses.extend(encode_at_least(clue, pmap, aux, state.grid_size))
            elif isinstance(clue, ExactlyClue):
                clauses.extend(encode_exactly(clue, pmap, aux, state.grid_size))
            elif isinstance(clue, ParityClue):
                clauses.extend(encode_parity(clue, pmap, aux, state.grid_size))

        formula = CNFFormula(clauses=tuple(clauses), primary_map=pmap, num_aux=aux.num_aux)
        opposite = -var if verdict == Verdict.CRIMINAL else var
        if not solve_dpll(formula, assumptions=(opposite,)).is_sat:
            removed.add(omitted_clue.clue_id)

    return tuple(c.clue_id for c in state.revealed_clues if c.clue_id not in removed)


class GameController:
    """Coordinates gameplay between GameEngine and public LogicAgent.

    Architectural guarantees:
    - Never uses private puzzle/hidden solution to decide whether a call is provable.
    - Sound verification: a call is accepted if and only if it is logically entailed
      by the current public knowledge base.
    - If neither status is forced -> rejects with NOT_PROVABLE.
    - If opposite status is forced -> rejects with CONTRADICTED.
    - If base KB is unsatisfiable -> rejects with INCONSISTENT.
    - If cell is already revealed -> rejects with ALREADY_REVEALED.
    - If cell is invalid -> rejects with INVALID_CELL.
    - On any rejection, neither engine state nor public state nor revision changes.
    - On acceptance, commits through the engine's private transition and returns
      the newly public clue/status. It never exposes the mutable engine.
    """

    def __init__(self, puzzle_or_engine: Puzzle | GameEngine) -> None:
        """Initialize controller with a private Puzzle or an existing GameEngine."""
        if isinstance(puzzle_or_engine, Puzzle):
            self._engine: GameEngine = GameEngine(puzzle_or_engine)
        elif isinstance(puzzle_or_engine, GameEngine):
            self._engine = puzzle_or_engine
        else:
            raise TypeError(
                f"Expected Puzzle or GameEngine, got {type(puzzle_or_engine).__name__}"
            )

    @property
    def public_state(self) -> PublicState:
        """Current immutable public game state snapshot."""
        return self._engine.public_state

    @property
    def revision(self) -> int:
        """Current monotonic state revision counter."""
        return self._engine.revision

    @property
    def is_solved(self) -> bool:
        """True if all characters in the puzzle have been revealed."""
        return self._engine.is_solved

    @property
    def grid_size(self) -> int:
        """Grid dimension N."""
        return self._engine.grid_size

    def restart(self) -> PublicState:
        """Reset the game back to its initial face-up state."""
        return self._engine.restart()

    def make_call(self, cell: CellId | str, verdict: Status | str) -> CallResult:
        """Attempt a manual verdict call for a cell.

        Verifies the call using sound public SAT entailment before revealing.
        Rejections preserve game state and revision.
        """
        # Normalize and validate cell
        if isinstance(cell, str):
            try:
                target_cell = CellId(cell)
            except ValueError:
                return CallResult(
                    accepted=False,
                    cell=None,
                    proposed_status=None,
                    rejection_reason=RejectionReason.INVALID_CELL,
                    state_revision=self.revision,
                    message=f"Invalid cell coordinate format: {cell!r}.",
                )
        elif isinstance(cell, CellId):
            target_cell = cell
        else:
            raise TypeError(f"cell must be CellId or str, got {type(cell).__name__}")

        if not target_cell.is_valid_for(self.grid_size):
            return CallResult(
                accepted=False,
                cell=target_cell,
                proposed_status=None,
                rejection_reason=RejectionReason.INVALID_CELL,
                state_revision=self.revision,
                message=f"Cell {target_cell} is out of bounds for grid size {self.grid_size}.",
            )

        # Normalize and validate proposed verdict
        if isinstance(verdict, str):
            try:
                target_status = Status(verdict.strip().upper())
            except ValueError:
                raise ValueError(
                    f"Invalid status verdict: {verdict!r}. Must be CRIMINAL or INNOCENT."
                )
        elif isinstance(verdict, Status):
            target_status = verdict
        else:
            raise TypeError(f"verdict must be Status or str, got {type(verdict).__name__}")

        # Check if already revealed
        if target_cell in self.public_state.revealed_cells:
            return CallResult(
                accepted=False,
                cell=target_cell,
                proposed_status=target_status,
                rejection_reason=RejectionReason.ALREADY_REVEALED,
                state_revision=self.revision,
                message=f"Cell {target_cell} has already been revealed.",
            )

        # Classify target cell using sound public entailment
        cls = ProofService.classify_cell(self.public_state, target_cell)

        # Handle inconsistent base KB
        if cls.verdict == Verdict.INCONSISTENT:
            return CallResult(
                accepted=False,
                cell=target_cell,
                proposed_status=target_status,
                rejection_reason=RejectionReason.INCONSISTENT,
                classification=cls,
                state_revision=self.revision,
                message="Public knowledge base is inconsistent; no calls can be accepted.",
            )

        # Handle ambiguous status
        if cls.verdict == Verdict.UNKNOWN:
            return CallResult(
                accepted=False,
                cell=target_cell,
                proposed_status=target_status,
                rejection_reason=RejectionReason.NOT_PROVABLE,
                classification=cls,
                state_revision=self.revision,
                message=f"Call for cell {target_cell} is NOT_PROVABLE under current public knowledge.",
            )

        # Handle forced CRIMINAL
        if cls.verdict == Verdict.CRIMINAL:
            if target_status == Status.CRIMINAL:
                try:
                    actual_status, clue = self._engine._reveal_proven(
                        target_cell, target_status
                    )
                except ValueError:
                    return CallResult(
                        accepted=False,
                        cell=target_cell,
                        proposed_status=target_status,
                        rejection_reason=RejectionReason.CONTRADICTED,
                        classification=cls,
                        state_revision=self.revision,
                        message=f"Call rejected: verdict for cell {target_cell} contradicts game engine state.",
                    )
                return CallResult(
                    accepted=True,
                    cell=target_cell,
                    proposed_status=target_status,
                    classification=cls,
                    revealed_status=actual_status,
                    revealed_clue=clue,
                    state_revision=self.revision,
                    message=f"Call accepted: cell {target_cell} is proven CRIMINAL.",
                )
            else:
                return CallResult(
                    accepted=False,
                    cell=target_cell,
                    proposed_status=target_status,
                    rejection_reason=RejectionReason.CONTRADICTED,
                    classification=cls,
                    state_revision=self.revision,
                    message=f"Call rejected: proposing {target_status.value} for cell {target_cell} is CONTRADICTED (cell is proven CRIMINAL).",
                )

        # Handle forced INNOCENT
        if cls.verdict == Verdict.INNOCENT:
            if target_status == Status.INNOCENT:
                try:
                    actual_status, clue = self._engine._reveal_proven(
                        target_cell, target_status
                    )
                except ValueError:
                    return CallResult(
                        accepted=False,
                        cell=target_cell,
                        proposed_status=target_status,
                        rejection_reason=RejectionReason.CONTRADICTED,
                        classification=cls,
                        state_revision=self.revision,
                        message=f"Call rejected: verdict for cell {target_cell} contradicts game engine state.",
                    )
                return CallResult(
                    accepted=True,
                    cell=target_cell,
                    proposed_status=target_status,
                    classification=cls,
                    revealed_status=actual_status,
                    revealed_clue=clue,
                    state_revision=self.revision,
                    message=f"Call accepted: cell {target_cell} is proven INNOCENT.",
                )
            else:
                return CallResult(
                    accepted=False,
                    cell=target_cell,
                    proposed_status=target_status,
                    rejection_reason=RejectionReason.CONTRADICTED,
                    classification=cls,
                    state_revision=self.revision,
                    message=f"Call rejected: proposing {target_status.value} for cell {target_cell} is CONTRADICTED (cell is proven INNOCENT).",
                )

        # Defensive fallback
        return CallResult(
            accepted=False,
            cell=target_cell,
            proposed_status=target_status,
            rejection_reason=RejectionReason.NOT_PROVABLE,
            classification=cls,
            state_revision=self.revision,
            message=f"Verdict for cell {target_cell} could not be proven.",
        )

    def step(self) -> DeductionStep | None:
        """Perform a single deterministic deduction step.

        Selects the first forced unresolved cell in row-major order, reveals it,
        and returns the recorded DeductionStep. If solved, stalled, or inconsistent,
        returns None without mutating state.
        """
        if self.is_solved:
            return None

        report = ProofService.classify_state(self.public_state)
        if not report.base_consistent or report.first_forced_cell is None:
            return None

        forced = report.first_forced_cell
        forced_status = (
            Status.CRIMINAL if forced.verdict == Verdict.CRIMINAL else Status.INNOCENT
        )

        active_clues = tuple(c.clue_id for c in self.public_state.revealed_clues)
        rev_before = self.revision
        try:
            revealed_status, revealed_clue = self._engine._reveal_proven(
                forced.cell, forced_status
            )
        except ValueError:
            return None
        rev_after = self.revision

        all_queries = (report.base_query,) + tuple(
            q for c in report.classifications.values() for q in c.queries
        )

        return DeductionStep(
            step_number=self.revision,
            active_clue_ids=active_clues,
            target_cell=forced.cell,
            target_verdict=forced_status,
            classification=forced,
            revealed_status=revealed_status,
            revealed_clue=revealed_clue,
            revealed_clue_id=revealed_clue.clue_id,
            step_metrics=report.aggregate_metrics,
            state_revision_before=rev_before,
            state_revision_after=rev_after,
            base_query=report.base_query,
            all_queries=all_queries,
            step_sat_calls=report.total_sat_calls,
            all_classifications=report.classifications,
        )

    def auto_solve(self, max_steps: int | None = None) -> AutoSolveReport:
        """Execute the no-guess deduction loop until SOLVED, STALLED, or INCONSISTENT.

        Never guesses or accesses hidden data. Always selects the first forced
        card in row-major order and rebuilds public KB after each reveal.
        """
        if self.is_solved:
            return AutoSolveReport(
                status=AutoSolveStatus.ALREADY_SOLVED,
                steps=(),
                total_steps=0,
                total_sat_calls=0,
                aggregate_metrics=DpllMetrics(0, 0, 0, 0.0),
                final_public_state=self.public_state,
                message="Puzzle is already completely solved.",
                terminal_sat_calls=0,
                terminal_metrics=DpllMetrics(0, 0, 0, 0.0),
            )

        if max_steps is not None and max_steps <= 0:
            return AutoSolveReport(
                status=AutoSolveStatus.STEP_LIMIT_REACHED,
                steps=(),
                total_steps=0,
                total_sat_calls=0,
                aggregate_metrics=DpllMetrics(0, 0, 0, 0.0),
                final_public_state=self.public_state,
                message=f"Auto-solve stopped: maximum step limit ({max_steps}) reached before executing any steps.",
                terminal_sat_calls=0,
                terminal_metrics=DpllMetrics(0, 0, 0, 0.0),
            )

        steps: list[DeductionStep] = []
        total_sat_calls = 0
        total_decisions = 0
        total_propagations = 0
        total_backtracks = 0
        total_runtime = 0.0
        step_counter = 0

        while not self.is_solved:
            if max_steps is not None and step_counter >= max_steps:
                return AutoSolveReport(
                    status=AutoSolveStatus.STEP_LIMIT_REACHED,
                    steps=tuple(steps),
                    total_steps=len(steps),
                    total_sat_calls=total_sat_calls,
                    aggregate_metrics=DpllMetrics(
                        decisions=total_decisions,
                        propagations=total_propagations,
                        backtracks=total_backtracks,
                        runtime=total_runtime,
                    ),
                    final_public_state=self.public_state,
                    message=f"Auto-solve stopped: maximum step limit ({max_steps}) reached.",
                    terminal_sat_calls=0,
                    terminal_metrics=DpllMetrics(0, 0, 0, 0.0),
                )

            report = ProofService.classify_state(self.public_state)

            if not report.base_consistent:
                total_sat_calls += report.total_sat_calls
                total_decisions += report.aggregate_metrics.decisions
                total_propagations += report.aggregate_metrics.propagations
                total_backtracks += report.aggregate_metrics.backtracks
                total_runtime += report.aggregate_metrics.runtime
                return AutoSolveReport(
                    status=AutoSolveStatus.INCONSISTENT,
                    steps=tuple(steps),
                    total_steps=len(steps),
                    total_sat_calls=total_sat_calls,
                    aggregate_metrics=DpllMetrics(
                        decisions=total_decisions,
                        propagations=total_propagations,
                        backtracks=total_backtracks,
                        runtime=total_runtime,
                    ),
                    final_public_state=self.public_state,
                    message="Deduction halted: public knowledge base is inconsistent.",
                    terminal_sat_calls=report.total_sat_calls,
                    terminal_metrics=report.aggregate_metrics,
                )

            if report.first_forced_cell is None:
                total_sat_calls += report.total_sat_calls
                total_decisions += report.aggregate_metrics.decisions
                total_propagations += report.aggregate_metrics.propagations
                total_backtracks += report.aggregate_metrics.backtracks
                total_runtime += report.aggregate_metrics.runtime
                return AutoSolveReport(
                    status=AutoSolveStatus.STALLED,
                    steps=tuple(steps),
                    total_steps=len(steps),
                    total_sat_calls=total_sat_calls,
                    aggregate_metrics=DpllMetrics(
                        decisions=total_decisions,
                        propagations=total_propagations,
                        backtracks=total_backtracks,
                        runtime=total_runtime,
                    ),
                    final_public_state=self.public_state,
                    message="Deduction stalled: no character status is logically entailed without guessing.",
                    terminal_sat_calls=report.total_sat_calls,
                    terminal_metrics=report.aggregate_metrics,
                )

            forced = report.first_forced_cell
            forced_status = (
                Status.CRIMINAL if forced.verdict == Verdict.CRIMINAL else Status.INNOCENT
            )
            active_clues = tuple(c.clue_id for c in self.public_state.revealed_clues)
            rev_before = self.revision
            try:
                revealed_status, revealed_clue = self._engine._reveal_proven(
                    forced.cell, forced_status
                )
            except ValueError:
                total_sat_calls += report.total_sat_calls
                total_decisions += report.aggregate_metrics.decisions
                total_propagations += report.aggregate_metrics.propagations
                total_backtracks += report.aggregate_metrics.backtracks
                total_runtime += report.aggregate_metrics.runtime
                return AutoSolveReport(
                    status=AutoSolveStatus.INCONSISTENT,
                    steps=tuple(steps),
                    total_steps=len(steps),
                    total_sat_calls=total_sat_calls,
                    aggregate_metrics=DpllMetrics(
                        decisions=total_decisions,
                        propagations=total_propagations,
                        backtracks=total_backtracks,
                        runtime=total_runtime,
                    ),
                    final_public_state=self.public_state,
                    message=f"Deduction halted: deduced verdict for cell {forced.cell} contradicted engine state.",
                    terminal_sat_calls=report.total_sat_calls,
                    terminal_metrics=report.aggregate_metrics,
                )

            rev_after = self.revision

            total_sat_calls += report.total_sat_calls
            total_decisions += report.aggregate_metrics.decisions
            total_propagations += report.aggregate_metrics.propagations
            total_backtracks += report.aggregate_metrics.backtracks
            total_runtime += report.aggregate_metrics.runtime

            step_counter += 1
            all_queries = (report.base_query,) + tuple(
                q for c in report.classifications.values() for q in c.queries
            )

            step_record = DeductionStep(
                step_number=step_counter,
                active_clue_ids=active_clues,
                target_cell=forced.cell,
                target_verdict=forced_status,
                classification=forced,
                revealed_status=revealed_status,
                revealed_clue=revealed_clue,
                revealed_clue_id=revealed_clue.clue_id,
                step_metrics=report.aggregate_metrics,
                state_revision_before=rev_before,
                state_revision_after=rev_after,
                base_query=report.base_query,
                all_queries=all_queries,
                step_sat_calls=report.total_sat_calls,
                all_classifications=report.classifications,
            )
            steps.append(step_record)

            if self.is_solved:
                return AutoSolveReport(
                    status=AutoSolveStatus.SOLVED,
                    steps=tuple(steps),
                    total_steps=len(steps),
                    total_sat_calls=total_sat_calls,
                    aggregate_metrics=DpllMetrics(
                        decisions=total_decisions,
                        propagations=total_propagations,
                        backtracks=total_backtracks,
                        runtime=total_runtime,
                    ),
                    final_public_state=self.public_state,
                    message=f"Puzzle solved successfully in {len(steps)} steps without guessing.",
                    terminal_sat_calls=0,
                    terminal_metrics=DpllMetrics(0, 0, 0, 0.0),
                )

            if max_steps is not None and step_counter >= max_steps:
                return AutoSolveReport(
                    status=AutoSolveStatus.STEP_LIMIT_REACHED,
                    steps=tuple(steps),
                    total_steps=len(steps),
                    total_sat_calls=total_sat_calls,
                    aggregate_metrics=DpllMetrics(
                        decisions=total_decisions,
                        propagations=total_propagations,
                        backtracks=total_backtracks,
                        runtime=total_runtime,
                    ),
                    final_public_state=self.public_state,
                    message=f"Auto-solve stopped: maximum step limit ({max_steps}) reached.",
                    terminal_sat_calls=0,
                    terminal_metrics=DpllMetrics(0, 0, 0, 0.0),
                )

        final_status = (
            AutoSolveStatus.SOLVED if self.is_solved else AutoSolveStatus.STALLED
        )
        msg = (
            f"Puzzle solved successfully in {len(steps)} steps without guessing."
            if self.is_solved
            else f"Auto-solve stopped after {len(steps)} steps."
        )

        return AutoSolveReport(
            status=final_status,
            steps=tuple(steps),
            total_steps=len(steps),
            total_sat_calls=total_sat_calls,
            aggregate_metrics=DpllMetrics(
                decisions=total_decisions,
                propagations=total_propagations,
                backtracks=total_backtracks,
                runtime=total_runtime,
            ),
            final_public_state=self.public_state,
            message=msg,
            terminal_sat_calls=0,
            terminal_metrics=DpllMetrics(0, 0, 0, 0.0),
        )

    def hint(self) -> Hint:
        """Derive a hint identifying a provable card without mutating game state."""
        if self.is_solved:
            return Hint(
                has_forced_cell=False,
                cell=None,
                verdict=None,
                classification=None,
                relevant_clue_ids=(),
                base_consistent=True,
                message="Puzzle is already completely solved.",
            )

        report = ProofService.classify_state(self.public_state)
        if not report.base_consistent:
            return Hint(
                has_forced_cell=False,
                cell=None,
                verdict=None,
                classification=None,
                relevant_clue_ids=(),
                base_consistent=False,
                message="Public knowledge base is inconsistent; no sound hint available.",
            )

        if report.first_forced_cell is None:
            return Hint(
                has_forced_cell=False,
                cell=None,
                verdict=None,
                classification=None,
                relevant_clue_ids=(),
                base_consistent=True,
                message="No character status can be proven from current public knowledge without guessing.",
            )

        forced = report.first_forced_cell
        forced_status = (
            Status.CRIMINAL if forced.verdict == Verdict.CRIMINAL else Status.INNOCENT
        )
        relevant_clues = find_relevant_clue_ids(
            self.public_state, forced.cell, forced.verdict
        )

        msg = f"Cell {forced.cell} is logically forced to be {forced_status.value}."
        if relevant_clues:
            msg += f" Relevant clue(s): {', '.join(relevant_clues)}."

        return Hint(
            has_forced_cell=True,
            cell=forced.cell,
            verdict=forced_status,
            classification=forced,
            relevant_clue_ids=relevant_clues,
            base_consistent=True,
            message=msg,
        )
