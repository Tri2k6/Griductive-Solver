"""Independent semantic evaluators for Griductive clue templates.

Inspects complete status assignments directly without using CNF or SAT solvers.
Used for offline puzzle validation, ground truth verification, and encoding tests.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from griductive.domain.model import (
    AtLeastClue,
    AtMostClue,
    CellId,
    Clue,
    DifferentClue,
    ExactlyClue,
    FactClue,
    Parity,
    ParityClue,
    SameClue,
    Status,
)
from griductive.domain.regions import resolve_region


def _get_is_criminal(
    cell: CellId, assignment: Mapping[CellId, Status | bool]
) -> bool:
    """Return True if cell is Criminal, False if Innocent."""
    if cell not in assignment:
        raise KeyError(f"Cell {cell} is missing from complete assignment")
    val = assignment[cell]
    if isinstance(val, Status):
        return val == Status.CRIMINAL
    if isinstance(val, bool):
        return val
    raise TypeError(
        f"Invalid assignment value type for cell {cell}: {type(val).__name__} ({val!r}). Expected Status or bool."
    )



def evaluate_fact(
    clue: FactClue, assignment: Mapping[CellId, Status | bool]
) -> bool:
    """Evaluate FACT(person, status): Target has the specified status."""
    return _get_is_criminal(clue.target, assignment) == clue.status.to_bool()


def evaluate_same(
    clue: SameClue, assignment: Mapping[CellId, Status | bool]
) -> bool:
    """Evaluate SAME(person_a, person_b): Both people have identical status."""
    return _get_is_criminal(clue.person_a, assignment) == _get_is_criminal(
        clue.person_b, assignment
    )


def evaluate_different(
    clue: DifferentClue, assignment: Mapping[CellId, Status | bool]
) -> bool:
    """Evaluate DIFFERENT(person_a, person_b): The two have different statuses."""
    return _get_is_criminal(clue.person_a, assignment) != _get_is_criminal(
        clue.person_b, assignment
    )


def count_criminals_in_cells(
    cells: Iterable[CellId], assignment: Mapping[CellId, Status | bool]
) -> int:
    """Count how many cells in the given collection are Criminals."""
    return sum(1 for c in cells if _get_is_criminal(c, assignment))


def evaluate_cardinality(
    clue: ExactlyClue | AtLeastClue | AtMostClue,
    assignment: Mapping[CellId, Status | bool],
    grid_size: int,
) -> bool:
    """Evaluate EXACTLY, AT_LEAST, or AT_MOST against an assignment.

    Validates that k is an integer and 0 <= k <= |region|.
    """
    if isinstance(clue.k, bool) or not isinstance(clue.k, int):
        raise TypeError(
            f"Cardinality k must be an integer, got {type(clue.k).__name__}: {clue.k!r}"
        )
    region_cells = resolve_region(clue.region, grid_size)
    region_len = len(region_cells)

    if clue.k < 0 or clue.k > region_len:
        raise ValueError(
            f"k={clue.k} out of bounds for region of size {region_len} (0..{region_len})"
        )

    count = count_criminals_in_cells(region_cells, assignment)

    if isinstance(clue, ExactlyClue):
        return count == clue.k
    if isinstance(clue, AtLeastClue):
        return count >= clue.k
    if isinstance(clue, AtMostClue):
        return count <= clue.k

    raise TypeError(f"Expected cardinality clue, got {type(clue).__name__}")


def evaluate_parity(
    clue: ParityClue,
    assignment: Mapping[CellId, Status | bool],
    grid_size: int,
) -> bool:
    """Evaluate PARITY(region, EVEN|ODD): Criminals count has the given parity."""
    region_cells = resolve_region(clue.region, grid_size)
    count = count_criminals_in_cells(region_cells, assignment)

    if clue.parity == Parity.EVEN:
        return count % 2 == 0
    if clue.parity == Parity.ODD:
        return count % 2 == 1

    raise ValueError(f"Unknown parity value: {clue.parity!r}")


def validate_complete_assignment(
    assignment: Mapping[CellId, Status | bool],
    grid_size: int,
) -> None:
    """Validate that assignment is complete, within bounds, and contains only valid types."""
    if grid_size < 1:
        raise ValueError(f"grid_size must be >= 1: {grid_size}")

    for idx in range(grid_size * grid_size):
        expected_cell = CellId.from_index(idx, grid_size)
        if expected_cell not in assignment:
            raise KeyError(f"Cell {expected_cell} is missing from complete assignment")

    for cell in assignment.keys():
        if not isinstance(cell, CellId) or not cell.is_valid_for(grid_size):
            raise ValueError(f"Assignment contains invalid or out-of-bounds cell: {cell!r}")

    for cell, val in assignment.items():
        if isinstance(val, Status):
            continue
        if isinstance(val, bool):
            continue
        raise TypeError(
            f"Invalid assignment value type for cell {cell}: {type(val).__name__} ({val!r}). Expected Status or bool."
        )


def evaluate_clue(
    clue: Clue,
    assignment: Mapping[CellId, Status | bool],
    grid_size: int,
) -> bool:
    """Directly evaluate any Clue variant against a complete assignment.

    Returns True if the clue's statement is satisfied, False otherwise.
    Does NOT call or depend on any CNF encoder or DPLL solver.
    """
    validate_complete_assignment(assignment, grid_size)
    if isinstance(clue, FactClue):
        return evaluate_fact(clue, assignment)
    if isinstance(clue, SameClue):
        return evaluate_same(clue, assignment)
    if isinstance(clue, DifferentClue):
        return evaluate_different(clue, assignment)
    if isinstance(clue, (ExactlyClue, AtLeastClue, AtMostClue)):
        return evaluate_cardinality(clue, assignment, grid_size)
    if isinstance(clue, ParityClue):
        return evaluate_parity(clue, assignment, grid_size)

    raise TypeError(f"Unknown clue type: {type(clue).__name__}")



def validate_all_clues(
    clues: Iterable[Clue],
    assignment: Mapping[CellId, Status | bool],
    grid_size: int,
) -> bool:
    """Return True if all clues evaluate to True under the complete assignment."""
    return all(evaluate_clue(clue, assignment, grid_size) for clue in clues)

