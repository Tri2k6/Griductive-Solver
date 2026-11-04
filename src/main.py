"""Griductive Solver — Main CLI and GUI launcher.

Usage:
  python src/main.py [gui] [--puzzle PATH]
  python src/main.py validate <puzzle_path>
  python src/main.py solve <puzzle_path> [--max-steps N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to sys.path so griductive package imports seamlessly
src_dir = Path(__file__).resolve().parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from griductive.game.controller import GameController
from griductive.game.io import load_puzzle_from_json
from griductive.analysis.validation import validate_puzzle


def cmd_gui(args: argparse.Namespace) -> int:
    """Launch the interactive Tkinter GUI."""
    from griductive.ui.gui import launch_gui

    puzzle_path = args.puzzle
    if puzzle_path:
        p = Path(puzzle_path)
        if not p.is_file():
            print(f"Error: Puzzle file not found: {puzzle_path}", file=sys.stderr)
            return 1
    else:
        # Default puzzle
        default_p = Path(__file__).resolve().parent.parent / "puzzles" / "puzzle_3x3_progressive.json"
        if default_p.is_file():
            puzzle_path = str(default_p)

    print(f"Starting Griductive GUI with puzzle: {puzzle_path}...")
    try:
        app = launch_gui(puzzle_path=puzzle_path)
        assert app.root is not None
        app.root.mainloop()
        return 0
    except Exception as e:
        print(f"Error launching GUI: {e}", file=sys.stderr)
        return 1


def cmd_validate(args: argparse.Namespace) -> int:
    """Run offline validation on a puzzle file."""
    p_path = Path(args.puzzle_path)
    if not p_path.is_file():
        print(f"Error: Puzzle file not found: {args.puzzle_path}", file=sys.stderr)
        return 1

    print(f"Validating puzzle: {p_path}...")
    try:
        puzzle = load_puzzle_from_json(p_path)
    except Exception as e:
        print(f"FAILED loader validation: {e}")
        return 1

    report = validate_puzzle(puzzle)
    print("\n--- Puzzle Validation Report ---")
    print(f"Is Valid Overall:       {report.is_valid}")
    print(f"Clues Truth:            {report.clues_truth}")
    if report.false_clue_ids:
        print(f"False Clue IDs:         {', '.join(report.false_clue_ids)}")
    print(f"Solution Uniqueness:    {report.uniqueness.value} (found {report.solution_count} solution(s))")
    print(f"Playability (No Guess): {report.playability.value}")
    print(f"Progressive Steps:      {report.playability_steps}")
    print("Messages:")
    for msg in report.messages:
        print(f"  * {msg}")

    return 0 if report.is_valid else 2


def cmd_solve(args: argparse.Namespace) -> int:
    """Run the deductive auto-solver and print the step trace."""
    p_path = Path(args.puzzle_path)
    if not p_path.is_file():
        print(f"Error: Puzzle file not found: {args.puzzle_path}", file=sys.stderr)
        return 1

    print(f"Loading puzzle: {p_path}...")
    try:
        puzzle = load_puzzle_from_json(p_path)
    except Exception as e:
        print(f"Loader error: {e}", file=sys.stderr)
        return 1

    ctrl = GameController(puzzle)
    print(f"Initial face-up cards: {sorted(str(c) for c in ctrl.public_state.revealed_cells)}")
    print(f"Running auto-solve (max_steps={args.max_steps})...\n")

    report = ctrl.auto_solve(max_steps=args.max_steps)

    for step in report.steps:
        print(
            f"Step {step.step_number:02d}: Cell {step.target_cell} -> "
            f"{step.target_verdict.value:<8} | Revealed clue: {step.revealed_clue_id:<6} | "
            f"SAT calls: {step.step_sat_calls} (Dec: {step.step_metrics.decisions}, "
            f"Prop: {step.step_metrics.propagations}, Backtracks: {step.step_metrics.backtracks})"
        )

    print("\n--- Auto Solve Summary ---")
    print(f"Status:            {report.status.value}")
    print(f"Total Steps:       {report.total_steps}")
    print(f"Total SAT Calls:   {report.total_sat_calls}")
    print(f"Total Decisions:   {report.aggregate_metrics.decisions}")
    print(f"Total Props:       {report.aggregate_metrics.propagations}")
    print(f"Total Backtracks:  {report.aggregate_metrics.backtracks}")
    print(f"Total Runtime:     {report.aggregate_metrics.runtime:.4f}s")
    print(f"Message:           {report.message}")

    return 0


def cmd_experiment(args: argparse.Namespace) -> int:
    """Run reproducible experiments and export results."""
    from griductive.analysis.experiments import ExperimentRunner

    runner = ExperimentRunner(manifest_path=args.manifest, repetitions=args.repetitions)
    print(f"Running Griductive experiment suite (repetitions={args.repetitions})...")

    csv_p, json_p, md_p = runner.run_and_export(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        repetitions=args.repetitions,
    )

    print("Experiments completed successfully:")
    print(f"  * CSV Data:     {csv_p}")
    print(f"  * JSON Data:    {json_p}")
    print(f"  * Summary MD:   {md_p}")

    if args.print_summary:
        print("\n" + md_p.read_text(encoding="utf-8"))

    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="griductive",
        description="Griductive Solver — Deductive Logic Game and SAT Solver",
    )
    subparsers = parser.add_subparsers(dest="command")

    # GUI command
    gui_parser = subparsers.add_parser("gui", help="Launch the interactive desktop GUI")
    gui_parser.add_argument("--puzzle", "-p", type=str, default=None, help="Path to puzzle JSON file")

    # Validate command
    val_parser = subparsers.add_parser("validate", help="Validate a puzzle file offline")
    val_parser.add_argument("puzzle_path", type=str, help="Path to puzzle JSON file")

    # Solve command
    solve_parser = subparsers.add_parser("solve", help="Auto-solve a puzzle from command line")
    solve_parser.add_argument("puzzle_path", type=str, help="Path to puzzle JSON file")
    solve_parser.add_argument("--max-steps", type=int, default=None, help="Maximum deduction steps")

    # Experiment command
    exp_parser = subparsers.add_parser("experiment", help="Run reproducible experiments and performance evaluation")
    exp_parser.add_argument("--manifest", type=str, default=None, help="Path to puzzle manifest JSON")
    exp_parser.add_argument("--output-dir", type=str, default="experiments", help="Output directory for reports")
    exp_parser.add_argument("--repetitions", "-r", type=int, default=5, help="Number of timing repetitions per puzzle")
    exp_parser.add_argument("--print-summary", action="store_true", help="Print summary table to console")

    # If no arguments provided, default to gui
    if not argv:
        args = parser.parse_args(["gui"])
    else:
        args = parser.parse_args(argv)

    if args.command == "gui":
        return cmd_gui(args)
    elif args.command == "validate":
        return cmd_validate(args)
    elif args.command == "solve":
        return cmd_solve(args)
    elif args.command == "experiment":
        return cmd_experiment(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
