"""Analysis module for Griductive.

Contains offline puzzle validation (uniqueness, playability) and benchmarking experiments.
"""

from griductive.analysis.experiments import (
    ExperimentResult,
    ExperimentRunner,
    ExperimentSuiteReport,
    TimingStats,
    main,
)
from griductive.analysis.validation import (
    PlayabilityResult,
    UniquenessResult,
    ValidationReport,
    check_clues_truth,
    check_playability,
    check_solution_uniqueness,
    validate_puzzle,
)

__all__ = [
    # Validation
    "UniquenessResult",
    "PlayabilityResult",
    "ValidationReport",
    "check_clues_truth",
    "check_solution_uniqueness",
    "check_playability",
    "validate_puzzle",
    # Experiments
    "TimingStats",
    "ExperimentResult",
    "ExperimentSuiteReport",
    "ExperimentRunner",
    "main",
]
