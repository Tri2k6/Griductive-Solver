# Handoff Report: Milestone M2 (T04: Puzzle I/O & T05: GameEngine)

## 1. Observation
- Verified starting state of prior milestone M1:
  - `model.py` and `semantics.py` already had defensive dictionary copying (`MappingProxyType(dict(...))`), strict type validation for assignments (`isinstance(val, (Status, bool))`), and integer validation for cardinality `k` (`not isinstance(k, bool) and isinstance(k, int)`).
  - Prior suite ran with `pytest -q`: `73 passed in 0.08s`.
- Implemented Task T04:
  - Created JSON schema `schema/puzzle_schema_v1.json` (Draft-07 specification).
  - Created `src/griductive/io.py` with `PUZZLE_SCHEMA_VERSION = "1.0"`, `load_puzzle_from_dict`, `load_puzzle_from_json`, and `validate_puzzle_data`.
  - Created minimal valid 3x3 fixture in `tests/fixtures/puzzle_3x3_valid.json` covering all six core templates (`FACT`, `SAME`, `DIFFERENT`, `EXACTLY`, `AT_LEAST`, `AT_MOST`) and both extensions (`PARITY`, `COMMON_NEIGHBORS`).
  - Implemented offline truth validation in `src/griductive/io.py` lines 384–390 invoking `semantics.evaluate_clue(clue, solution, grid_size)`.
  - Added 24 unit tests in `tests/test_io.py`.
- Implemented Task T05:
  - Created `src/griductive/engine.py` with `GameEngine`:
    - Private puzzle ownership (`_puzzle`, `_revealed_cells`, `_revision`).
    - Immutable public snapshot via `public_state` / `get_public_state()` / `public_view()`.
    - Guarded `reveal(cell, verdict)`: raises `ValueError` on wrong verdict, out-of-bounds cell, or re-revealing card, while leaving `_revealed_cells` and `_revision` unchanged.
    - Supported `restart()` resetting to initial face-up cards and revision 0.
  - Added 10 unit tests in `tests/test_engine.py`.
- Verified compilation and test suite:
  - `python -m compileall -q src tests` exited with code 0 (zero output).
  - `pytest -q` output:
    ```
    ........................................................................ [ 67%]
    ...................................                                      [100%]
    107 passed in 0.13s
    ```
  - `python -m flake8 --select=F src/griductive/io.py src/griductive/engine.py tests/test_io.py tests/test_engine.py` exited with code 0 (zero violations).
- Updated documentation and task tracker:
  - `TASKS.md`: Checked off T01, T03, T04, T05.
  - `progress.md`: Recorded audit pass of T01–T03 and completed implementation of T04 and T05.

## 2. Logic Chain
1. *T01–T03 Audit and Dependencies*:
   - Observation: Initial review identified 4 potential issues in T01 and T03, but inspecting `src/griductive/model.py` and `src/griductive/semantics.py` revealed that immutable mapping wrappers, invariant assertions, and integer type checks had already been repaired, passing 73 unit tests.
   - Deduction: T01–T03 dependencies are fully satisfied, permitting execution of T04 and T05.
2. *Task T04 Compliance*:
   - Observation: `io.py` parses coordinate strings, unique character names, profession, hidden statuses, and structured clues. Reference resolution handles both display names and coordinates, detecting self-comparison (`person_a == person_b`).
   - Observation: `io.py` verifies all clues against the hidden solution using `semantics.evaluate_clue`. In `test_offline_truth_validation_rejects_false_clue`, modifying a clue from INNOCENT to CRIMINAL raises `ValueError` with `"evaluates to FALSE under the hidden solution"`.
   - Deduction: T04 acceptance criteria are completely satisfied without leaking private solutions to public consumers.
3. *Task T05 Compliance*:
   - Observation: `GameEngine` stores `_puzzle` privately. `public_state` returns a `PublicState` where face-down cards have `is_revealed=False`, `status=None`, and `clue=None`.
   - Observation: In `test_rejected_reveal_wrong_verdict_leaves_state_unchanged`, attempting a wrong verdict on A2 raises `ValueError` and asserts `engine.revision == rev_before` and `engine.public_state == state_before`.
   - Observation: In `test_solve_and_restart`, sequentially revealing all 9 cards reaches `is_solved == True`, and `engine.restart()` restores initial face-up cards with `revision == 0`.
   - Deduction: T05 acceptance criteria are completely satisfied.

## 3. Caveats
- `io.py` validates that every clue is true under the puzzle's ground truth solution (semantic validity). Complete clue uniqueness checking (verifying whether there are 0, 1, or multiple models satisfying all clues) is assigned to T14 (`validation.py`), not T04.
- `GameEngine.restart()` resets `revision` to 0.

## 4. Conclusion
Tasks T04 and T05 are fully implemented, verified, and integrated into the project codebase. All 107 unit tests pass with zero errors, zero failures, and zero lint warnings.

## 5. Verification Method
- Independent command execution:
  1. `python -m compileall -q src tests` (must exit with code 0).
  2. `pytest -q` (must report 107 passed in ~0.15s).
  3. `python -m flake8 --select=F src/griductive/io.py src/griductive/engine.py tests/test_io.py tests/test_engine.py` (must report 0 errors).
- Files to inspect:
  - `src/griductive/io.py`
  - `src/griductive/engine.py`
  - `schema/puzzle_schema_v1.json`
  - `tests/fixtures/puzzle_3x3_valid.json`
  - `tests/test_io.py`
  - `tests/test_engine.py`
  - `TASKS.md`
  - `progress.md`
