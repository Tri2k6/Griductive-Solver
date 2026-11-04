"""Puzzle specification, JSON loading, and validation for Griductive Solver."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from griductive.domain.model import (
    AtLeastClue,
    AtMostClue,
    CellId,
    Character,
    Clue,
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
    RegionExpr,
    RowRegion,
    SameClue,
    Status,
)
from griductive.domain.regions import resolve_region
from griductive.domain.semantics import evaluate_clue

PUZZLE_SCHEMA_VERSION = "1.0"


def _resolve_reference(
    ref: Any,
    name_to_cell: Mapping[str, CellId],
    cell_to_name: Mapping[CellId, str],
    valid_cells: set[CellId],
    context: str,
) -> tuple[CellId, str]:
    """Resolve a character reference (by unique display name or coordinate string) to (CellId, name)."""
    if not isinstance(ref, str):
        raise TypeError(f"{context}: reference must be a string, got {type(ref).__name__} ({ref!r})")

    stripped = ref.strip()
    if not stripped:
        raise ValueError(f"{context}: reference string cannot be empty")

    # Check if reference is a known character display name
    if stripped in name_to_cell:
        cell = name_to_cell[stripped]
        return cell, stripped

    # Check if reference is a coordinate string within grid
    try:
        cell = CellId(stripped)
    except ValueError as exc:
        raise ValueError(
            f"{context}: reference {stripped!r} is neither a known character name nor a valid cell coordinate."
        ) from exc

    if cell in valid_cells:
        name = cell_to_name[cell]
        return cell, name

    raise ValueError(f"{context}: cell coordinate {stripped!r} is out of bounds for the puzzle grid.")


def _parse_region(
    reg_data: Any,
    grid_size: int,
    name_to_cell: Mapping[str, CellId],
    cell_to_name: Mapping[CellId, str],
    valid_cells: set[CellId],
    owner: CellId,
) -> RegionExpr:
    """Parse and validate a RegionExpr dictionary."""
    if not isinstance(reg_data, dict):
        raise TypeError(f"Region for cell {owner} must be a dictionary, got {type(reg_data).__name__}")

    reg_type = reg_data.get("type")
    if not isinstance(reg_type, str):
        raise ValueError(f"Region for cell {owner} missing valid 'type' string")

    reg_type_upper = reg_type.strip().upper()

    if reg_type_upper == "ROW":
        if "row" not in reg_data:
            raise ValueError(f"ROW region for cell {owner} missing 'row' field")
        row = reg_data["row"]
        if isinstance(row, bool) or not isinstance(row, int):
            raise TypeError(f"ROW region 'row' must be an integer, got {type(row).__name__}")
        if row < 1 or row > grid_size:
            raise ValueError(f"ROW region row {row} out of bounds for grid_size {grid_size} (1..{grid_size})")
        return RowRegion(row=row)

    if reg_type_upper == "COL":
        if "col" not in reg_data:
            raise ValueError(f"COL region for cell {owner} missing 'col' field")
        col = reg_data["col"]
        if not isinstance(col, str) or len(col.strip()) != 1 or not col.strip().isalpha():
            raise ValueError(f"COL region 'col' must be a single letter, got {col!r}")
        col_str = col.strip().upper()
        col_idx = ord(col_str) - ord("A") + 1
        if col_idx < 1 or col_idx > grid_size:
            raise ValueError(f"COL region col {col_str!r} out of bounds for grid_size {grid_size}")
        return ColRegion(col=col_str)

    if reg_type_upper == "NEIGHBORS":
        if "center" not in reg_data:
            raise ValueError(f"NEIGHBORS region for cell {owner} missing 'center' field")
        center_cell, _ = _resolve_reference(
            reg_data["center"],
            name_to_cell,
            cell_to_name,
            valid_cells,
            f"NEIGHBORS region center for cell {owner}",
        )
        return NeighborsRegion(center=center_cell)

    if reg_type_upper == "EXPLICIT":
        if "cells" not in reg_data:
            raise ValueError(f"EXPLICIT region for cell {owner} missing 'cells' field")
        cells_raw = reg_data["cells"]
        if not isinstance(cells_raw, (list, tuple)):
            raise TypeError(f"EXPLICIT region 'cells' must be a list or tuple, got {type(cells_raw).__name__}")
        if len(cells_raw) == 0:
            raise ValueError(f"EXPLICIT region for cell {owner} cannot be empty")

        resolved_cells: list[CellId] = []
        for idx, item in enumerate(cells_raw):
            c, _ = _resolve_reference(
                item,
                name_to_cell,
                cell_to_name,
                valid_cells,
                f"EXPLICIT region cell index {idx} for cell {owner}",
            )
            resolved_cells.append(c)

        if len(set(resolved_cells)) != len(resolved_cells):
            raise ValueError(f"EXPLICIT region for cell {owner} contains duplicate cells: {resolved_cells}")

        return ExplicitRegion(cells=tuple(resolved_cells))

    if reg_type_upper == "COMMON_NEIGHBORS":
        if "cell_a" not in reg_data or "cell_b" not in reg_data:
            raise ValueError(
                f"COMMON_NEIGHBORS region for cell {owner} requires both 'cell_a' and 'cell_b' fields"
            )
        cell_a, _ = _resolve_reference(
            reg_data["cell_a"],
            name_to_cell,
            cell_to_name,
            valid_cells,
            f"COMMON_NEIGHBORS cell_a for cell {owner}",
        )
        cell_b, _ = _resolve_reference(
            reg_data["cell_b"],
            name_to_cell,
            cell_to_name,
            valid_cells,
            f"COMMON_NEIGHBORS cell_b for cell {owner}",
        )
        return CommonNeighborsRegion(cell_a=cell_a, cell_b=cell_b)

    raise ValueError(f"Unknown region type {reg_type!r} in clue for cell {owner}")


def _parse_clue(
    clue_data: Any,
    owner: CellId,
    grid_size: int,
    name_to_cell: Mapping[str, CellId],
    cell_to_name: Mapping[CellId, str],
    valid_cells: set[CellId],
    seen_clue_ids: set[str],
) -> Clue:
    """Parse and validate a structured clue dictionary."""
    if not isinstance(clue_data, dict):
        raise TypeError(f"Clue for cell {owner} must be a dictionary, got {type(clue_data).__name__}")

    clue_type = clue_data.get("type")
    if not isinstance(clue_type, str):
        raise ValueError(f"Clue for cell {owner} missing valid 'type' string")

    # Clue ID
    has_id = False
    clue_id_raw = None
    if "id" in clue_data:
        has_id = True
        clue_id_raw = clue_data["id"]
    elif "clue_id" in clue_data:
        has_id = True
        clue_id_raw = clue_data["clue_id"]

    if has_id:
        if not isinstance(clue_id_raw, str) or not clue_id_raw.strip():
            raise ValueError(f"Clue ID for cell {owner} must be a non-empty string, got {clue_id_raw!r}")
        clue_id = clue_id_raw.strip()
    else:
        clue_id = f"c_{owner.name}"

    if clue_id in seen_clue_ids:
        raise ValueError(f"Duplicate clue ID {clue_id!r} detected in puzzle")
    seen_clue_ids.add(clue_id)

    clue_type_upper = clue_type.strip().upper()

    if clue_type_upper == "FACT":
        if "target" not in clue_data:
            raise ValueError(f"FACT clue {clue_id} missing 'target' field")
        if "status" not in clue_data:
            raise ValueError(f"FACT clue {clue_id} missing 'status' field")

        target_cell, target_name = _resolve_reference(
            clue_data["target"],
            name_to_cell,
            cell_to_name,
            valid_cells,
            f"FACT clue {clue_id} target",
        )
        st_raw = clue_data["status"]
        if not isinstance(st_raw, str):
            raise TypeError(f"FACT clue {clue_id} status must be a string, got {type(st_raw).__name__}")
        try:
            status = Status(st_raw.strip().upper())
        except ValueError as exc:
            raise ValueError(f"Invalid status {st_raw!r} in FACT clue {clue_id}. Must be CRIMINAL or INNOCENT.") from exc

        return FactClue(
            clue_id=clue_id,
            owner=owner,
            target=target_cell,
            status=status,
            target_name=target_name,
        )

    if clue_type_upper in ("SAME", "DIFFERENT"):
        if "person_a" not in clue_data or "person_b" not in clue_data:
            raise ValueError(f"{clue_type_upper} clue {clue_id} requires both 'person_a' and 'person_b' fields")

        cell_a, name_a = _resolve_reference(
            clue_data["person_a"],
            name_to_cell,
            cell_to_name,
            valid_cells,
            f"{clue_type_upper} clue {clue_id} person_a",
        )
        cell_b, name_b = _resolve_reference(
            clue_data["person_b"],
            name_to_cell,
            cell_to_name,
            valid_cells,
            f"{clue_type_upper} clue {clue_id} person_b",
        )

        if cell_a == cell_b:
            raise ValueError(
                f"{clue_type_upper} clue {clue_id} cannot compare a person with themselves: {clue_data['person_a']!r}"
            )

        if clue_type_upper == "SAME":
            return SameClue(
                clue_id=clue_id,
                owner=owner,
                person_a=cell_a,
                person_b=cell_b,
                name_a=name_a,
                name_b=name_b,
            )
        return DifferentClue(
            clue_id=clue_id,
            owner=owner,
            person_a=cell_a,
            person_b=cell_b,
            name_a=name_a,
            name_b=name_b,
        )

    if clue_type_upper in ("EXACTLY", "AT_LEAST", "AT_MOST"):
        if "k" not in clue_data:
            raise ValueError(f"{clue_type_upper} clue {clue_id} missing 'k' field")
        if "region" not in clue_data:
            raise ValueError(f"{clue_type_upper} clue {clue_id} missing 'region' field")

        k = clue_data["k"]
        if isinstance(k, bool) or not isinstance(k, int):
            raise TypeError(f"{clue_type_upper} clue {clue_id} 'k' must be an integer, got {type(k).__name__}")

        region_expr = _parse_region(
            clue_data["region"],
            grid_size,
            name_to_cell,
            cell_to_name,
            valid_cells,
            owner,
        )
        region_cells = resolve_region(region_expr, grid_size)
        if k < 0 or k > len(region_cells):
            raise ValueError(
                f"{clue_type_upper} clue {clue_id} cardinality k={k} out of bounds for region size {len(region_cells)} (0..{len(region_cells)})"
            )

        if clue_type_upper == "EXACTLY":
            return ExactlyClue(clue_id=clue_id, owner=owner, k=k, region=region_expr)
        if clue_type_upper == "AT_LEAST":
            return AtLeastClue(clue_id=clue_id, owner=owner, k=k, region=region_expr)
        return AtMostClue(clue_id=clue_id, owner=owner, k=k, region=region_expr)

    if clue_type_upper == "PARITY":
        if "parity" not in clue_data:
            raise ValueError(f"PARITY clue {clue_id} missing 'parity' field")
        if "region" not in clue_data:
            raise ValueError(f"PARITY clue {clue_id} missing 'region' field")

        p_raw = clue_data["parity"]
        if not isinstance(p_raw, str):
            raise TypeError(f"PARITY clue {clue_id} 'parity' must be a string, got {type(p_raw).__name__}")
        try:
            parity = Parity(p_raw.strip().upper())
        except ValueError as exc:
            raise ValueError(f"Invalid parity {p_raw!r} in PARITY clue {clue_id}. Must be EVEN or ODD.") from exc

        region_expr = _parse_region(
            clue_data["region"],
            grid_size,
            name_to_cell,
            cell_to_name,
            valid_cells,
            owner,
        )
        # Ensure region resolves without error
        resolve_region(region_expr, grid_size)
        return ParityClue(clue_id=clue_id, owner=owner, parity=parity, region=region_expr)

    raise ValueError(f"Unknown clue type {clue_type!r} in clue {clue_id} for cell {owner}")


def load_puzzle_from_dict(data: dict[str, Any]) -> Puzzle:
    """Parse, validate, and construct a private Puzzle from a dictionary.

    Validates schema structure, grid coverage, uniqueness of names and coordinates,
    region resolution, cardinality bounds, initial face-up cards, and semantic truth
    under the ground truth solution.
    """
    if not isinstance(data, dict):
        raise TypeError(f"Puzzle data must be a dictionary, got {type(data).__name__}")

    # Schema version
    if "schema_version" not in data:
        raise ValueError("Missing 'schema_version' in puzzle data")
    version_raw = data["schema_version"]
    if not isinstance(version_raw, str):
        raise TypeError(
            "schema_version must be a string, "
            f"got {type(version_raw).__name__}"
        )
    version = version_raw.strip()
    if version != PUZZLE_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported schema_version {version!r}. Supported version is {PUZZLE_SCHEMA_VERSION!r}"
        )

    # Grid size
    if "grid_size" not in data:
        raise ValueError("Missing 'grid_size' in puzzle data")
    grid_size = data["grid_size"]
    if isinstance(grid_size, bool) or not isinstance(grid_size, int):
        raise TypeError(f"grid_size must be an integer, got {type(grid_size).__name__}")
    if grid_size < 2:
        raise ValueError(f"grid_size must be >= 2, got {grid_size}")

    # Characters list
    if "characters" not in data:
        raise ValueError("Missing 'characters' list in puzzle data")
    chars_data = data["characters"]
    if not isinstance(chars_data, list):
        raise TypeError(f"'characters' must be a list, got {type(chars_data).__name__}")

    expected_cells = grid_size * grid_size
    if len(chars_data) != expected_cells:
        raise ValueError(
            f"Expected {expected_cells} characters for grid_size {grid_size}, got {len(chars_data)}"
        )

    # First pass: validate character metadata, cells, names, and solution
    characters: list[Character] = []
    solution: dict[CellId, Status] = {}
    clue_dicts: dict[CellId, dict[str, Any]] = {}
    name_to_cell: dict[str, CellId] = {}
    cell_to_name: dict[CellId, str] = {}
    valid_cells: set[CellId] = set()

    for idx, char_entry in enumerate(chars_data):
        if not isinstance(char_entry, dict):
            raise TypeError(f"Character entry at index {idx} must be a dict, got {type(char_entry).__name__}")

        for field in ("cell", "name", "profession", "status", "clue"):
            if field not in char_entry:
                raise ValueError(f"Character entry at index {idx} missing required field {field!r}")

        cell_str = char_entry["cell"]
        if not isinstance(cell_str, str):
            raise TypeError(f"Character cell must be a coordinate string, got {type(cell_str).__name__}")
        cell = CellId(cell_str)

        if not cell.is_valid_for(grid_size):
            raise ValueError(f"Cell {cell} at index {idx} is out of bounds for grid_size {grid_size}")

        if cell in valid_cells:
            raise ValueError(f"Duplicate character cell coordinate: {cell}")
        valid_cells.add(cell)

        name = char_entry["name"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Character name at index {idx} must be a non-empty string, got {name!r}")
        name_str = name.strip()
        if name_str in name_to_cell:
            raise ValueError(f"Duplicate character name {name_str!r} in puzzle")
        name_to_cell[name_str] = cell
        cell_to_name[cell] = name_str

        prof = char_entry["profession"]
        if not isinstance(prof, str):
            raise TypeError(f"Character profession must be a string, got {type(prof).__name__}")

        st_raw = char_entry["status"]
        if not isinstance(st_raw, str):
            raise TypeError(f"Character status must be a string, got {type(st_raw).__name__}")
        try:
            status = Status(st_raw.strip().upper())
        except ValueError as exc:
            raise ValueError(
                f"Invalid status {st_raw!r} for character {name_str}. Must be CRIMINAL or INNOCENT."
            ) from exc

        characters.append(Character(cell=cell, name=name_str, profession=prof.strip()))
        solution[cell] = status
        clue_dicts[cell] = char_entry["clue"]

    # Verify that all N*N cells in row-major order are present
    for r in range(1, grid_size + 1):
        for c in range(1, grid_size + 1):
            expected_cell = CellId.from_coords(r, c)
            if expected_cell not in valid_cells:
                raise ValueError(f"Missing character for grid coordinate {expected_cell}")

    # Second pass: parse and validate all clues
    clues: dict[CellId, Clue] = {}
    seen_clue_ids: set[str] = set()
    for cell, c_dict in clue_dicts.items():
        clue = _parse_clue(
            c_dict,
            cell,
            grid_size,
            name_to_cell,
            cell_to_name,
            valid_cells,
            seen_clue_ids,
        )
        clues[cell] = clue

    # Initial face-up cards
    if "initial_face_up" not in data:
        raise ValueError("Missing 'initial_face_up' in puzzle data")
    face_up_raw = data["initial_face_up"]
    if not isinstance(face_up_raw, (list, tuple)):
        raise TypeError(f"'initial_face_up' must be a list or tuple, got {type(face_up_raw).__name__}")
    if len(face_up_raw) == 0:
        raise ValueError("'initial_face_up' must contain at least one cell")

    initial_face_up_cells: list[CellId] = []
    for item in face_up_raw:
        c, _ = _resolve_reference(
            item,
            name_to_cell,
            cell_to_name,
            valid_cells,
            "initial_face_up",
        )
        initial_face_up_cells.append(c)

    if len(set(initial_face_up_cells)) != len(initial_face_up_cells):
        raise ValueError(f"'initial_face_up' contains duplicate cells: {initial_face_up_cells}")

    # Offline truth validation: every clue must evaluate to True under the solution!
    for cell, clue in clues.items():
        if not evaluate_clue(clue, solution, grid_size):
            raise ValueError(
                f"Puzzle validation failed: clue {clue.clue_id} for cell {cell} ({clue.__class__.__name__}) "
                f"evaluates to FALSE under the hidden solution."
            )

    return Puzzle(
        grid_size=grid_size,
        characters=tuple(characters),
        solution=solution,
        clues=clues,
        initial_face_up=frozenset(initial_face_up_cells),
    )


def load_puzzle_from_json(path_or_json: str | Path) -> Puzzle:
    """Load a Puzzle from a JSON file path or a raw JSON string."""
    if isinstance(path_or_json, Path):
        content = path_or_json.read_text(encoding="utf-8")
        data = json.loads(content)
    elif isinstance(path_or_json, str):
        stripped = path_or_json.strip()
        if not stripped:
            raise ValueError("Empty puzzle path or JSON string provided")
        if stripped.startswith("{"):
            data = json.loads(stripped)
        else:
            p = Path(path_or_json)
            if not p.is_file():
                raise FileNotFoundError(f"Puzzle file not found: {path_or_json}")
            content = p.read_text(encoding="utf-8")
            data = json.loads(content)
    else:
        raise TypeError(f"Expected str or Path, got {type(path_or_json).__name__}")

    return load_puzzle_from_dict(data)


def validate_puzzle_data(data: dict[str, Any]) -> None:
    """Validate puzzle data dictionary without returning the Puzzle object.

    Raises ValueError, TypeError, or KeyError if data is invalid or inconsistent.
    """
    load_puzzle_from_dict(data)
