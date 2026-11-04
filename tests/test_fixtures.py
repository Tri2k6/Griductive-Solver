"""Comprehensive unit and integration tests for puzzle fixtures and manifest."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from griductive.game.io import load_puzzle_from_json
from griductive.domain.model import (
    AtLeastClue,
    AtMostClue,
    CommonNeighborsRegion,
    DifferentClue,
    ExactlyClue,
    ExplicitRegion,
    FactClue,
    NeighborsRegion,
    ParityClue,
    Puzzle,
    RowRegion,
    ColRegion,
    SameClue,
)
from griductive.analysis.validation import (
    PlayabilityResult,
    UniquenessResult,
    validate_puzzle,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "puzzles"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"


def test_manifest_structure_and_files_exist():
    """Verify that manifest.json is valid and all referenced files exist."""
    assert MANIFEST_PATH.is_file(), f"Manifest not found at {MANIFEST_PATH}"
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert data.get("manifest_version") == "1.0"
    puzzles = data.get("puzzles")
    assert isinstance(puzzles, list) and len(puzzles) >= 5

    for entry in puzzles:
        fpath = Path(__file__).resolve().parent.parent / entry["file"]
        assert fpath.is_file(), f"Puzzle file {entry['file']} does not exist."
        assert isinstance(entry["schema_valid"], bool)
        assert isinstance(entry["semantic_valid"], bool)


def test_valid_fixtures_load_and_validate():
    """Verify all fixtures marked semantically valid against manifest claims."""
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for entry in data["puzzles"]:
        if not entry["semantic_valid"]:
            continue

        fpath = Path(__file__).resolve().parent.parent / entry["file"]
        puzzle = load_puzzle_from_json(fpath)
        assert isinstance(puzzle, Puzzle)
        assert puzzle.grid_size == entry["grid_size"]

        report = validate_puzzle(puzzle)
        assert report.clues_truth is entry["clues_truth"]
        assert report.uniqueness.value == entry["expected_uniqueness"]
        assert report.playability.value == entry["expected_playability"]
        assert report.playability_steps == entry["expected_steps"]

        if entry["expected_playability"] == "SOLVABLE_NO_GUESS":
            assert report.is_playable_no_guess is True
            assert report.playability_steps == entry["expected_steps"]


def test_invalid_false_clue_fixture_rejected():
    """Verify that puzzle_invalid_false_clue.json fails loader with ValueError."""
    fpath = FIXTURES_DIR / "puzzle_invalid_false_clue.json"
    assert fpath.is_file()
    with pytest.raises(ValueError, match="evaluates to FALSE under the hidden solution"):
        load_puzzle_from_json(fpath)


def test_fixture_template_and_extension_coverage():
    """Verify that the suite of fixtures covers all 6 templates, both extensions, and regions."""
    p_3x3 = load_puzzle_from_json(FIXTURES_DIR / "puzzle_3x3_progressive.json")
    p_4x4 = load_puzzle_from_json(FIXTURES_DIR / "puzzle_4x4_progressive.json")

    all_clues = list(p_3x3.clues.values()) + list(p_4x4.clues.values())

    clue_types = {type(c) for c in all_clues}
    assert FactClue in clue_types, "FACT clue missing"
    assert SameClue in clue_types, "SAME clue missing"
    assert DifferentClue in clue_types, "DIFFERENT clue missing"
    assert ExactlyClue in clue_types, "EXACTLY clue missing"
    assert AtMostClue in clue_types, "AT_MOST clue missing"
    assert AtLeastClue in clue_types, "AT_LEAST clue missing"
    assert ParityClue in clue_types, "PARITY clue missing (Extension 1)"

    # Check extension 2: COMMON_NEIGHBORS
    common_neighbors_found = False
    region_types = set()
    for c in all_clues:
        if hasattr(c, "region"):
            region_types.add(type(c.region))
            if isinstance(c.region, CommonNeighborsRegion):
                common_neighbors_found = True

    assert common_neighbors_found, "COMMON_NEIGHBORS missing (Extension 2)"
    assert RowRegion in region_types, "ROW region missing"
    assert ColRegion in region_types, "COL region missing"
    assert ExplicitRegion in region_types, "EXPLICIT region missing"
    assert NeighborsRegion in region_types, "NEIGHBORS region missing"


def test_manifest_coverage_metadata_matches_fixture_json():
    """Manifest template, region, and extension claims match every raw fixture."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for entry in manifest["puzzles"]:
        fixture_path = Path(__file__).resolve().parent.parent / entry["file"]
        raw = json.loads(fixture_path.read_text(encoding="utf-8"))
        clues = [character["clue"] for character in raw["characters"]]
        templates = {clue["type"].strip().upper() for clue in clues}
        regions = {
            clue["region"]["type"].strip().upper()
            for clue in clues
            if "region" in clue
        }
        extensions = templates.intersection({"PARITY"})
        if "COMMON_NEIGHBORS" in regions:
            extensions.add("COMMON_NEIGHBORS")

        assert set(entry["templates_used"]) == templates
        assert set(entry["regions_used"]) == regions
        assert set(entry["extensions_used"]) == extensions


def test_invalid_fixture_manifest_classification():
    """The false-clue fixture is schema-valid but semantically has zero models."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entry = next(
        item for item in manifest["puzzles"]
        if item["id"] == "puzzle_invalid_false_clue"
    )
    assert entry["schema_valid"] is True
    assert entry["semantic_valid"] is False
    assert entry["clues_truth"] is False
    assert entry["expected_uniqueness"] == "ZERO"
    assert entry["expected_playability"] == "SKIPPED"


def test_3x3_progressive_solves_in_8_steps():
    """Test 3x3 progressive puzzle step progression."""
    from griductive.game.controller import GameController, AutoSolveStatus

    puzzle = load_puzzle_from_json(FIXTURES_DIR / "puzzle_3x3_progressive.json")
    ctrl = GameController(puzzle)
    report = ctrl.auto_solve()
    assert report.status == AutoSolveStatus.SOLVED
    assert report.total_steps == 8
    assert ctrl.is_solved is True


def test_4x4_progressive_solves_in_15_steps():
    """Test 4x4 progressive puzzle step progression."""
    from griductive.game.controller import GameController, AutoSolveStatus

    puzzle = load_puzzle_from_json(FIXTURES_DIR / "puzzle_4x4_progressive.json")
    ctrl = GameController(puzzle)
    report = ctrl.auto_solve()
    assert report.status == AutoSolveStatus.SOLVED
    assert report.total_steps == 15
    assert ctrl.is_solved is True


def test_stalled_puzzles_terminate_as_stalled():
    """Test that stalled puzzles terminate with STALLED status."""
    from griductive.game.controller import GameController, AutoSolveStatus

    # 3x3 stalled
    p3 = load_puzzle_from_json(FIXTURES_DIR / "puzzle_3x3_stalled.json")
    c3 = GameController(p3)
    rep3 = c3.auto_solve()
    assert rep3.status == AutoSolveStatus.STALLED
    assert not c3.is_solved

    # 4x4 stalled
    p4 = load_puzzle_from_json(FIXTURES_DIR / "puzzle_4x4_stalled.json")
    c4 = GameController(p4)
    rep4 = c4.auto_solve()
    assert rep4.status == AutoSolveStatus.STALLED
    assert not c4.is_solved
