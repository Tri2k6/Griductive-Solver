"""Adversarial stress tests for Puzzle I/O (src/griductive/io.py).

Probes schema edge cases, malformed coordinates, duplicate references,
invalid cardinality k, bad regions, initial_face_up bounds,
offline truth validation, immutability preservation, and clue ID validation.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from griductive.game.io import (
    load_puzzle_from_dict,
    load_puzzle_from_json,
    validate_puzzle_data,
)
from griductive.domain.model import CellId, Status


@pytest.fixture
def valid_3x3_dict() -> dict[str, Any]:
    """Load valid 3x3 puzzle dictionary fixture."""
    fixture_path = Path("tests/fixtures/puzzle_3x3_valid.json")
    return json.loads(fixture_path.read_text(encoding="utf-8"))


# ============================================================================
# 1. Top-level Schema and Grid Size Edge Cases
# ============================================================================


def test_malformed_schema_versions(valid_3x3_dict: dict[str, Any]) -> None:
    """Verify various unsupported or malformed schema versions."""
    for bad_ver in ["2.0", "0.9", "1.1", "", "v1.0"]:
        d = copy.deepcopy(valid_3x3_dict)
        d["schema_version"] = bad_ver
        with pytest.raises(ValueError, match="Unsupported schema_version"):
            load_puzzle_from_dict(d)

    for bad_ver in [1, 1.0, True, None, ["1.0"], {}]:
        d = copy.deepcopy(valid_3x3_dict)
        d["schema_version"] = bad_ver
        with pytest.raises(TypeError, match="schema_version must be a string"):
            load_puzzle_from_dict(d)


def test_schema_defines_each_supported_clue_and_region_variant() -> None:
    """Keep the published Draft-07 schema aligned with the manual loader contract."""
    schema_path = Path("schema/puzzle_schema_v1.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    definitions = schema["definitions"]

    version_schema = schema["properties"]["schema_version"]
    assert version_schema["type"] == "string"
    assert re.fullmatch(version_schema["pattern"], " 1.0 ")
    assert len(definitions["clue"]["oneOf"]) == 7
    assert len(definitions["region"]["oneOf"]) == 5

    required_by_clue = {
        "fact_clue": {"type", "target", "status"},
        "same_clue": {"type", "person_a", "person_b"},
        "different_clue": {"type", "person_a", "person_b"},
        "exactly_clue": {"type", "k", "region"},
        "at_least_clue": {"type", "k", "region"},
        "at_most_clue": {"type", "k", "region"},
        "parity_clue": {"type", "parity", "region"},
    }
    for clue_name, required in required_by_clue.items():
        assert required.issubset(definitions[clue_name]["required"])
        type_schema = definitions[clue_name]["properties"]["type"]
        assert type_schema["type"] == "string"

    normalized_clue_types = {
        "fact_clue": " fact ",
        "same_clue": " same ",
        "different_clue": " different ",
        "exactly_clue": " exactly ",
        "at_least_clue": " at_least ",
        "at_most_clue": " at_most ",
        "parity_clue": " parity ",
    }
    for definition_name, sample in normalized_clue_types.items():
        pattern = definitions[definition_name]["properties"]["type"]["pattern"]
        assert re.fullmatch(pattern, sample)

    for region_variant in definitions["region"]["oneOf"]:
        assert region_variant["properties"]["type"]["type"] == "string"
    assert re.fullmatch(definitions["status"]["pattern"], " innocent ")
    assert re.fullmatch(definitions["parity"]["pattern"], " odd ")


def test_schema_normalization_matches_loader(
    valid_3x3_dict: dict[str, Any],
) -> None:
    """Values accepted after loader normalization must also match the schema."""
    data = copy.deepcopy(valid_3x3_dict)
    data["schema_version"] = " 1.0 "
    data["characters"][0]["cell"] = " a1 "
    data["characters"][0]["status"] = " criminal "
    data["characters"][0]["clue"]["type"] = " fact "
    data["characters"][0]["clue"]["status"] = " innocent "
    data["initial_face_up"][0] = f" {data['initial_face_up'][0].lower()} "

    puzzle = load_puzzle_from_dict(data)
    assert puzzle.grid_size == 3
    assert puzzle.solution[CellId("A1")] == Status.CRIMINAL


def test_missing_required_top_level_keys(
    valid_3x3_dict: dict[str, Any],
) -> None:
    """Verify missing each required top-level key raises ValueError."""
    for key in (
        "schema_version",
        "grid_size",
        "characters",
        "initial_face_up",
    ):
        d = copy.deepcopy(valid_3x3_dict)
        del d[key]
        with pytest.raises(ValueError, match=f"Missing '{key}'"):
            load_puzzle_from_dict(d)


def test_invalid_grid_sizes(valid_3x3_dict: dict[str, Any]) -> None:
    """Verify non-integer, negative, zero, or <2 grid sizes."""
    # Type errors
    for bad_type in [True, False, 3.5, "3", None, [3]]:
        d = copy.deepcopy(valid_3x3_dict)
        d["grid_size"] = bad_type
        with pytest.raises(TypeError, match="grid_size must be an integer"):
            load_puzzle_from_dict(d)

    # Value errors (size < 2)
    for bad_size in [1, 0, -1, -5]:
        d = copy.deepcopy(valid_3x3_dict)
        d["grid_size"] = bad_size
        with pytest.raises(ValueError, match="grid_size must be >= 2"):
            load_puzzle_from_dict(d)


# ============================================================================
# 2. Character Counts, Duplicates, and Geometry Bounds
# ============================================================================


def test_character_count_mismatches(valid_3x3_dict: dict[str, Any]) -> None:
    """Verify mismatch between character count and grid_size * grid_size."""
    # 8 characters instead of 9
    d8 = copy.deepcopy(valid_3x3_dict)
    d8["characters"].pop()
    with pytest.raises(ValueError, match="Expected 9 characters"):
        load_puzzle_from_dict(d8)

    # 10 characters instead of 9
    d10 = copy.deepcopy(valid_3x3_dict)
    extra_char = copy.deepcopy(d10["characters"][0])
    extra_char["cell"] = "C3"
    d10["characters"].append(extra_char)
    with pytest.raises(ValueError, match="Expected 9 characters"):
        load_puzzle_from_dict(d10)


def test_malformed_and_oob_cell_coordinates(
    valid_3x3_dict: dict[str, Any],
) -> None:
    """Verify malformed coordinate strings or out of bounds cells."""
    bad_coords = ["1A", "AA1", "A", "1", "", "A0", "A-1", "@1", "A1B", "A 1"]
    for bad_coord in bad_coords:
        d = copy.deepcopy(valid_3x3_dict)
        d["characters"][0]["cell"] = bad_coord
        with pytest.raises(ValueError):
            load_puzzle_from_dict(d)

    # Valid coordinate format, but out of 3x3 bounds
    for oob_coord in ["D1", "A4", "D4", "Z9"]:
        d = copy.deepcopy(valid_3x3_dict)
        d["characters"][0]["cell"] = oob_coord
        with pytest.raises(ValueError, match="out of bounds"):
            load_puzzle_from_dict(d)


def test_duplicate_character_coordinates_and_names(
    valid_3x3_dict: dict[str, Any],
) -> None:
    """Verify duplicate cell coordinates and duplicate display names."""
    # Duplicate coordinate
    d_cell = copy.deepcopy(valid_3x3_dict)
    d_cell["characters"][1]["cell"] = "A1"
    with pytest.raises(ValueError, match="Duplicate character cell"):
        load_puzzle_from_dict(d_cell)

    # Case-insensitive duplicate coordinate ("a1" vs "A1")
    d_cell_case = copy.deepcopy(valid_3x3_dict)
    d_cell_case["characters"][1]["cell"] = "a1"
    with pytest.raises(ValueError, match="Duplicate character cell"):
        load_puzzle_from_dict(d_cell_case)

    # Duplicate name
    d_name = copy.deepcopy(valid_3x3_dict)
    d_name["characters"][1]["name"] = "Alice"
    with pytest.raises(
        ValueError, match="Duplicate character name 'Alice'"
    ):
        load_puzzle_from_dict(d_name)

    # Duplicate name with whitespace stripping
    d_name_ws = copy.deepcopy(valid_3x3_dict)
    d_name_ws["characters"][1]["name"] = "  Alice  "
    with pytest.raises(
        ValueError, match="Duplicate character name 'Alice'"
    ):
        load_puzzle_from_dict(d_name_ws)


# ============================================================================
# 3. Clue ID Validation (Adversarial Edge Cases)
# ============================================================================


def test_clue_id_invalid_empty_or_falsy_rejected(
    valid_3x3_dict: dict[str, Any],
) -> None:
    """Clue ID, when provided, must be a non-empty string and not falsy."""
    for bad_id in ["", "   ", 0, False, [], {}]:
        d = copy.deepcopy(valid_3x3_dict)
        d["characters"][0]["clue"]["id"] = bad_id
        with pytest.raises(
            (ValueError, TypeError),
            match="[Cc]lue ID.*must be a non-empty string",
        ):
            load_puzzle_from_dict(d)


def test_duplicate_clue_id_cross_character(
    valid_3x3_dict: dict[str, Any],
) -> None:
    """Duplicate clue IDs across different characters must be rejected."""
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][0]["clue"]["id"] = "shared_id"
    d["characters"][1]["clue"]["id"] = "shared_id"
    with pytest.raises(ValueError, match="Duplicate clue ID 'shared_id'"):
        load_puzzle_from_dict(d)


# ============================================================================
# 4. Self-Referencing and Reference Resolution in SAME / DIFFERENT
# ============================================================================


def test_same_self_comparison_all_modes(
    valid_3x3_dict: dict[str, Any],
) -> None:
    """SAME clue cannot compare person with themselves (name/coord/mixed)."""
    # By name
    d1 = copy.deepcopy(valid_3x3_dict)
    d1["characters"][1]["clue"] = {
        "type": "SAME",
        "person_a": "Alice",
        "person_b": "Alice",
    }
    with pytest.raises(
        ValueError, match="cannot compare a person with themselves"
    ):
        load_puzzle_from_dict(d1)

    # By coordinate
    d2 = copy.deepcopy(valid_3x3_dict)
    d2["characters"][1]["clue"] = {
        "type": "SAME",
        "person_a": "A1",
        "person_b": "A1",
    }
    with pytest.raises(
        ValueError, match="cannot compare a person with themselves"
    ):
        load_puzzle_from_dict(d2)

    # Mixed name and coordinate
    d3 = copy.deepcopy(valid_3x3_dict)
    d3["characters"][1]["clue"] = {
        "type": "SAME",
        "person_a": "Alice",
        "person_b": "A1",
    }
    with pytest.raises(
        ValueError, match="cannot compare a person with themselves"
    ):
        load_puzzle_from_dict(d3)


def test_different_self_comparison_all_modes(
    valid_3x3_dict: dict[str, Any],
) -> None:
    """DIFFERENT clue cannot compare person with themselves."""
    d = copy.deepcopy(valid_3x3_dict)
    d["characters"][2]["clue"] = {
        "type": "DIFFERENT",
        "person_a": "Charlie",
        "person_b": "C1",
    }
    with pytest.raises(
        ValueError, match="cannot compare a person with themselves"
    ):
        load_puzzle_from_dict(d)


# ============================================================================
# 5. Cardinality Clue Constraints (k and Region Bounds)
# ============================================================================


def test_cardinality_k_type_and_bounds(
    valid_3x3_dict: dict[str, Any],
) -> None:
    """k in EXACTLY/AT_LEAST/AT_MOST must be non-boolean int in 0..|region|."""
    # Non-int / bool
    for bad_k in [True, False, 1.5, "2", None, [1]]:
        d = copy.deepcopy(valid_3x3_dict)
        d["characters"][3]["clue"]["k"] = bad_k
        with pytest.raises(TypeError, match="'k' must be an integer"):
            load_puzzle_from_dict(d)

    # Out of bounds (< 0 or > region size)
    for oob_k in [-1, -10, 4, 100]:
        d = copy.deepcopy(valid_3x3_dict)
        d["characters"][3]["clue"]["k"] = oob_k
        with pytest.raises(ValueError, match="cardinality k=.*out of bounds"):
            load_puzzle_from_dict(d)


def test_region_geometric_bounds(valid_3x3_dict: dict[str, Any]) -> None:
    """Test out of bounds and malformed regions."""
    # ROW bounds
    for bad_row in [0, -1, 4, 10]:
        d = copy.deepcopy(valid_3x3_dict)
        d["characters"][3]["clue"]["region"]["row"] = bad_row
        with pytest.raises(
            ValueError,
            match="ROW region row .* out of bounds",
        ):
            load_puzzle_from_dict(d)

    # COL bounds
    for bad_col in ["D", "Z", "1", "AB", ""]:
        d = copy.deepcopy(valid_3x3_dict)
        d["characters"][5]["clue"]["region"]["col"] = bad_col
        with pytest.raises(ValueError):
            load_puzzle_from_dict(d)

    # NEIGHBORS center out of bounds or invalid
    for bad_center in ["D4", "Ghost", "", "   "]:
        d = copy.deepcopy(valid_3x3_dict)
        d["characters"][4]["clue"]["region"]["center"] = bad_center
        with pytest.raises(ValueError):
            load_puzzle_from_dict(d)

    # EXPLICIT empty or duplicates
    d_empty = copy.deepcopy(valid_3x3_dict)
    d_empty["characters"][8]["clue"]["region"]["cells"] = []
    with pytest.raises(ValueError, match="EXPLICIT region .* cannot be empty"):
        load_puzzle_from_dict(d_empty)

    d_dup_mixed = copy.deepcopy(valid_3x3_dict)
    d_dup_mixed["characters"][8]["clue"]["region"]["cells"] = [
        "Alice",
        "A1",
        "C3",
    ]
    with pytest.raises(ValueError, match="contains duplicate cells"):
        load_puzzle_from_dict(d_dup_mixed)

    # COMMON_NEIGHBORS with same cell (by coord, name, or mixed)
    for a, b in [("A1", "A1"), ("Alice", "Alice"), ("Alice", "A1")]:
        d_cn = copy.deepcopy(valid_3x3_dict)
        d_cn["characters"][7]["clue"]["region"] = {
            "type": "COMMON_NEIGHBORS",
            "cell_a": a,
            "cell_b": b,
        }
        with pytest.raises(
            ValueError,
            match="CommonNeighborsRegion requires two distinct cells",
        ):
            load_puzzle_from_dict(d_cn)


# ============================================================================
# 6. initial_face_up Constraints
# ============================================================================


def test_initial_face_up_edge_cases(valid_3x3_dict: dict[str, Any]) -> None:
    """Verify initial_face_up must be non-empty, distinct, valid cells."""
    # Empty
    d_empty = copy.deepcopy(valid_3x3_dict)
    d_empty["initial_face_up"] = []
    with pytest.raises(
        ValueError, match="'initial_face_up' must contain at least one cell"
    ):
        load_puzzle_from_dict(d_empty)

    # Non-list type
    for bad_type in [None, "A1", 123, {"A1"}]:
        d = copy.deepcopy(valid_3x3_dict)
        d["initial_face_up"] = bad_type
        with pytest.raises(
            TypeError, match="'initial_face_up' must be a list or tuple"
        ):
            load_puzzle_from_dict(d)

    # Out of bounds cell
    d_oob = copy.deepcopy(valid_3x3_dict)
    d_oob["initial_face_up"] = ["A1", "D4"]
    with pytest.raises(ValueError, match="out of bounds"):
        load_puzzle_from_dict(d_oob)

    # Unknown character name
    d_ghost = copy.deepcopy(valid_3x3_dict)
    d_ghost["initial_face_up"] = ["A1", "Ghost"]
    with pytest.raises(
        ValueError, match="neither a known character name nor a valid cell"
    ):
        load_puzzle_from_dict(d_ghost)

    # Duplicate mixed name and coordinate
    d_dup = copy.deepcopy(valid_3x3_dict)
    d_dup["initial_face_up"] = ["Alice", "A1"]
    with pytest.raises(
        ValueError, match="'initial_face_up' contains duplicate cells"
    ):
        load_puzzle_from_dict(d_dup)


# ============================================================================
# 7. Offline Truth Validation on Contradictory Clues
# ============================================================================


def test_offline_truth_validation_all_templates(
    valid_3x3_dict: dict[str, Any],
) -> None:
    """Ensure false clues under hidden solution are rejected with error."""
    # False FACT
    d1 = copy.deepcopy(valid_3x3_dict)
    d1["characters"][0]["clue"]["status"] = "CRIMINAL"  # Bob is INNOCENT
    with pytest.raises(
        ValueError, match="evaluates to FALSE under the hidden solution"
    ):
        load_puzzle_from_dict(d1)

    # False SAME
    d2 = copy.deepcopy(valid_3x3_dict)
    d2["characters"][1]["clue"]["person_a"] = "Alice"  # Alice is CRIMINAL
    with pytest.raises(
        ValueError, match="evaluates to FALSE under the hidden solution"
    ):
        load_puzzle_from_dict(d2)

    # False DIFFERENT
    d3 = copy.deepcopy(valid_3x3_dict)
    d3["characters"][2]["clue"]["person_a"] = "David"  # Both INNOCENT
    with pytest.raises(
        ValueError, match="evaluates to FALSE under the hidden solution"
    ):
        load_puzzle_from_dict(d3)

    # False EXACTLY
    d4 = copy.deepcopy(valid_3x3_dict)
    d4["characters"][3]["clue"]["k"] = 1  # Actually 2
    with pytest.raises(
        ValueError, match="evaluates to FALSE under the hidden solution"
    ):
        load_puzzle_from_dict(d4)

    # False AT_LEAST
    d5 = copy.deepcopy(valid_3x3_dict)
    d5["characters"][4]["clue"]["k"] = 5  # Actually 3
    with pytest.raises(
        ValueError, match="evaluates to FALSE under the hidden solution"
    ):
        load_puzzle_from_dict(d5)

    # False AT_MOST
    d6 = copy.deepcopy(valid_3x3_dict)
    d6["characters"][5]["clue"]["k"] = 0  # Actually 1
    with pytest.raises(
        ValueError, match="evaluates to FALSE under the hidden solution"
    ):
        load_puzzle_from_dict(d6)

    # False PARITY
    d7 = copy.deepcopy(valid_3x3_dict)
    d7["characters"][6]["clue"]["parity"] = "EVEN"  # Actually ODD
    with pytest.raises(
        ValueError, match="evaluates to FALSE under the hidden solution"
    ):
        load_puzzle_from_dict(d7)

    # False COMMON_NEIGHBORS region count
    d8 = copy.deepcopy(valid_3x3_dict)
    d8["characters"][7]["clue"]["k"] = 0  # Actually 1
    with pytest.raises(
        ValueError, match="evaluates to FALSE under the hidden solution"
    ):
        load_puzzle_from_dict(d8)


# ============================================================================
# 8. Immutability and Input Mutation Independence
# ============================================================================


def test_puzzle_immutability_and_input_isolation(
    valid_3x3_dict: dict[str, Any],
) -> None:
    """Verify loaded Puzzle cannot be corrupted by external input mutation."""
    dict_copy = copy.deepcopy(valid_3x3_dict)
    puzzle = load_puzzle_from_dict(dict_copy)

    # Validate helper validation function passes
    validate_puzzle_data(dict_copy)

    # Mutating input dictionary after load must not affect puzzle
    dict_copy["characters"][0]["status"] = "INNOCENT"
    dict_copy["grid_size"] = 999
    dict_copy["initial_face_up"].append("C3")

    assert puzzle.grid_size == 3
    assert puzzle.solution[CellId("A1")] == Status.CRIMINAL
    assert CellId("C3") not in puzzle.initial_face_up

    # Mutating puzzle solution mapping must raise TypeError
    with pytest.raises(TypeError):
        puzzle.solution[CellId("A1")] = Status.INNOCENT  # type: ignore

    # Mutating puzzle clues mapping must raise TypeError
    with pytest.raises(TypeError):
        puzzle.clues[CellId("A1")] = None  # type: ignore


# ============================================================================
# 9. load_puzzle_from_json String vs Path Handling
# ============================================================================


def test_load_puzzle_from_json_string_and_empty() -> None:
    """Verify loading from JSON string and rejection of empty string."""
    # Empty string should raise ValueError or FileNotFoundError
    with pytest.raises((ValueError, FileNotFoundError)):
        load_puzzle_from_json("")
