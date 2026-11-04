"""Unit tests for region resolution and highlighting."""

import pytest
from griductive.domain.model import (
    AtLeastClue,
    AtMostClue,
    CellId,
    ColRegion,
    CommonNeighborsRegion,
    DifferentClue,
    ExactlyClue,
    ExplicitRegion,
    FactClue,
    NeighborsRegion,
    Parity,
    ParityClue,
    RowRegion,
    SameClue,
    Status,
)
from griductive.domain.regions import get_clue_highlight_cells, resolve_region


class TestRowAndColRegions:
    def test_row_region_3x3(self) -> None:
        cells = resolve_region(RowRegion(1), 3)
        assert cells == (CellId("A1"), CellId("B1"), CellId("C1"))

        cells = resolve_region(RowRegion(3), 3)
        assert cells == (CellId("A3"), CellId("B3"), CellId("C3"))

    def test_row_region_out_of_bounds(self) -> None:
        with pytest.raises(ValueError, match="Row 0 out of bounds"):
            resolve_region(RowRegion(0), 3)
        with pytest.raises(ValueError, match="Row 4 out of bounds"):
            resolve_region(RowRegion(4), 3)

    def test_col_region_3x3(self) -> None:
        cells = resolve_region(ColRegion("B"), 3)
        assert cells == (CellId("B1"), CellId("B2"), CellId("B3"))

    def test_col_region_out_of_bounds(self) -> None:
        with pytest.raises(ValueError, match="Column 'D' out of bounds"):
            resolve_region(ColRegion("D"), 3)


class TestNeighborsRegion:
    def test_interior_cell_8_neighbors(self) -> None:
        # B2 in 3x3 grid has all 8 surrounding cells
        neighbors = resolve_region(NeighborsRegion(CellId("B2")), 3)
        expected = (
            CellId("A1"),
            CellId("B1"),
            CellId("C1"),
            CellId("A2"),
            CellId("C2"),
            CellId("A3"),
            CellId("B3"),
            CellId("C3"),
        )
        assert neighbors == expected
        assert CellId("B2") not in neighbors  # self is strictly excluded

    def test_corner_cell_3_neighbors(self) -> None:
        # A1 top-left corner
        a1_neighbors = resolve_region(NeighborsRegion(CellId("A1")), 3)
        assert a1_neighbors == (CellId("B1"), CellId("A2"), CellId("B2"))
        assert CellId("A1") not in a1_neighbors

        # C3 bottom-right corner
        c3_neighbors = resolve_region(NeighborsRegion(CellId("C3")), 3)
        assert c3_neighbors == (CellId("B2"), CellId("C2"), CellId("B3"))
        assert CellId("C3") not in c3_neighbors

    def test_edge_cell_5_neighbors(self) -> None:
        # B1 top edge
        b1_neighbors = resolve_region(NeighborsRegion(CellId("B1")), 3)
        expected = (
            CellId("A1"),
            CellId("C1"),
            CellId("A2"),
            CellId("B2"),
            CellId("C2"),
        )
        assert b1_neighbors == expected
        assert CellId("B1") not in b1_neighbors

    def test_neighbors_out_of_bounds_center(self) -> None:
        with pytest.raises(ValueError, match="out of bounds"):
            resolve_region(NeighborsRegion(CellId("D1")), 3)


class TestExplicitRegion:
    def test_valid_explicit_region_sorted(self) -> None:
        cells = (CellId("C3"), CellId("A1"), CellId("B2"))
        resolved = resolve_region(ExplicitRegion(cells), 3)
        assert resolved == (CellId("A1"), CellId("B2"), CellId("C3"))

    def test_empty_explicit_region_fails(self) -> None:
        with pytest.raises(ValueError, match="at least one cell"):
            resolve_region(ExplicitRegion(()), 3)

    def test_duplicate_explicit_cells_fails(self) -> None:
        cells = (CellId("A1"), CellId("B2"), CellId("A1"))
        with pytest.raises(ValueError, match="duplicate cell"):
            resolve_region(ExplicitRegion(cells), 3)

    def test_explicit_cell_out_of_bounds_fails(self) -> None:
        cells = (CellId("A1"), CellId("D4"))
        with pytest.raises(ValueError, match="out of bounds"):
            resolve_region(ExplicitRegion(cells), 3)


class TestCommonNeighborsRegion:
    def test_opposite_corners_share_center(self) -> None:
        # In 3x3: A1 neighbors: {B1, A2, B2}. C3 neighbors: {B2, C2, B3}.
        # Common neighbor: B2.
        common = resolve_region(CommonNeighborsRegion(CellId("A1"), CellId("C3")), 3)
        assert common == (CellId("B2"),)

    def test_adjacent_corners_share_two_neighbors(self) -> None:
        # In 3x3: A1 and C1.
        # A1 neighbors: B1, A2, B2.
        # C1 neighbors: B1, B2, C2.
        # Common: B1, B2.
        common = resolve_region(CommonNeighborsRegion(CellId("A1"), CellId("C1")), 3)
        assert common == (CellId("B1"), CellId("B2"))

    def test_opposite_edges_share_middle_row(self) -> None:
        # B1 and B3 in 3x3.
        # B1 neighbors: A1, C1, A2, B2, C2.
        # B3 neighbors: A2, B2, C2, A3, C3.
        # Common: A2, B2, C2.
        common = resolve_region(CommonNeighborsRegion(CellId("B1"), CellId("B3")), 3)
        assert common == (CellId("A2"), CellId("B2"), CellId("C2"))

    def test_disjoint_common_neighbors_is_empty(self) -> None:
        # In 4x4: A1 and D4 share no common neighbors.
        common = resolve_region(CommonNeighborsRegion(CellId("A1"), CellId("D4")), 4)
        assert common == ()

    def test_identical_cells_fails(self) -> None:
        with pytest.raises(ValueError, match="requires two distinct cells"):
            resolve_region(CommonNeighborsRegion(CellId("A1"), CellId("A1")), 3)

    def test_out_of_bounds_cells_fails(self) -> None:
        with pytest.raises(ValueError, match="out of bounds"):
            resolve_region(CommonNeighborsRegion(CellId("A1"), CellId("E1")), 4)


class TestHighlightCells:
    def test_fact_clue_highlight(self) -> None:
        clue = FactClue("c1", CellId("A1"), CellId("B2"), Status.CRIMINAL)
        assert get_clue_highlight_cells(clue, 3) == (CellId("B2"),)

    def test_same_and_different_clue_highlight(self) -> None:
        same = SameClue("c2", CellId("A1"), CellId("C3"), CellId("A2"))
        assert get_clue_highlight_cells(same, 3) == (CellId("A2"), CellId("C3"))

        diff = DifferentClue("c3", CellId("A1"), CellId("B1"), CellId("A3"))
        assert get_clue_highlight_cells(diff, 3) == (CellId("B1"), CellId("A3"))

    def test_counting_and_parity_clue_highlight(self) -> None:
        ex = ExactlyClue("c4", CellId("A1"), 1, RowRegion(2))
        assert get_clue_highlight_cells(ex, 3) == (CellId("A2"), CellId("B2"), CellId("C2"))

        at_least = AtLeastClue("c5", CellId("A1"), 1, ColRegion("A"))
        assert get_clue_highlight_cells(at_least, 3) == (CellId("A1"), CellId("A2"), CellId("A3"))

        at_most = AtMostClue("c6", CellId("A1"), 2, NeighborsRegion(CellId("A1")))
        assert get_clue_highlight_cells(at_most, 3) == (CellId("B1"), CellId("A2"), CellId("B2"))

        parity = ParityClue("c7", CellId("A1"), Parity.EVEN, ExplicitRegion((CellId("C1"), CellId("B3"))))
        assert get_clue_highlight_cells(parity, 3) == (CellId("C1"), CellId("B3"))

