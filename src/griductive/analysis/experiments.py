"""Performance evaluation and experimental pipeline for Griductive Solver (T18).

Provides reproducible measurement of:
- Primary and auxiliary variable counts, CNF clauses.
- SAT query counts, DPLL decisions, propagations, backtracks.
- Runtime (distinguishing solver DPLL runtime from end-to-end solving).
- Timing variability (mean, std dev, min, max across repetitions).
- Bounded per-puzzle wall-clock timeout and non-aborting failure row retention.
- Export to machine-readable CSV, JSON, and human-readable Markdown summary.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import datetime
import json
import multiprocessing
import os
from pathlib import Path
import platform
import statistics
import sys
import time
from typing import Any, Mapping, Sequence

from griductive.analysis.validation import validate_puzzle
from griductive.game.controller import AutoSolveReport, GameController
from griductive.game.io import load_puzzle_from_json
from griductive.solver.kb import build_knowledge_base


@dataclass(frozen=True)
class TimingStats:
    """Statistical summary of timing across repeated runs."""

    mean_s: float
    std_s: float
    min_s: float
    max_s: float
    samples_s: tuple[float, ...]

    @property
    def mean_ms(self) -> float:
        return self.mean_s * 1000.0

    @property
    def std_ms(self) -> float:
        return self.std_s * 1000.0

    @property
    def min_ms(self) -> float:
        return self.min_s * 1000.0

    @property
    def max_ms(self) -> float:
        return self.max_s * 1000.0

    @classmethod
    def from_samples(cls, samples: Sequence[float]) -> TimingStats:
        if not samples:
            return cls(mean_s=0.0, std_s=0.0, min_s=0.0, max_s=0.0, samples_s=())
        s_list = list(samples)
        m = statistics.mean(s_list)
        s = statistics.stdev(s_list) if len(s_list) > 1 else 0.0
        return cls(
            mean_s=m,
            std_s=s,
            min_s=min(s_list),
            max_s=max(s_list),
            samples_s=tuple(s_list),
        )


@dataclass(frozen=True)
class StepMetricRecord:
    """Detailed metric accounting for an individual deduction step."""

    step_number: int
    target_cell: str
    target_verdict: str
    revealed_clue_id: str
    active_clues_count: int
    step_sat_calls: int
    step_decisions: int
    step_propagations: int
    step_backtracks: int
    step_runtime_s: float


@dataclass(frozen=True)
class ExperimentResult:
    """Comprehensive performance and metric measurement result for a single puzzle fixture."""

    puzzle_id: str
    file_path: str
    grid_size: int
    description: str
    is_valid_format: bool
    clues_truth: bool
    uniqueness: str
    solution_count: int
    playability: str
    expected_steps: int
    terminal_status: str
    total_steps: int
    initial_vars: int
    initial_prim_vars: int
    initial_aux_vars: int
    initial_clauses: int
    final_vars: int
    final_prim_vars: int
    final_aux_vars: int
    final_clauses: int
    total_sat_calls: int
    dpll_decisions: int
    dpll_propagations: int
    dpll_backtracks: int
    dpll_runtime: TimingStats
    e2e_runtime: TimingStats
    repetitions: int
    counters_deterministic: bool
    steps_detail: tuple[StepMetricRecord, ...]
    error_message: str | None = None


@dataclass(frozen=True)
class ExperimentSuiteReport:
    """Complete experimental suite report covering all measured fixtures."""

    timestamp: str
    manifest_file: str
    results: tuple[ExperimentResult, ...]
    platform_info: Mapping[str, Any]
    settings: Mapping[str, Any]


def _run_puzzle_worker(
    connection: Any,
    manifest_path: str,
    entry: dict[str, Any],
    repetitions: int,
) -> None:
    """Execute a single puzzle benchmark in an isolated process for deadline enforcement."""
    try:
        runner = ExperimentRunner(manifest_path=manifest_path, repetitions=repetitions)
        res = runner._run_puzzle_direct(entry, repetitions=repetitions)
        connection.send((res, None))
    except Exception as exc:
        connection.send((None, f"{type(exc).__name__}: {exc}"))
    finally:
        connection.close()


class ExperimentRunner:
    """Orchestrates deterministic measurement and benchmarking of Griductive puzzles."""

    def __init__(
        self,
        manifest_path: str | Path | None = None,
        repetitions: int = 5,
        timeout_seconds: float = 30.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if manifest_path is None:
            manifest_path = Path(__file__).resolve().parents[3] / "puzzles" / "manifest.json"
        self.manifest_path = Path(manifest_path)
        self.repetitions = max(1, repetitions)
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _failure_result(
        entry: Mapping[str, Any],
        status: str,
        message: str,
    ) -> ExperimentResult:
        """Build a preserved failure/timeout row so no manifest case is dropped."""
        empty = TimingStats.from_samples(())
        grid_size = entry.get("grid_size")
        expected_steps = entry.get("expected_steps")
        return ExperimentResult(
            puzzle_id=str(entry.get("id", "unknown")),
            file_path=str(entry.get("file", "")),
            grid_size=grid_size if type(grid_size) is int else 0,
            description=str(entry.get("description", "")),
            is_valid_format=False,
            clues_truth=False,
            uniqueness="UNKNOWN",
            solution_count=0,
            playability="SKIPPED",
            expected_steps=expected_steps if type(expected_steps) is int else 0,
            terminal_status=status,
            total_steps=0,
            initial_vars=0,
            initial_prim_vars=0,
            initial_aux_vars=0,
            initial_clauses=0,
            final_vars=0,
            final_prim_vars=0,
            final_aux_vars=0,
            final_clauses=0,
            total_sat_calls=0,
            dpll_decisions=0,
            dpll_propagations=0,
            dpll_backtracks=0,
            dpll_runtime=empty,
            e2e_runtime=empty,
            repetitions=0,
            counters_deterministic=False,
            steps_detail=(),
            error_message=message,
        )

    def run_puzzle(
        self,
        entry: dict[str, Any],
        repetitions: int | None = None,
        *,
        manifest_path: str | Path | None = None,
    ) -> ExperimentResult:
        """Benchmark one puzzle within the configured wall-clock timeout.

        Use the supplied manifest to resolve relative puzzle paths when provided.
        """
        if not isinstance(entry, dict):
            return self._failure_result({}, "ERROR", "Manifest entry must be a JSON object.")
        for field in ("grid_size", "expected_steps"):
            if field in entry and type(entry[field]) is not int:
                return self._failure_result(entry, "ERROR", f"Manifest field '{field}' must be an integer.")

        reps = self.repetitions if repetitions is None else max(1, repetitions)
        source_manifest = self.manifest_path if manifest_path is None else Path(manifest_path)
        ctx = multiprocessing.get_context("spawn")
        parent_conn, child_conn = ctx.Pipe(duplex=False)
        proc = ctx.Process(
            target=_run_puzzle_worker,
            args=(child_conn, str(source_manifest), entry, reps),
        )
        proc.start()
        child_conn.close()
        try:
            if not parent_conn.poll(self.timeout_seconds):
                proc.terminate()
                return self._failure_result(
                    entry,
                    "TIMEOUT",
                    f"Exceeded wall-clock timeout of {self.timeout_seconds:g}s.",
                )
            try:
                result, error = parent_conn.recv()
            except EOFError:
                return self._failure_result(
                    entry,
                    "ERROR",
                    f"Worker exited unexpectedly without result (exitcode={proc.exitcode}).",
                )
            if error is not None:
                return self._failure_result(entry, "ERROR", error)
            assert result is not None
            return result
        finally:
            parent_conn.close()
            proc.join()

    def _run_puzzle_direct(
        self,
        entry: dict[str, Any],
        repetitions: int,
    ) -> ExperimentResult:
        """Measure a single puzzle directly inside the worker process."""
        reps = max(1, repetitions)
        puzzle_id = entry.get("id", "unknown")
        raw_file = entry.get("file", "")
        fpath = Path(raw_file)
        if not fpath.is_absolute():
            # Bundled manifests also use paths relative to the project root.
            for directory in (self.manifest_path.parent, self.manifest_path.parent.parent):
                candidate = directory / fpath
                if candidate.is_file():
                    fpath = candidate
                    break

        grid_size = entry.get("grid_size", 0)
        desc = entry.get("description", "")
        expected_steps = entry.get("expected_steps", 0)

        if not entry.get("semantic_valid", True):
            try:
                load_puzzle_from_json(fpath)
                err_msg = "Expected semantic validation rejection, but puzzle loaded successfully."
            except Exception as e:
                err_msg = str(e)

            return ExperimentResult(
                puzzle_id=puzzle_id,
                file_path=str(fpath),
                grid_size=grid_size,
                description=desc,
                is_valid_format=False,
                clues_truth=False,
                uniqueness="ZERO",
                solution_count=0,
                playability="SKIPPED",
                expected_steps=expected_steps,
                terminal_status="INVALID_PUZZLE",
                total_steps=0,
                initial_vars=0,
                initial_prim_vars=0,
                initial_aux_vars=0,
                initial_clauses=0,
                final_vars=0,
                final_prim_vars=0,
                final_aux_vars=0,
                final_clauses=0,
                total_sat_calls=0,
                dpll_decisions=0,
                dpll_propagations=0,
                dpll_backtracks=0,
                dpll_runtime=TimingStats(0.0, 0.0, 0.0, 0.0, ()),
                e2e_runtime=TimingStats(0.0, 0.0, 0.0, 0.0, ()),
                repetitions=0,
                counters_deterministic=True,
                steps_detail=(),
                error_message=err_msg,
            )

        puzzle = load_puzzle_from_json(fpath)
        val_report = validate_puzzle(puzzle)

        init_ctrl = GameController(puzzle)
        init_kb = build_knowledge_base(init_ctrl.public_state)
        init_prim = init_kb.num_primary
        init_aux = init_kb.num_aux
        init_vars = init_kb.num_vars
        init_clauses = init_kb.num_clauses

        e2e_samples: list[float] = []
        dpll_samples: list[float] = []
        baseline_report: AutoSolveReport | None = None
        final_kb_stats: tuple[int, int, int, int] = (0, 0, 0, 0)
        counters_match = True

        for r in range(reps):
            ctrl = GameController(puzzle)
            t_start = time.perf_counter()
            rep = ctrl.auto_solve()
            t_end = time.perf_counter()

            e2e_samples.append(t_end - t_start)
            dpll_samples.append(rep.aggregate_metrics.runtime)

            if r == 0:
                baseline_report = rep
                final_kb = build_knowledge_base(ctrl.public_state)
                final_kb_stats = (
                    final_kb.num_vars,
                    final_kb.num_primary,
                    final_kb.num_aux,
                    final_kb.num_clauses,
                )
            else:
                assert baseline_report is not None
                if (
                    rep.status != baseline_report.status
                    or rep.total_steps != baseline_report.total_steps
                    or rep.total_sat_calls != baseline_report.total_sat_calls
                    or rep.aggregate_metrics.decisions != baseline_report.aggregate_metrics.decisions
                    or rep.aggregate_metrics.propagations != baseline_report.aggregate_metrics.propagations
                    or rep.aggregate_metrics.backtracks != baseline_report.aggregate_metrics.backtracks
                ):
                    counters_match = False

        assert baseline_report is not None

        step_records = tuple(
            StepMetricRecord(
                step_number=s.step_number,
                target_cell=str(s.target_cell),
                target_verdict=s.target_verdict.value,
                revealed_clue_id=s.revealed_clue_id,
                active_clues_count=len(s.active_clue_ids),
                step_sat_calls=s.step_sat_calls,
                step_decisions=s.step_metrics.decisions,
                step_propagations=s.step_metrics.propagations,
                step_backtracks=s.step_metrics.backtracks,
                step_runtime_s=s.step_metrics.runtime,
            )
            for s in baseline_report.steps
        )

        return ExperimentResult(
            puzzle_id=puzzle_id,
            file_path=str(fpath),
            grid_size=puzzle.grid_size,
            description=desc,
            is_valid_format=True,
            clues_truth=val_report.clues_truth,
            uniqueness=val_report.uniqueness.value,
            solution_count=val_report.solution_count,
            playability=val_report.playability.value,
            expected_steps=expected_steps,
            terminal_status=baseline_report.status.value,
            total_steps=baseline_report.total_steps,
            initial_vars=init_vars,
            initial_prim_vars=init_prim,
            initial_aux_vars=init_aux,
            initial_clauses=init_clauses,
            final_vars=final_kb_stats[0],
            final_prim_vars=final_kb_stats[1],
            final_aux_vars=final_kb_stats[2],
            final_clauses=final_kb_stats[3],
            total_sat_calls=baseline_report.total_sat_calls,
            dpll_decisions=baseline_report.aggregate_metrics.decisions,
            dpll_propagations=baseline_report.aggregate_metrics.propagations,
            dpll_backtracks=baseline_report.aggregate_metrics.backtracks,
            dpll_runtime=TimingStats.from_samples(dpll_samples),
            e2e_runtime=TimingStats.from_samples(e2e_samples),
            repetitions=reps,
            counters_deterministic=counters_match,
            steps_detail=step_records,
            error_message=None,
        )

    def run_suite(
        self,
        manifest_path: str | Path | None = None,
        repetitions: int | None = None,
    ) -> ExperimentSuiteReport:
        """Run the full experiment suite across all puzzles in the manifest."""
        m_path = self.manifest_path if manifest_path is None else Path(manifest_path)
        if not m_path.is_file():
            raise FileNotFoundError(f"Manifest not found: {m_path}")

        reps = self.repetitions if repetitions is None else repetitions
        data = json.loads(m_path.read_text(encoding="utf-8"))
        puzzles = data.get("puzzles", [])

        results = tuple(
            self.run_puzzle(entry, repetitions=reps, manifest_path=m_path)
            for entry in puzzles
        )

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        platform_meta = {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "cpu_count": os.cpu_count() or 1,
        }
        settings_meta = {
            "repetitions": reps,
            "timeout_seconds": self.timeout_seconds,
            "manifest": str(m_path),
        }

        return ExperimentSuiteReport(
            timestamp=now_str,
            manifest_file=str(m_path),
            results=results,
            platform_info=platform_meta,
            settings=settings_meta,
        )

    def export_csv(self, report: ExperimentSuiteReport, out_path: str | Path) -> Path:
        """Export experiment results as a clean, machine-readable CSV table."""
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "puzzle_id",
            "grid_size",
            "is_valid_format",
            "clues_truth",
            "uniqueness",
            "solution_count",
            "playability",
            "terminal_status",
            "steps_taken",
            "expected_steps",
            "initial_prim_vars",
            "initial_aux_vars",
            "initial_total_vars",
            "initial_clauses",
            "final_prim_vars",
            "final_aux_vars",
            "final_total_vars",
            "final_clauses",
            "total_sat_calls",
            "dpll_decisions",
            "dpll_propagations",
            "dpll_backtracks",
            "dpll_runtime_mean_ms",
            "dpll_runtime_std_ms",
            "e2e_runtime_mean_ms",
            "e2e_runtime_std_ms",
            "e2e_runtime_min_ms",
            "e2e_runtime_max_ms",
            "repetitions",
            "counters_deterministic",
            "error_message",
        ]

        with target.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in report.results:
                writer.writerow(
                    {
                        "puzzle_id": r.puzzle_id,
                        "grid_size": r.grid_size,
                        "is_valid_format": r.is_valid_format,
                        "clues_truth": r.clues_truth,
                        "uniqueness": r.uniqueness,
                        "solution_count": r.solution_count,
                        "playability": r.playability,
                        "terminal_status": r.terminal_status,
                        "steps_taken": r.total_steps,
                        "expected_steps": r.expected_steps,
                        "initial_prim_vars": r.initial_prim_vars,
                        "initial_aux_vars": r.initial_aux_vars,
                        "initial_total_vars": r.initial_vars,
                        "initial_clauses": r.initial_clauses,
                        "final_prim_vars": r.final_prim_vars,
                        "final_aux_vars": r.final_aux_vars,
                        "final_total_vars": r.final_vars,
                        "final_clauses": r.final_clauses,
                        "total_sat_calls": r.total_sat_calls,
                        "dpll_decisions": r.dpll_decisions,
                        "dpll_propagations": r.dpll_propagations,
                        "dpll_backtracks": r.dpll_backtracks,
                        "dpll_runtime_mean_ms": f"{r.dpll_runtime.mean_ms:.3f}",
                        "dpll_runtime_std_ms": f"{r.dpll_runtime.std_ms:.3f}",
                        "e2e_runtime_mean_ms": f"{r.e2e_runtime.mean_ms:.3f}",
                        "e2e_runtime_std_ms": f"{r.e2e_runtime.std_ms:.3f}",
                        "e2e_runtime_min_ms": f"{r.e2e_runtime.min_ms:.3f}",
                        "e2e_runtime_max_ms": f"{r.e2e_runtime.max_ms:.3f}",
                        "repetitions": r.repetitions,
                        "counters_deterministic": r.counters_deterministic,
                        "error_message": r.error_message or "",
                    }
                )

        return target

    def export_json(self, report: ExperimentSuiteReport, out_path: str | Path) -> Path:
        """Export comprehensive hierarchical JSON data including per-step breakdown."""
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "timestamp": report.timestamp,
            "manifest_file": report.manifest_file,
            "platform_info": dict(report.platform_info),
            "settings": dict(report.settings),
            "results": [asdict(r) for r in report.results],
        }

        with target.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        return target

    @classmethod
    def generate_summary_markdown(cls, report: ExperimentSuiteReport) -> str:
        """Generate human-readable Markdown summary report with dynamic tables and analysis."""
        lines = [
            "# Griductive Solver — Experimental Performance Report",
            "",
            f"- **Execution Timestamp:** `{report.timestamp}`",
            f"- **Platform:** `{report.platform_info.get('system')} {report.platform_info.get('release')} ({report.platform_info.get('machine')})`",
            f"- **Python Version:** `{report.platform_info.get('python_version')}`",
            f"- **Timing Repetitions:** `{report.settings.get('repetitions')} runs per puzzle`",
            f"- **Per-Puzzle Wall-Clock Timeout:** `{report.settings.get('timeout_seconds')}s`",
            "",
            "## 1. Summary Metrics Table",
            "",
            "| Puzzle ID | Grid | Uniqueness | Playability | Status | Steps | Prim / Aux | Clauses | SAT Calls | Dec | Prop | Back | DPLL Time (ms) | E2E Time (ms) |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]

        for r in report.results:
            if not r.is_valid_format:
                lines.append(
                    f"| `{r.puzzle_id}` | {r.grid_size}×{r.grid_size} | {r.uniqueness} | {r.playability} | `{r.terminal_status}` | - | - | - | - | - | - | - | - | - |"
                )
            else:
                lines.append(
                    "".join(
                        [
                            f"| `{r.puzzle_id}` | {r.grid_size}×{r.grid_size} | {r.uniqueness} | {r.playability} | `{r.terminal_status}` | ",
                            f"{r.total_steps}/{r.expected_steps} | {r.final_prim_vars} / {r.final_aux_vars} | {r.final_clauses} | ",
                            f"{r.total_sat_calls} | {r.dpll_decisions} | {r.dpll_propagations} | {r.dpll_backtracks} | ",
                            f"{r.dpll_runtime.mean_ms:.2f} ± {r.dpll_runtime.std_ms:.2f} | ",
                            f"{r.e2e_runtime.mean_ms:.2f} ± {r.e2e_runtime.std_ms:.2f} |",
                        ]
                    )
                )

        measured = [r for r in report.results if r.repetitions > 0]
        solved = [r for r in report.results if r.terminal_status == "SOLVED"]
        stalled = [r for r in report.results if r.terminal_status == "STALLED"]
        failed = [
            r for r in report.results
            if r.terminal_status in {"INVALID_PUZZLE", "TIMEOUT", "ERROR", "INCONSISTENT"}
        ]
        det_count = sum(1 for r in measured if r.counters_deterministic)

        size_summaries: list[str] = []
        for size in sorted({r.grid_size for r in solved}):
            group = [r for r in solved if r.grid_size == size]
            avg_e2e = statistics.mean(r.e2e_runtime.mean_ms for r in group)
            avg_dpll = statistics.mean(r.dpll_runtime.mean_ms for r in group)
            avg_calls = statistics.mean(r.total_sat_calls for r in group)
            label = f"{size}×{size}" + (" stress cases" if size >= 5 else "")
            size_summaries.append(
                f"  - **{label} ({len(group)} solved puzzle(s)):** mean SAT calls = `{avg_calls:.1f}`, "
                f"mean DPLL time = `{avg_dpll:.2f} ms`, mean end-to-end time = `{avg_e2e:.2f} ms`."
            )

        lines.extend(
            [
                "",
                "## 2. Key Experimental Findings and Analysis",
                "",
                "### A. Determinism & Accounting Verification",
                f"- Deterministic search counters verified on `{det_count}/{len(measured)}` measured cases (`total_sat_calls`, `dpll_decisions`, `dpll_propagations`, `dpll_backtracks`, `total_steps` invariant across all repetitions).",
                f"- Overall manifest breakdown (`{len(report.results)}` total cases): `{len(solved)}` solved without guessing, `{len(stalled)}` halted cleanly as `STALLED` without guessing, and `{len(failed)}` retained as invalid/error/timeout diagnostic rows.",
                "",
                "### B. Progressive Deduction, Stalled States & Retained Failure/Timeout Rows",
                "- **Progressively Solvable Puzzles (`SOLVED`):** Every hidden card was proved strictly via refutation (`UNSAT` under opposite temporary assumption) before reveal.",
                "- **Stalled & Ambiguous Puzzles (`STALLED`):** Unique-but-stalled fixtures (`UNIQUE`) and under-constrained fixtures (`MULTIPLE`) both terminated safely without guessing once neither `C_i` nor `¬C_i` was entailed.",
            ]
        )
        if failed:
            lines.append("- **Retained Failure / Timeout / Invalid Cases (never omitted from exports):**")
            for r in failed:
                lines.append(
                    f"  - `{r.puzzle_id}` (`{r.terminal_status}`): {r.error_message or 'Recorded diagnostic failure.'}"
                )

        lines.extend(
            [
                "",
                "### C. Theoretical Complexity vs. Empirical Measurements",
                "- **Theoretical Bound:** Worst-case DPLL search over $V = N^2 + N_{\\text{aux}}$ variables is $\\mathcal{O}(2^V)$, and each deduction wave issues up to $2U + 1$ SAT queries for $U \\le N^2$ unresolved cards.",
                "- **Empirical Scaling Across Grid Sizes:**",
                *size_summaries,
                "- **Timing Convention:** Per-puzzle wall-clock timeout bounds worker execution, while reported `e2e_runtime` and `dpll_runtime` measure pure solving repetitions excluding subprocess spawn and offline uniqueness validation.",
            ]
        )

        return "\n".join(lines) + "\n"

    @classmethod
    def export_summary_markdown(cls, report: ExperimentSuiteReport, out_path: str | Path) -> Path:
        """Export the human-readable Markdown summary to disk."""
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = cls.generate_summary_markdown(report)
        target.write_text(content, encoding="utf-8")
        return target

    def run_and_export(
        self,
        manifest_path: str | Path | None = None,
        output_dir: str | Path | None = None,
        repetitions: int | None = None,
    ) -> tuple[Path, Path, Path]:
        """Execute the entire suite and export CSV, JSON, and Markdown summaries."""
        if output_dir is None:
            out_dir = Path(__file__).resolve().parents[3] / "experiments"
        else:
            out_dir = Path(output_dir)

        out_dir.mkdir(parents=True, exist_ok=True)
        report = self.run_suite(manifest_path=manifest_path, repetitions=repetitions)

        csv_path = out_dir / "results.csv"
        json_path = out_dir / "results.json"
        md_path = out_dir / "summary.md"

        self.export_csv(report, csv_path)
        self.export_json(report, json_path)
        self.export_summary_markdown(report, md_path)

        return (csv_path, json_path, md_path)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for running experiments."""
    import argparse

    parser = argparse.ArgumentParser(description="Griductive Solver — Experiment Runner")
    parser.add_argument("--manifest", type=str, default=None, help="Path to puzzle manifest JSON")
    parser.add_argument("--output-dir", type=str, default="experiments", help="Output directory for reports")
    parser.add_argument(
        "--repetitions", "-r", type=int, default=5, help="Number of timing repetitions per puzzle"
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="Per-puzzle wall-clock timeout in seconds"
    )
    parser.add_argument("--print-summary", action="store_true", help="Print summary table to console")

    args = parser.parse_args(argv)

    runner = ExperimentRunner(
        manifest_path=args.manifest,
        repetitions=args.repetitions,
        timeout_seconds=args.timeout,
    )
    print(
        f"Running Griductive experiment suite (repetitions={args.repetitions}, timeout={args.timeout}s)..."
    )

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


if __name__ == "__main__":
    sys.exit(main())
