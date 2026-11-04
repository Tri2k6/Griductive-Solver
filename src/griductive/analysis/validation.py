"""Offline puzzle validation: semantic truth checks, uniqueness checking, and playability simulation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from griductive.domain.model import (
    AtLeastClue,
    AtMostClue,
    CellId,
    DifferentClue,
    ExactlyClue,
    FactClue,
    ParityClue,
    Puzzle,
    SameClue,
    Status,
)
from griductive.domain.semantics import evaluate_clue
from griductive.solver.cnf import (
    AuxAllocator,
    CNFFormula,
    PrimaryVarMap,
    encode_at_least,
    encode_at_most,
    encode_different,
    encode_exactly,
    encode_fact,
    encode_parity,
    encode_same,
)
from griductive.solver.dpll import solve_dpll
from griductive.game.engine import GameEngine
from griductive.game.controller import AutoSolveStatus, GameController


class UniquenessResult(str, Enum):
    """Result of complete-clue solution uniqueness check."""

    ZERO = "ZERO"          # No solution satisfies all clues + initial face-up cards (UNSAT)
    UNIQUE = "UNIQUE"      # Exactly one solution satisfies all clues + initial face-up cards
    MULTIPLE = "MULTIPLE"  # Two or more distinct solutions satisfy all clues + initial face-up cards


class PlayabilityResult(str, Enum):
    """Result of the progressive no-guess deduction simulation."""

    SOLVABLE_NO_GUESS = "SOLVABLE_NO_GUESS"  # Fully solved from initial face-up cards without guessing
    STALLED = "STALLED"                      # Stalls because no unresolved cards are logically forced
    INCONSISTENT = "INCONSISTENT"            # Initial or intermediate public knowledge base is unsatisfiable
    SKIPPED = "SKIPPED"                      # Playability simulation skipped due to false clues


@dataclass(frozen=True)
class ValidationReport:
    """Comprehensive offline validation report for a puzzle."""

    is_valid: bool
    clues_truth: bool
    false_clue_ids: tuple[str, ...]
    uniqueness: UniquenessResult
    solution_count: int
    first_solution: Mapping[CellId, Status] | None = None
    second_solution: Mapping[CellId, Status] | None = None
    is_playable_no_guess: bool = False
    playability: PlayabilityResult = PlayabilityResult.STALLED
    playability_steps: int = 0
    messages: tuple[str, ...] = ()


def check_clues_truth(puzzle: Puzzle) -> tuple[bool, tuple[str, ...]]:
    """Verify that every clue in the puzzle evaluates to True against the complete solution.

    Uses independent semantic evaluators (semantics.evaluate_clue) without CNF or DPLL.
    Returns (all_true, tuple_of_false_clue_ids).
    """
    false_clue_ids: list[str] = []
    for cell, clue in sorted(puzzle.clues.items(), key=lambda item: item[0]):
        is_true = evaluate_clue(clue, puzzle.solution, puzzle.grid_size)
        if not is_true:
            false_clue_ids.append(clue.clue_id)

    return len(false_clue_ids) == 0, tuple(false_clue_ids)


def check_solution_uniqueness(
    puzzle: Puzzle,
) -> tuple[
    UniquenessResult,
    int,
    Mapping[CellId, Status] | None,
    Mapping[CellId, Status] | None,
]:
    """Check solution uniqueness across the complete clue set + initial face-up cards.

    Strict rules:
    - Encodes initial face-up cards as unit clauses.
    - Encodes ALL clues in puzzle.clues.
    - NEVER injects hidden solution units for face-down cards.
    - If first query is UNSAT -> ZERO solutions.
    - If first query is SAT: adds a single blocking clause over PRIMARY variables (1..N²)
      and solves again:
      - If second query is UNSAT -> UNIQUE (exactly 1 solution).
      - If second query is SAT -> MULTIPLE (2 or more distinct solutions).
    """
    pmap = PrimaryVarMap(puzzle.grid_size)
    aux = AuxAllocator(pmap)
    clauses: list[tuple[int, ...]] = []

    # 1. Initial face-up cards as unit clauses
    for cell in sorted(puzzle.initial_face_up):
        var = pmap.cell_to_var(cell)
        status = puzzle.solution[cell]
        clauses.append((var if status == Status.CRIMINAL else -var,))

    # 2. Encode all clues in the puzzle
    for cell, clue in sorted(puzzle.clues.items(), key=lambda item: item[0]):
        if isinstance(clue, FactClue):
            clauses.extend(encode_fact(clue, pmap, aux))
        elif isinstance(clue, SameClue):
            clauses.extend(encode_same(clue, pmap, aux))
        elif isinstance(clue, DifferentClue):
            clauses.extend(encode_different(clue, pmap, aux))
        elif isinstance(clue, AtMostClue):
            clauses.extend(encode_at_most(clue, pmap, aux, puzzle.grid_size))
        elif isinstance(clue, AtLeastClue):
            clauses.extend(encode_at_least(clue, pmap, aux, puzzle.grid_size))
        elif isinstance(clue, ExactlyClue):
            clauses.extend(encode_exactly(clue, pmap, aux, puzzle.grid_size))
        elif isinstance(clue, ParityClue):
            clauses.extend(encode_parity(clue, pmap, aux, puzzle.grid_size))
        else:
            raise TypeError(f"Unknown clue type: {type(clue).__name__}")

    formula = CNFFormula(clauses=tuple(clauses), primary_map=pmap, num_aux=aux.num_aux)

    # First SAT query: find first satisfying model
    res1 = solve_dpll(formula)
    if not res1.is_sat or res1.model is None:
        return UniquenessResult.ZERO, 0, None, None

    # Reconstruct first primary assignment
    all_cells = [
        CellId.from_coords(r, c)
        for r in range(1, puzzle.grid_size + 1)
        for c in range(1, puzzle.grid_size + 1)
    ]
    sol1 = {
        cell: (Status.CRIMINAL if res1.model[pmap.cell_to_var(cell)] else Status.INNOCENT)
        for cell in all_cells
    }

    # Construct single blocking clause over PRIMARY variables only:
    # At least one primary variable must differ from sol1
    blocking_clause = tuple(
        -v if res1.model[v] else v for v in range(1, pmap.num_primary + 1)
    )

    formula2 = CNFFormula(
        clauses=formula.clauses + (blocking_clause,),
        primary_map=pmap,
        num_aux=formula.num_aux,
    )

    # Second SAT query: search for an alternative distinct primary assignment
    res2 = solve_dpll(formula2)
    if not res2.is_sat or res2.model is None:
        return UniquenessResult.UNIQUE, 1, sol1, None

    sol2 = {
        cell: (Status.CRIMINAL if res2.model[pmap.cell_to_var(cell)] else Status.INNOCENT)
        for cell in all_cells
    }
    return UniquenessResult.MULTIPLE, 2, sol1, sol2


def check_playability(puzzle: Puzzle) -> tuple[PlayabilityResult, int]:
    """Simulate autonomous no-guess deduction starting from initial face-up cards.

    Returns (playability_result, deduction_steps_taken).
    """
    engine = GameEngine(puzzle)
    controller = GameController(engine)
    report = controller.auto_solve()

    if report.status in (AutoSolveStatus.SOLVED, AutoSolveStatus.ALREADY_SOLVED):
        return PlayabilityResult.SOLVABLE_NO_GUESS, len(report.steps)
    elif report.status == AutoSolveStatus.INCONSISTENT:
        return PlayabilityResult.INCONSISTENT, len(report.steps)
    else:
        return PlayabilityResult.STALLED, len(report.steps)


def validate_puzzle(puzzle: Puzzle) -> ValidationReport:
    """Perform complete offline validation of a puzzle instance.

    Validates:
    1. Semantic truth: all clues are true under ground truth solution.
    2. Uniqueness: exactly one primary assignment satisfies all clues.
    3. Playability: whether puzzle is solvable progressively without guessing.
    """
    messages: list[str] = []

    # 1. Semantic truth check
    clues_truth, false_clues = check_clues_truth(puzzle)
    if not clues_truth:
        messages.append(
            f"Semantic truth failure: clues {', '.join(false_clues)} evaluate to False under the solution."
        )
        # Do not run unsafe progressive simulation after a false-clue condition has been established
        uniqueness, count, sol1, sol2 = check_solution_uniqueness(puzzle)
        if uniqueness == UniquenessResult.ZERO:
            messages.append("Uniqueness result: puzzle has ZERO satisfying solutions (UNSAT).")
        elif uniqueness == UniquenessResult.MULTIPLE:
            messages.append("Uniqueness result: puzzle has MULTIPLE distinct satisfying solutions.")
        else:
            messages.append("Uniqueness result: puzzle formula has one model (conflicts with solution due to false clues).")

        messages.append("Playability simulation skipped: puzzle contains false clue(s).")

        return ValidationReport(
            is_valid=False,
            clues_truth=False,
            false_clue_ids=false_clues,
            uniqueness=uniqueness,
            solution_count=count,
            first_solution=sol1,
            second_solution=sol2,
            is_playable_no_guess=False,
            playability=PlayabilityResult.SKIPPED,
            playability_steps=0,
            messages=tuple(messages),
        )

    messages.append("Semantic truth PASS: all clues are true under ground truth solution.")

    # 2. Uniqueness check
    uniqueness, count, sol1, sol2 = check_solution_uniqueness(puzzle)
    if uniqueness == UniquenessResult.ZERO:
        messages.append("Uniqueness failure: puzzle has ZERO satisfying solutions (UNSAT).")
    elif uniqueness == UniquenessResult.MULTIPLE:
        messages.append("Uniqueness failure: puzzle has MULTIPLE distinct satisfying solutions.")
    else:
        messages.append("Uniqueness PASS: puzzle has exactly ONE unique satisfying solution.")

    # 3. Playability check
    playability, steps = check_playability(puzzle)
    if playability == PlayabilityResult.SOLVABLE_NO_GUESS:
        if steps == 0:
            messages.append("Playability PASS: puzzle is initially solved with zero deduction steps required.")
        else:
            messages.append(
                f"Playability PASS: puzzle is fully solvable without guessing in {steps} steps."
            )
    elif playability == PlayabilityResult.STALLED:
        messages.append(
            f"Playability NOTICE: puzzle is stalled after {steps} step(s); cannot be solved progressively without guessing."
        )
    else:
        messages.append("Playability NOTICE: initial public knowledge base is inconsistent.")

    is_valid = clues_truth and (uniqueness == UniquenessResult.UNIQUE)
    is_playable = playability == PlayabilityResult.SOLVABLE_NO_GUESS

    return ValidationReport(
        is_valid=is_valid,
        clues_truth=clues_truth,
        false_clue_ids=false_clues,
        uniqueness=uniqueness,
        solution_count=count,
        first_solution=sol1,
        second_solution=sol2,
        is_playable_no_guess=is_playable,
        playability=playability,
        playability_steps=steps,
        messages=tuple(messages),
    )
