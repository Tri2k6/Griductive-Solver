"""Comprehensive unit tests for puzzle loading, schema validation, and semantics checks."""

import copy
import json
from pathlib import Path

import pytest

from griductive.game.io import (
    PUZZLE_SCHEMA_VERSION,
    load_puzzle_from_dict,
    load_puzzle_from_json,
    validate_puzzle_data,
)
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
    Puzzle,
    RowRegion,
    SameClue,
    Status,
)


@pytest.fixture
def valid_3x3_dict() -> dict:
    """Load valid 3x3 puzzle dictionary fixture."""
    fixture_path = Path("tests/fixtures/puzzle_3x3_valid.json")
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_puzzle_schema_version_constant():
    """Verify supported schema version constant."""
    assert PUZZLE_SCHEMA_VERSION == "1.0"


def test_load_valid_fixture_file():
    """Verify loading valid 3x3 fixture from path."""
    fixture_path = Path("tests/fixtures/puzzle_3x3_valid.json")
    puzzle = load_puzzle_from_json(fixture_path)

    assert isinstance(puzzle, Puzzle)
    assert puzzle.grid_size == 3
    assert len(puzzle.characters) == 9
    assert len(puzzle.solution) == 9
    assert len(puzzle.clues) == 9
    assert puzzle.initial_face_up == frozenset({CellId("A1"), CellId("B2")})

    # Validate specific clues
    c_a1 = puzzle.clues[CellId("A1")]
    assert isinstance(c_a1, FactClue)
    assert c_a1.target == CellId("B1")
    assert c_a1.target_name == "Bob"
    assert c_a1.status == Status.INNOCENT

    c_b1 = puzzle.clues[CellId("B1")]
    assert isinstance(c_b1, SameClue)
    assert c_b1.person_a == CellId("A2")
    assert c_b1.person_b == CellId("C2")

    c_c1 = puzzle.clues[CellId("C1")]
    assert isinstance(c_c1, DifferentClue)
    assert c_c1.person_a == CellId("A1")
    assert c_c1.person_b == CellId("B1")

    c_a2 = puzzle.clues[CellId("A2")]
    assert isinstance(c_a2, ExactlyClue)
    assert c_a2.k == 2
    assert isinstance(c_a2.region, RowRegion)
    assert c_a2.region.row == 1

    c_b2 = puzzle.clues[CellId("B2")]
    assert isinstance(c_b2, AtLeastClue)
    assert c_b2.k == 2
    assert isinstance(c_b2.region, NeighborsRegion)
    assert c_b2.region.center == CellId("B2")

    c_c2 = puzzle.clues[CellId("C2")]
    assert isinstance(c_c2, AtMostClue)
    assert c_c2.k == 1
    assert isinstance(c_c2.region, ColRegion)
    assert c_c2.region.col == "C"

    c_a3 = puzzle.clues[CellId("A3")]
    assert isinstance(c_a3, ParityClue)
    assert c_a3.parity == Parity.ODD
    assert isinstance(c_a3.region, RowRegion)

    c_b3 = puzzle.clues[CellId("B3")]
    assert isinstance(c_b3, ExactlyClue)
    assert c_b3.k == 1
    assert isinstance(c_b3.region, CommonNeighborsRegion)
    assert c_b3.region.cell_a == CellId("A1")
    assert c_b3.region.cell_b == CellId("C1")

    c_c3 = puzzle.clues[CellId("C3")]
    assert isinstance(c_c3, ExactlyClue)
    assert c_c3.k == 2
    assert isinstance(c_c3.region, ExplicitRegion)
    assert c_c3.region.cells == (CellId("A1"), CellId("A3"), CellId("C3"))


def test_load_from_json_string(valid_3x3_dict):
    """Verify loading from raw JSON string."""
    json_str = json.dumps(valid_3x3_dict)
    puzzle = load_puzzle_from_json(json_str)
    assert puzzle.grid_size == 3


def test_load_from_path_string():
    """Verify loading from string path."""
    puzzle = load_puzzle_from_json("tests/fixtures/puzzle_3x3_valid.json")
    assert puzzle.grid_size == 3


def test_validate_puzzle_data_success(valid_3x3_dict):
    """Verify validate_puzzle_data passes on valid puzzle dict."""
    res = validate_puzzle_data(valid_3x3_dict)
    assert res is None


def test_load_invalid_type_raises():
    """Verify non-dict raises TypeError."""
    with pytest.raises(TypeError, match="must be a dictionary"):
        load_puzzle_from_dict(["not", "a", "dict"])  # type: ignore

    with pytest.raises(TypeError, match="Expected str or Path"):
        load_puzzle_from_json(12345)  # type: ignore


def test_missing_or_invalid_schema_version(valid_3x3_dict):
    """Verify missing or unsupported schema version."""
    d = copy.deepcopy(valid_3x3_dict)
    del d["schema_version"]
    with pytest.raises(ValueError, match="Missing 'schema_version'"):
        load_puzzle_from_dict(d)

    d["schema_version"] = "99.0"
    with pytest.raises(ValueError, match="Unsupported schema_version"):
        load_puzzle_from_dict(d)


def test_missing_or_invalid_grid_size(valid_3x3_dict):
    """Verify missing, invalid type, or <2 grid_size."""
    d = copy.deepcopy(valid_3x3_dict)
    del d["grid_size"]
    with pytest.raises(ValueError, match="Missing 'grid_size'"):
        load_puzzle_from_dict(d)

    d["grid_size"] = "three"
    with pytest.raises(TypeError, match="grid_size must be an integer"):
        load_puzzle_from_dict(d)

    d["grid_size"] = True
    with pytest.raises(TypeError, match="grid_size must be an integer"):
        load_puzzle_from_dict(d)

    d["grid_size"] = 1
    with pytest.raises(ValueError, match="grid_size must be >= 2"):
        load_puzzle_from_dict(d)


def test_character_count_mismatch(valid_3x3_dict):
    """Verify character count must match N*N."""
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"].pop()
    with pytest.raises(ValueError, match="Expected 9 characters"):
        load_puzzle_from_dict(d)


def test_character_missing_field(valid_3x3_dict):
    """Verify missing character fields."""
    for field in ("cell", "name", "profession", "status", "clue"):
        d = copy.deepcopy(valid_3x3_dict)
        del d["characters"][0][field]
        with pytest.raises(ValueError, match=f"missing required field '{field}'"):
            load_puzzle_from_dict(d)


def test_character_invalid_cell_coordinate(valid_3x3_dict):
    """Verify invalid cell format or out of bounds."""
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][0]["cell"] = "1A"
    with pytest.raises(ValueError, match="Invalid cell coordinate"):
        load_puzzle_from_dict(d)

    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][0]["cell"] = "D1"
    with pytest.raises(ValueError, match="out of bounds"):
        load_puzzle_from_dict(d)


def test_duplicate_character_cell(valid_3x3_dict):
    """Verify duplicate cell coordinate."""
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][1]["cell"] = "A1"
    with pytest.raises(ValueError, match="Duplicate character cell"):
        load_puzzle_from_dict(d)


def test_duplicate_character_name(valid_3x3_dict):
    """Verify duplicate character name."""
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][1]["name"] = "Alice"
    with pytest.raises(ValueError, match="Duplicate character name"):
        load_puzzle_from_dict(d)


def test_invalid_character_status(valid_3x3_dict):
    """Verify invalid character status string."""
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][0]["status"] = "GUILTY"
    with pytest.raises(ValueError, match="Invalid status 'GUILTY'"):
        load_puzzle_from_dict(d)


def test_clue_missing_type(valid_3x3_dict):
    """Verify clue missing type string."""
    d = copy.deepcopy(valid_3x3_dict)
    del d["characters"][0]["clue"]["type"]
    with pytest.raises(ValueError, match="missing valid 'type' string"):
        load_puzzle_from_dict(d)


def test_clue_unknown_type(valid_3x3_dict):
    """Verify unknown clue type."""
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][0]["clue"]["type"] = "MAGIC"
    with pytest.raises(ValueError, match="Unknown clue type 'MAGIC'"):
        load_puzzle_from_dict(d)


def test_duplicate_clue_id(valid_3x3_dict):
    """Verify duplicate clue ID raises ValueError."""
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][1]["clue"]["id"] = d["characters"][0]["clue"]["id"]
    with pytest.raises(ValueError, match="Duplicate clue ID"):
        load_puzzle_from_dict(d)


def test_same_self_comparison_rejected(valid_3x3_dict):
    """Verify SAME cannot compare person with themselves (by name or cell)."""
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][1]["clue"] = {
        "type": "SAME",
        "person_a": "David",
        "person_b": "David",
    }
    with pytest.raises(ValueError, match="cannot compare a person with themselves"):
        load_puzzle_from_dict(d)

    # Mixed name and coordinate referencing same cell
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][1]["clue"] = {
        "type": "SAME",
        "person_a": "David",
        "person_b": "A2",  # David is at A2
    }
    with pytest.raises(ValueError, match="cannot compare a person with themselves"):
        load_puzzle_from_dict(d)


def test_different_self_comparison_rejected(valid_3x3_dict):
    """Verify DIFFERENT cannot compare person with themselves."""
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][2]["clue"] = {
        "type": "DIFFERENT",
        "person_a": "Alice",
        "person_b": "A1",
    }
    with pytest.raises(ValueError, match="cannot compare a person with themselves"):
        load_puzzle_from_dict(d)


def test_unresolved_reference_in_clue(valid_3x3_dict):
    """Verify reference to unknown name or out of bounds cell."""
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][0]["clue"]["target"] = "Zorblax"
    with pytest.raises(ValueError, match="neither a known character name nor a valid cell"):
        load_puzzle_from_dict(d)

    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][0]["clue"]["target"] = "E5"  # Valid coordinate format but out of 3x3 grid
    with pytest.raises(ValueError, match="out of bounds"):
        load_puzzle_from_dict(d)


def test_region_validation_errors(valid_3x3_dict):
    """Verify region errors: bad row, bad col, bad k, duplicate explicit cells."""
    # ROW out of bounds
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][3]["clue"]["region"]["row"] = 5
    with pytest.raises(ValueError, match="ROW region row 5 out of bounds"):
        load_puzzle_from_dict(d)

    # COL out of bounds
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][5]["clue"]["region"]["col"] = "Z"
    with pytest.raises(ValueError, match="COL region col 'Z' out of bounds"):
        load_puzzle_from_dict(d)

    # Cardinality k negative
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][3]["clue"]["k"] = -1
    with pytest.raises(ValueError, match="out of bounds"):
        load_puzzle_from_dict(d)

    # Cardinality k exceeding region size
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][3]["clue"]["k"] = 10
    with pytest.raises(ValueError, match="out of bounds"):
        load_puzzle_from_dict(d)

    # Cardinality k boolean
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][3]["clue"]["k"] = True
    with pytest.raises(TypeError, match="'k' must be an integer"):
        load_puzzle_from_dict(d)

    # EXPLICIT duplicate cells
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][8]["clue"]["region"]["cells"] = ["A1", "A1"]
    with pytest.raises(ValueError, match="contains duplicate cells"):
        load_puzzle_from_dict(d)


def test_parity_validation_errors(valid_3x3_dict):
    """Verify PARITY requires valid parity string."""
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][6]["clue"]["parity"] = "MAYBE"
    with pytest.raises(ValueError, match="Invalid parity 'MAYBE'"):
        load_puzzle_from_dict(d)


def test_initial_face_up_validation_errors(valid_3x3_dict):
    """Verify initial_face_up non-empty, no duplicates, valid cells."""
    d = copy.deepcopy(valid_3x3_dict)
    d["initial_face_up"] = []
    with pytest.raises(ValueError, match="must contain at least one cell"):
        load_puzzle_from_dict(d)

    d = copy.deepcopy(valid_3x3_dict)
    d["initial_face_up"] = ["A1", "A1"]
    with pytest.raises(ValueError, match="contains duplicate cells"):
        load_puzzle_from_dict(d)

    d = copy.deepcopy(valid_3x3_dict)
    d["initial_face_up"] = ["D4"]
    with pytest.raises(ValueError, match="out of bounds"):
        load_puzzle_from_dict(d)


def test_offline_truth_validation_rejects_false_clue(valid_3x3_dict):
    """Offline truth validation MUST reject a puzzle if any clue is false under solution."""
    d = copy.deepcopy(valid_3x3_dict)
    # A1 clue states Bob is INNOCENT (which is True in valid fixture).
    # Let's change A1 clue to state Bob is CRIMINAL (which is False!).
    d["characters"][0]["clue"]["status"] = "CRIMINAL"

    with pytest.raises(ValueError, match="evaluates to FALSE under the hidden solution"):
        load_puzzle_from_dict(d)
