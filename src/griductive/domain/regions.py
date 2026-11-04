"""Region resolution and clue highlighting for Griductive Solver."""

from __future__ import annotations

from typing import Mapping

from griductive.domain.model import (
    AtLeastClue,
    AtMostClue,
    CellId,
    Clue,
    ColRegion,
    CommonNeighborsRegion,
    DifferentClue,
    ExactlyClue,
    ExplicitRegion,
    FactClue,
    NeighborsRegion,
    ParityClue,
    RegionExpr,
    RowRegion,
    SameClue,
)


def resolve_region(region: RegionExpr, grid_size: int) -> tuple[CellId, ...]:
    """Resolve a RegionExpr into a deterministic, ordered tuple of distinct cells.

    Cells are ordered in row-major order (top-to-bottom, left-to-right).
    Raises ValueError on invalid bounds, bad coordinates, or duplicate explicit cells.
    """
    if grid_size < 1:
        raise ValueError(f"grid_size must be >= 1: {grid_size}")

    if isinstance(region, RowRegion):
        if region.row < 1 or region.row > grid_size:
            raise ValueError(
                f"Row {region.row} out of bounds for grid_size {grid_size} (1..{grid_size})"
            )
        return tuple(
            CellId.from_coords(region.row, col_idx)
            for col_idx in range(1, grid_size + 1)
        )

    if isinstance(region, ColRegion):
        col_str = region.col.strip().upper()
        if not col_str.isalpha() or len(col_str) != 1:
            raise ValueError(f"Invalid column format: {region.col!r}")
        col_idx = ord(col_str) - ord("A") + 1
        if col_idx < 1 or col_idx > grid_size:
            raise ValueError(
                f"Column {region.col!r} out of bounds for grid_size {grid_size}"
            )
        return tuple(
            CellId.from_coords(row, col_idx)
            for row in range(1, grid_size + 1)
        )

    if isinstance(region, NeighborsRegion):
        center = region.center
        if not center.is_valid_for(grid_size):
            raise ValueError(
                f"Center cell {center} is out of bounds for grid_size {grid_size}"
            )
        neighbors: list[CellId] = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue  # The cell itself is strictly excluded
                nr = center.row + dr
                nc = center.col_idx + dc
                if 1 <= nr <= grid_size and 1 <= nc <= grid_size:
                    neighbors.append(CellId.from_coords(nr, nc))
        return tuple(sorted(neighbors))

    if isinstance(region, ExplicitRegion):
        if not region.cells:
            raise ValueError("ExplicitRegion must contain at least one cell")
        seen: set[CellId] = set()
        for cell in region.cells:
            if not cell.is_valid_for(grid_size):
                raise ValueError(
                    f"Cell {cell} in ExplicitRegion out of bounds for grid_size {grid_size}"
                )
            if cell in seen:
                raise ValueError(
                    f"ExplicitRegion contains duplicate cell: {cell}"
                )
            seen.add(cell)
        return tuple(sorted(region.cells))

    if isinstance(region, CommonNeighborsRegion):
        a = region.cell_a
        b = region.cell_b
        if not a.is_valid_for(grid_size):
            raise ValueError(
                f"Cell {a} in CommonNeighborsRegion out of bounds for grid_size {grid_size}"
            )
        if not b.is_valid_for(grid_size):
            raise ValueError(
                f"Cell {b} in CommonNeighborsRegion out of bounds for grid_size {grid_size}"
            )
        if a == b:
            raise ValueError(
                f"CommonNeighborsRegion requires two distinct cells, got {a} twice"
            )
        neighbors_a = set(resolve_region(NeighborsRegion(a), grid_size))
        neighbors_b = set(resolve_region(NeighborsRegion(b), grid_size))
        common = neighbors_a & neighbors_b
        return tuple(sorted(common))

    raise TypeError(f"Unknown region type: {type(region).__name__}")


def get_clue_highlight_cells(
    clue: Clue,
    grid_size: int,
    char_name_to_cell: Mapping[str, CellId] | None = None,
) -> tuple[CellId, ...]:
    """Return all cells referenced or counted by a clue, in row-major order.

    Used by the GUI to visually highlight related cards when a clue is selected.
    """
    if isinstance(clue, FactClue):
        return (clue.target,)

    if isinstance(clue, (SameClue, DifferentClue)):
        return tuple(sorted({clue.person_a, clue.person_b}))

    if isinstance(clue, (ExactlyClue, AtLeastClue, AtMostClue, ParityClue)):
        return resolve_region(clue.region, grid_size)

    raise TypeError(f"Unknown clue type: {type(clue).__name__}")

