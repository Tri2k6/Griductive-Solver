"""Unit and integration tests for T18 — Experiments and Performance Evaluation."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import pytest

from griductive.analysis.experiments import (
    ExperimentResult,
    ExperimentRunner,
    ExperimentSuiteReport,
    TimingStats,
    main as exp_main,
)
import sys
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
import main as cli_main

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "puzzles" / "manifest.json"


def test_timing_stats_calculations():
    """Verify TimingStats statistical calculations."""
    samples = [0.010, 0.012, 0.011, 0.013, 0.014]
    stats = TimingStats.from_samples(samples)

    assert pytest.approx(stats.mean_s, rel=1e-3) == 0.012
    assert pytest.approx(stats.mean_ms, rel=1e-3) == 12.0
    assert stats.min_s == 0.010
    assert stats.max_s == 0.014
    assert stats.std_s > 0
    assert len(stats.samples_s) == 5

    # Empty samples guard
    empty = TimingStats.from_samples([])
    assert empty.mean_s == 0.0
    assert empty.std_s == 0.0
    assert empty.samples_s == ()


def test_run_single_puzzle_progressive():
    """Verify running an experiment on a progressively solvable puzzle."""
    runner = ExperimentRunner(manifest_path=MANIFEST_PATH, repetitions=3)
    entry = {
        "id": "puzzle_3x3_progressive",
        "file": "puzzles/puzzle_3x3_progressive.json",
        "grid_size": 3,
        "description": "Progressive 3x3 test",
        "expected_steps": 8,
        "semantic_valid": True,
    }

    res = runner.run_puzzle(entry, repetitions=3)
    assert isinstance(res, ExperimentResult)
    assert res.puzzle_id == "puzzle_3x3_progressive"
    assert res.grid_size == 3
    assert res.is_valid_format is True
    assert res.clues_truth is True
    assert res.uniqueness == "UNIQUE"
    assert res.solution_count == 1
    assert res.playability == "SOLVABLE_NO_GUESS"
    assert res.terminal_status == "SOLVED"
    assert res.total_steps == 8
    assert res.expected_steps == 8

    # Variables & Clauses
    assert res.initial_prim_vars == 9
    assert res.final_prim_vars == 9
    assert res.final_aux_vars == 33
    assert res.final_vars == 42
    assert res.final_clauses == 85

    # DPLL Metrics & Determinism
    assert res.total_sat_calls == 76
    assert res.dpll_decisions == 0  # Pure unit propagation
    assert res.dpll_propagations == 610
    assert res.dpll_backtracks == 0
    assert res.counters_deterministic is True
    assert res.repetitions == 3
    assert len(res.e2e_runtime.samples_s) == 3
    assert res.e2e_runtime.mean_ms > 0

    # Step details
    assert len(res.steps_detail) == 8
    assert res.steps_detail[0].step_number == 1
    assert res.steps_detail[0].target_cell == "B1"
    assert res.steps_detail[0].target_verdict == "INNOCENT"
    assert res.steps_detail[7].step_number == 8


def test_run_stalled_and_ambiguous_puzzles():
    """Verify that stalled and ambiguous puzzles are measured without error."""
    runner = ExperimentRunner(manifest_path=MANIFEST_PATH, repetitions=2)

    # 1. Stalled 3x3
    entry_stalled = {
        "id": "puzzle_3x3_stalled",
        "file": "puzzles/puzzle_3x3_stalled.json",
        "grid_size": 3,
        "description": "Stalled 3x3 test",
        "expected_steps": 1,
        "semantic_valid": True,
    }
    res_stalled = runner.run_puzzle(entry_stalled, repetitions=2)
    assert res_stalled.uniqueness == "UNIQUE"
    assert res_stalled.playability == "STALLED"
    assert res_stalled.terminal_status == "STALLED"
    assert res_stalled.total_steps == 1
    assert res_stalled.dpll_decisions > 0  # Branching occurred to test UNKNOWN cards
    assert res_stalled.counters_deterministic is True

    # 2. Ambiguous 3x3
    entry_ambiguous = {
        "id": "puzzle_3x3_ambiguous",
        "file": "puzzles/puzzle_3x3_ambiguous.json",
        "grid_size": 3,
        "description": "Ambiguous 3x3 test",
        "expected_steps": 0,
        "semantic_valid": True,
    }
    res_ambiguous = runner.run_puzzle(entry_ambiguous, repetitions=2)
    assert res_ambiguous.uniqueness == "MULTIPLE"
    assert res_ambiguous.solution_count == 2
    assert res_ambiguous.playability == "STALLED"
    assert res_ambiguous.terminal_status == "STALLED"
    assert res_ambiguous.total_steps == 0
    assert res_ambiguous.counters_deterministic is True


def test_run_invalid_puzzle_gracefully():
    """Verify invalid puzzle fixture is captured without crashing the suite."""
    runner = ExperimentRunner(manifest_path=MANIFEST_PATH)
    entry_invalid = {
        "id": "puzzle_invalid_false_clue",
        "file": "puzzles/puzzle_invalid_false_clue.json",
        "grid_size": 3,
        "description": "Invalid false clue fixture",
        "expected_steps": 0,
        "semantic_valid": False,
    }
    res = runner.run_puzzle(entry_invalid)
    assert res.is_valid_format is False
    assert res.clues_truth is False
    assert res.terminal_status == "INVALID_PUZZLE"
    assert res.playability == "SKIPPED"
    assert res.error_message is not None
    assert "evaluates to FALSE" in res.error_message


def test_full_suite_run_and_exports(tmp_path):
    """Verify running the full suite and exporting CSV, JSON, and Markdown summaries."""
    runner = ExperimentRunner(manifest_path=MANIFEST_PATH, repetitions=2)
    suite = runner.run_suite(repetitions=2)

    assert isinstance(suite, ExperimentSuiteReport)
    assert len(suite.results) == 6
    assert suite.platform_info.get("python_version") is not None
    assert suite.settings.get("repetitions") == 2

    # Export files
    csv_file, json_file, md_file = runner.run_and_export(
        manifest_path=MANIFEST_PATH,
        output_dir=tmp_path,
        repetitions=2,
    )

    assert csv_file.is_file()
    assert json_file.is_file()
    assert md_file.is_file()

    # 1. Validate CSV
    with csv_file.open(encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 6
        p3_prog = next(r for r in reader if r["puzzle_id"] == "puzzle_3x3_progressive")
        assert p3_prog["terminal_status"] == "SOLVED"
        assert p3_prog["steps_taken"] == "8"
        assert p3_prog["total_sat_calls"] == "76"
        assert p3_prog["dpll_decisions"] == "0"
        assert p3_prog["counters_deterministic"] == "True"

    # 2. Validate JSON
    with json_file.open(encoding="utf-8") as f:
        data = json.load(f)
        assert data["manifest_file"] == str(MANIFEST_PATH)
        assert len(data["results"]) == 6
        r0 = data["results"][0]
        assert r0["puzzle_id"] == "puzzle_3x3_progressive"
        assert "steps_detail" in r0
        assert len(r0["steps_detail"]) == 8

    # 3. Validate Markdown Summary
    md_text = md_file.read_text(encoding="utf-8")
    assert "# Griductive Solver — Experimental Performance Report" in md_text
    assert "puzzle_3x3_progressive" in md_text
    assert "puzzle_4x4_progressive" in md_text
    assert "Theoretical Complexity vs. Empirical Measurements" in md_text


def test_cli_experiment_subcommand(tmp_path):
    """Verify running experiments via CLI entry point."""
    rc = cli_main.main(["experiment", "--repetitions", "2", "--output-dir", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "results.csv").is_file()
    assert (tmp_path / "results.json").is_file()
    assert (tmp_path / "summary.md").is_file()
