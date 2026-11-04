"""Unit tests for independent clue semantics."""

import ast
import inspect
from pathlib import Path

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
from griductive.domain.semantics import (
    evaluate_clue,
    validate_all_clues,
    validate_complete_assignment,
)


@pytest.fixture
def sample_3x3_assignment() -> dict[CellId, Status]:
    """Sample complete 3x3 assignment:
    Row 1: A1=CRIMINAL, B1=INNOCENT, C1=CRIMINAL  (2 criminals)
    Row 2: A2=INNOCENT, B2=CRIMINAL, C2=INNOCENT  (1 criminal)
    Row 3: A3=CRIMINAL, B3=INNOCENT, C3=INNOCENT  (1 criminal)
    """
    return {
        CellId("A1"): Status.CRIMINAL,
        CellId("B1"): Status.INNOCENT,
        CellId("C1"): Status.CRIMINAL,
        CellId("A2"): Status.INNOCENT,
        CellId("B2"): Status.CRIMINAL,
        CellId("C2"): Status.INNOCENT,
        CellId("A3"): Status.CRIMINAL,
        CellId("B3"): Status.INNOCENT,
        CellId("C3"): Status.INNOCENT,
    }


class TestFactSemantics:
    def test_fact_true_and_false(self, sample_3x3_assignment: dict[CellId, Status]) -> None:
        # A1 is CRIMINAL
        true_clue = FactClue("f1", CellId("A1"), CellId("A1"), Status.CRIMINAL)
        false_clue = FactClue("f2", CellId("A1"), CellId("A1"), Status.INNOCENT)
        assert evaluate_clue(true_clue, sample_3x3_assignment, 3) is True
        assert evaluate_clue(false_clue, sample_3x3_assignment, 3) is False

        # B1 is INNOCENT
        true_b1 = FactClue("f3", CellId("B1"), CellId("B1"), Status.INNOCENT)
        false_b1 = FactClue("f4", CellId("B1"), CellId("B1"), Status.CRIMINAL)
        assert evaluate_clue(true_b1, sample_3x3_assignment, 3) is True
        assert evaluate_clue(false_b1, sample_3x3_assignment, 3) is False

    def test_fact_with_boolean_assignment(self) -> None:
        bool_map = {
            CellId("A1"): True,
            CellId("B1"): False,
            CellId("A2"): False,
            CellId("B2"): True,
        }
        clue_crim = FactClue("f1", CellId("A1"), CellId("A1"), Status.CRIMINAL)
        clue_inno = FactClue("f2", CellId("A1"), CellId("A2"), Status.INNOCENT)
        assert evaluate_clue(clue_crim, bool_map, 2) is True
        assert evaluate_clue(clue_inno, bool_map, 2) is True



class TestSameAndDifferentSemantics:
    def test_same_clue(self, sample_3x3_assignment: dict[CellId, Status]) -> None:
        # A1 (CRIMINAL) and C1 (CRIMINAL) -> SAME is True
        assert evaluate_clue(
            SameClue("s1", CellId("A1"), CellId("A1"), CellId("C1")),
            sample_3x3_assignment,
            3,
        ) is True

        # B1 (INNOCENT) and C2 (INNOCENT) -> SAME is True
        assert evaluate_clue(
            SameClue("s2", CellId("A1"), CellId("B1"), CellId("C2")),
            sample_3x3_assignment,
            3,
        ) is True

        # A1 (CRIMINAL) and B1 (INNOCENT) -> SAME is False
        assert evaluate_clue(
            SameClue("s3", CellId("A1"), CellId("A1"), CellId("B1")),
            sample_3x3_assignment,
            3,
        ) is False

    def test_different_clue(self, sample_3x3_assignment: dict[CellId, Status]) -> None:
        # A1 (CRIMINAL) and B1 (INNOCENT) -> DIFFERENT is True
        assert evaluate_clue(
            DifferentClue("d1", CellId("A1"), CellId("A1"), CellId("B1")),
            sample_3x3_assignment,
            3,
        ) is True

        # A1 (CRIMINAL) and C1 (CRIMINAL) -> DIFFERENT is False
        assert evaluate_clue(
            DifferentClue("d2", CellId("A1"), CellId("A1"), CellId("C1")),
            sample_3x3_assignment,
            3,
        ) is False


class TestCardinalitySemantics:
    def test_exactly_row(self, sample_3x3_assignment: dict[CellId, Status]) -> None:
        # Row 1 has A1(C), B1(I), C1(C) -> exactly 2 criminals
        assert evaluate_clue(ExactlyClue("e1", CellId("A1"), 2, RowRegion(1)), sample_3x3_assignment, 3) is True
        assert evaluate_clue(ExactlyClue("e2", CellId("A1"), 1, RowRegion(1)), sample_3x3_assignment, 3) is False
        assert evaluate_clue(ExactlyClue("e3", CellId("A1"), 0, RowRegion(1)), sample_3x3_assignment, 3) is False

    def test_at_least_col(self, sample_3x3_assignment: dict[CellId, Status]) -> None:
        # Col A has A1(C), A2(I), A3(C) -> 2 criminals
        assert evaluate_clue(AtLeastClue("al1", CellId("A1"), 2, ColRegion("A")), sample_3x3_assignment, 3) is True
        assert evaluate_clue(AtLeastClue("al2", CellId("A1"), 1, ColRegion("A")), sample_3x3_assignment, 3) is True
        assert evaluate_clue(AtLeastClue("al3", CellId("A1"), 0, ColRegion("A")), sample_3x3_assignment, 3) is True
        assert evaluate_clue(AtLeastClue("al4", CellId("A1"), 3, ColRegion("A")), sample_3x3_assignment, 3) is False

    def test_at_most_neighbors(self, sample_3x3_assignment: dict[CellId, Status]) -> None:
        # Neighbors of A1 (corner: B1(I), A2(I), B2(C)) -> 1 criminal
        assert evaluate_clue(
            AtMostClue("am1", CellId("A1"), 1, NeighborsRegion(CellId("A1"))),
            sample_3x3_assignment,
            3,
        ) is True
        assert evaluate_clue(
            AtMostClue("am2", CellId("A1"), 2, NeighborsRegion(CellId("A1"))),
            sample_3x3_assignment,
            3,
        ) is True
        assert evaluate_clue(
            AtMostClue("am3", CellId("A1"), 0, NeighborsRegion(CellId("A1"))),
            sample_3x3_assignment,
            3,
        ) is False

    def test_cardinality_boundary_k(self, sample_3x3_assignment: dict[CellId, Status]) -> None:
        region = RowRegion(1)  # size 3
        # Valid bounds 0..3
        assert evaluate_clue(AtLeastClue("b1", CellId("A1"), 0, region), sample_3x3_assignment, 3) is True
        assert evaluate_clue(AtMostClue("b2", CellId("A1"), 3, region), sample_3x3_assignment, 3) is True

        # Out of bounds: k < 0
        with pytest.raises(ValueError, match="out of bounds"):
            evaluate_clue(ExactlyClue("err1", CellId("A1"), -1, region), sample_3x3_assignment, 3)

        # Out of bounds: k > |region| (k=4 > 3)
        with pytest.raises(ValueError, match="out of bounds"):
            evaluate_clue(ExactlyClue("err2", CellId("A1"), 4, region), sample_3x3_assignment, 3)


class TestExtensionSemantics:
    def test_parity_clue(self, sample_3x3_assignment: dict[CellId, Status]) -> None:
        # Row 1 has 2 criminals (EVEN)
        assert evaluate_clue(ParityClue("p1", CellId("A1"), Parity.EVEN, RowRegion(1)), sample_3x3_assignment, 3) is True
        assert evaluate_clue(ParityClue("p2", CellId("A1"), Parity.ODD, RowRegion(1)), sample_3x3_assignment, 3) is False

        # Row 2 has 1 criminal (ODD)
        assert evaluate_clue(ParityClue("p3", CellId("A1"), Parity.ODD, RowRegion(2)), sample_3x3_assignment, 3) is True
        assert evaluate_clue(ParityClue("p4", CellId("A1"), Parity.EVEN, RowRegion(2)), sample_3x3_assignment, 3) is False

    def test_common_neighbors_extension(self, sample_3x3_assignment: dict[CellId, Status]) -> None:
        # In 3x3: Common neighbors of A1 and C3 is B2.
        # B2 is CRIMINAL in sample assignment (count = 1).
        cn_region = CommonNeighborsRegion(CellId("A1"), CellId("C3"))

        assert evaluate_clue(ExactlyClue("c1", CellId("A1"), 1, cn_region), sample_3x3_assignment, 3) is True
        assert evaluate_clue(ExactlyClue("c2", CellId("A1"), 0, cn_region), sample_3x3_assignment, 3) is False
        assert evaluate_clue(ParityClue("c3", CellId("A1"), Parity.ODD, cn_region), sample_3x3_assignment, 3) is True
        assert evaluate_clue(ParityClue("c4", CellId("A1"), Parity.EVEN, cn_region), sample_3x3_assignment, 3) is False

    def test_empty_common_neighbors_region(self) -> None:
        # In 4x4: A1 and D4 share 0 common neighbors (region size = 0).
        cn_empty = CommonNeighborsRegion(CellId("A1"), CellId("D4"))
        dummy_assignment = {CellId.from_index(i, 4): Status.INNOCENT for i in range(16)}

        # Count is 0
        assert evaluate_clue(ExactlyClue("e0", CellId("A1"), 0, cn_empty), dummy_assignment, 4) is True
        assert evaluate_clue(AtMostClue("m0", CellId("A1"), 0, cn_empty), dummy_assignment, 4) is True
        # 0 is even
        assert evaluate_clue(ParityClue("p0", CellId("A1"), Parity.EVEN, cn_empty), dummy_assignment, 4) is True
        assert evaluate_clue(ParityClue("p1", CellId("A1"), Parity.ODD, cn_empty), dummy_assignment, 4) is False


class TestValidationAndIsolation:
    def test_validate_all_clues(self, sample_3x3_assignment: dict[CellId, Status]) -> None:
        true_clues = [
            FactClue("c1", CellId("A1"), CellId("A1"), Status.CRIMINAL),
            SameClue("c2", CellId("B1"), CellId("B1"), CellId("C2")),
            ExactlyClue("c3", CellId("C1"), 2, RowRegion(1)),
            ParityClue("c4", CellId("A2"), Parity.EVEN, RowRegion(1)),
        ]
        assert validate_all_clues(true_clues, sample_3x3_assignment, 3) is True

        false_clues = list(true_clues) + [FactClue("bad", CellId("A3"), CellId("A1"), Status.INNOCENT)]
        assert validate_all_clues(false_clues, sample_3x3_assignment, 3) is False

    def test_missing_cell_raises_key_error(self) -> None:
        partial_map = {CellId("A1"): Status.CRIMINAL}
        clue = SameClue("s", CellId("A1"), CellId("A1"), CellId("B1"))
        with pytest.raises(KeyError, match="missing from complete assignment"):
            evaluate_clue(clue, partial_map, 3)

    def test_semantics_module_does_not_import_cnf_or_dpll(self) -> None:
        """Strict acceptance check: semantics.py must NOT import cnf or dpll."""
        import griductive.domain.semantics as sem_mod

        src_path = Path(inspect.getfile(sem_mod))
        tree = ast.parse(src_path.read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "cnf" not in alias.name.lower()
                    assert "dpll" not in alias.name.lower()
                    assert "sat" not in alias.name.lower()
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert "cnf" not in node.module.lower()
                    assert "dpll" not in node.module.lower()
                    assert "sat" not in node.module.lower()

    @pytest.mark.parametrize("bad_val", [1, 0, "CRIMINAL", "INNOCENT", None, 1.0, [True]])
    def test_invalid_assignment_value_type(
        self, sample_3x3_assignment: dict[CellId, Status], bad_val: object
    ) -> None:
        bad_map = dict(sample_3x3_assignment)
        bad_map[CellId("A1")] = bad_val  # type: ignore[assignment]
        clue = FactClue("f", CellId("A1"), CellId("A1"), Status.CRIMINAL)
        with pytest.raises(TypeError, match="Invalid assignment value type"):
            evaluate_clue(clue, bad_map, 3)

    @pytest.mark.parametrize("bad_k", [1.0, True, False, "2", None])
    def test_cardinality_k_type_validation(
        self, sample_3x3_assignment: dict[CellId, Status], bad_k: object
    ) -> None:
        clue = ExactlyClue("err", CellId("A1"), bad_k, RowRegion(1))  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="Cardinality k must be an integer"):
            evaluate_clue(clue, sample_3x3_assignment, 3)

    def test_incomplete_assignment_missing_cell_row_major_order(
        self, sample_3x3_assignment: dict[CellId, Status]
    ) -> None:
        partial_map = dict(sample_3x3_assignment)
        del partial_map[CellId("B1")]
        clue = FactClue("f", CellId("A1"), CellId("A1"), Status.CRIMINAL)
        with pytest.raises(KeyError, match=r"Cell B1 is missing from complete assignment"):
            evaluate_clue(clue, partial_map, 3)

        del partial_map[CellId("A1")]
        with pytest.raises(KeyError, match=r"Cell A1 is missing from complete assignment"):
            evaluate_clue(clue, partial_map, 3)

    def test_assignment_with_extra_cells_raises_value_error(
        self, sample_3x3_assignment: dict[CellId, Status]
    ) -> None:
        extra_map = dict(sample_3x3_assignment)
        extra_map[CellId("D1")] = Status.INNOCENT
        clue = FactClue("f", CellId("A1"), CellId("A1"), Status.CRIMINAL)
        with pytest.raises(ValueError, match="out-of-bounds cell"):
            evaluate_clue(clue, extra_map, 3)

    def test_validate_complete_assignment_invalid_grid_size(
        self, sample_3x3_assignment: dict[CellId, Status]
    ) -> None:
        with pytest.raises(ValueError, match="grid_size must be >= 1"):
            validate_complete_assignment(sample_3x3_assignment, 0)


