# Review and Adversarial Audit Report — Milestone M1 (T03 Review)

**Agent**: teamwork_reviewer_m1_2 (Roles: reviewer, critic)  
**Date**: 2026-11-04  
**Working Directory**: `.agents/teamwork/teamwork_reviewer_m1_2/`  
**Milestone**: M1 (Audit & Repair T01–T03)  
**Target Scope**: T03 (Independent clue semantics) in `src/griductive/semantics.py` and `tests/test_semantics.py`  
**Handoff Type**: Hard (Review Complete)

---

## Review Summary

**Verdict**: **APPROVE**  
**Integrity Assessment**: **NO INTEGRITY VIOLATIONS DETECTED**  
- No hardcoded test results embedded in source code.
- No dummy or facade implementations; pure algorithmic logic throughout.
- No shortcuts or external SAT/CNF tool delegation.
- No fabricated verification outputs or self-certifying bypasses.
- Independent verification and adversarial stress tests all passed.

---

## 1. Observation

1. **Compilation Check**:
   - Command: `python -m compileall -q src tests`
   - Exit code: `0`
   - Output: Clean compilation, zero syntax or byte-compile errors.

2. **Test Suite Execution**:
   - Command: `pytest -q tests/test_semantics.py`
   - Result: `29 passed in 0.08s`
   - Command: `pytest -q`
   - Result: `73 passed in 0.09s` (full repository test suite passing with 0 warnings/failures).

3. **Strict Value Typing Inspection (`_get_is_criminal`)**:
   - In `src/griductive/semantics.py` (lines 27–41):
     ```python
     def _get_is_criminal(
         cell: CellId, assignment: Mapping[CellId, Status | bool]
     ) -> bool:
         """Return True if cell is Criminal, False if Innocent."""
         if cell not in assignment:
             raise KeyError(f"Cell {cell} is missing from complete assignment")
         val = assignment[cell]
         if isinstance(val, Status):
             return val == Status.CRIMINAL
         if isinstance(val, bool):
             return val
         raise TypeError(
             f"Invalid assignment value type for cell {cell}: {type(val).__name__} ({val!r}). Expected Status or bool."
         )
     ```
     - Direct `bool(val)` coercion was completely removed.
     - Accepts only `Status` enum or actual `bool` instances (`True` / `False`).
     - Raises `TypeError` for ints (`0`, `1`, `-1`), floats (`1.0`, `0.0`), strings (`"CRIMINAL"`, `"INNOCENT"`), `None`, and arbitrary objects.

4. **Cardinality `k` Validation Inspection (`evaluate_cardinality`)**:
   - In `src/griductive/semantics.py` (lines 85–95):
     ```python
     if isinstance(clue.k, bool) or not isinstance(clue.k, int):
         raise TypeError(
             f"Cardinality k must be an integer, got {type(clue.k).__name__}: {clue.k!r}"
         )
     region_cells = resolve_region(clue.region, grid_size)
     region_len = len(region_cells)

     if clue.k < 0 or clue.k > region_len:
         raise ValueError(
             f"k={clue.k} out of bounds for region of size {region_len} (0..{region_len})"
         )
     ```
     - Handles Python's type hierarchy where `issubclass(bool, int) is True` by explicitly testing `isinstance(clue.k, bool)` first.
     - Strictly rejects `bool` (`True`, `False`), non-integer numerics (`1.0`), strings, and `None` with `TypeError`.
     - Validates integer bounds `0 <= clue.k <= region_len`, raising `ValueError` for out-of-bound `k`.

5. **Complete Assignment Verification Inspection (`validate_complete_assignment`)**:
   - In `src/griductive/semantics.py` (lines 126–152):
     ```python
     def validate_complete_assignment(
         assignment: Mapping[CellId, Status | bool],
         grid_size: int,
     ) -> None:
         """Validate that assignment is complete, within bounds, and contains only valid types."""
         if grid_size < 1:
             raise ValueError(f"grid_size must be >= 1: {grid_size}")

         for idx in range(grid_size * grid_size):
             expected_cell = CellId.from_index(idx, grid_size)
             if expected_cell not in assignment:
                 raise KeyError(f"Cell {expected_cell} is missing from complete assignment")

         for cell in assignment.keys():
             if not isinstance(cell, CellId) or not cell.is_valid_for(grid_size):
                 raise ValueError(f"Assignment contains invalid or out-of-bounds cell: {cell!r}")

         for cell, val in assignment.items():
             if isinstance(val, Status):
                 continue
             if isinstance(val, bool):
                 continue
             raise TypeError(
                 f"Invalid assignment value type for cell {cell}: {type(val).__name__} ({val!r}). Expected Status or bool."
             )
     ```
     - Enforces `grid_size >= 1`.
     - Scans `0 <= idx < N*N` in row-major order; raises `KeyError` naming the very first missing cell.
     - Rejects non-`CellId` keys and out-of-bounds coordinates with `ValueError`.
     - Enforces value types for all cells, raising `TypeError` for non-Status/non-bool values.
     - Called automatically at the beginning of `evaluate_clue`.

6. **Zero CNF/DPLL Dependencies**:
   - Module imports in `src/griductive/semantics.py`:
     - Standard library: `from __future__ import annotations`, `typing.Iterable`, `typing.Mapping`.
     - Internal modules: `griductive.model` and `griductive.regions`.
     - Zero imports of `cnf.py`, `dpll.py`, `sat`, or external solvers.
     - AST test in `tests/test_semantics.py::TestValidationAndIsolation::test_semantics_module_does_not_import_cnf_or_dpll` parses AST and asserts no import nodes contain `cnf`, `dpll`, or `sat`.

---

## 2. Logic Chain

1. **Strict Value Typing & Coercion Elimination**:
   - `_get_is_criminal` previously allowed silent truthiness coercion via `bool(val)`. In the repaired code, the check is partitioned into:
     - `isinstance(val, Status)`: evaluates `val == Status.CRIMINAL` (returns pure `bool`).
     - `isinstance(val, bool)`: returns `val`.
     - Fallthrough: unconditionally raises `TypeError`.
   - Because `bool` is checked specifically and `int` does not inherit from `bool`, `isinstance(1, bool)` is `False`, ensuring integers `0` and `1` are rejected as required.
2. **Cardinality `k` Type and Bounds Checking**:
   - In Python, `isinstance(True, int)` is `True`. To correctly reject boolean values passed as `k`, `isinstance(clue.k, bool)` is checked first.
   - Non-int types (e.g. `float(1.0)`) fail `isinstance(clue.k, int)`. Both cases raise `TypeError`.
   - The boundary `0 <= clue.k <= region_len` is checked immediately after resolving the region, raising `ValueError` on violations.
3. **Completeness & Deterministic Ordering**:
   - `validate_complete_assignment` generates expected `CellId` from index `0` to `N*N - 1`. `CellId.from_index` maps indices row-major (`A1`, `B1`, ..., `A2`, `B2`, ...). The first missing cell in this sequence is raised via `KeyError`, fulfilling the specification.
   - Any extraneous keys (such as `D1` in a 3x3 grid) or non-`CellId` objects are rejected with `ValueError`.
4. **Architectural Isolation**:
   - `semantics.py` acts as a pure oracle against a complete assignment. It relies strictly on `model.py` and `regions.py`.
   - This architectural independence enables offline puzzle validation, sanity testing, and test fixtures without coupling to the CNF encoder or DPLL solver.

---

## 3. Adversarial Stress Testing Results

Adversarial evaluation script tested corner cases and attack scenarios:

| Scenario / Attack Vector | Input | Expected Outcome | Actual Outcome | Status |
|---|---|---|---|---|
| Truthiness coercion bypass | `assignment[A1] = 1`, `0`, `-1` | `TypeError` | `TypeError` raised | PASS |
| Non-status object values | `assignment[A1] = "CRIMINAL"`, `1.0`, `None`, `{}` | `TypeError` | `TypeError` raised | PASS |
| Cardinality bool spoofing | `clue.k = True`, `clue.k = False` | `TypeError` | `TypeError` raised | PASS |
| Cardinality float spoofing | `clue.k = 1.0`, `0.0` | `TypeError` | `TypeError` raised | PASS |
| Cardinality negative bound | `clue.k = -1` on row region | `ValueError` | `ValueError` raised | PASS |
| Cardinality overflow bound | `clue.k = 4` on 3x3 row (size 3) | `ValueError` | `ValueError` raised | PASS |
| Empty region cardinality | `k = 0` on empty common-neighbors | Evaluates `True` | Evaluates `True` | PASS |
| Empty region non-zero | `k = 1` on empty common-neighbors | `ValueError` (1 > 0) | `ValueError` raised | PASS |
| Missing cell order check | Both A1 and B1 missing from assignment | `KeyError: Cell A1 is missing...` | Reports A1 | PASS |
| Out-of-bounds cell key | `assignment[CellId('D1')]` on 3x3 | `ValueError: out-of-bounds cell` | `ValueError` raised | PASS |
| Non-CellId mapping key | `assignment['A1'] = Status.INNOCENT` | `ValueError: invalid or out-of-bounds cell` | `ValueError` raised | PASS |
| Invalid grid size | `validate_complete_assignment(..., 0)` | `ValueError: grid_size must be >= 1` | `ValueError` raised | PASS |

**Overall Risk Assessment**: **LOW**

---

## 4. Caveats

- **No Caveats**: All acceptance criteria for T03 in `ORIGINAL_REQUEST.md`, `TASKS.md`, `docs/requirements.md`, and `docs/assignment.pdf` have been completely satisfied.
- The semantics module is completely self-contained and ready for integration with T04 (`io.py`) and offline validation tooling (`validation.py`).

---

## 5. Conclusion

**Verdict: APPROVE**

The implementation of T03 in `src/griductive/semantics.py` and test suite in `tests/test_semantics.py`:
1. Correctly eliminates all `bool(val)` coercion, enforcing strict `Status` or `bool` types and raising `TypeError` for other types.
2. Correctly rejects `bool` and non-integer types for cardinality `k` and strictly validates bounds `0 <= k <= |region|`.
3. Fully implements `validate_complete_assignment`, verifying all N*N cells in row-major order, rejecting out-of-bounds/invalid keys, and checking value types.
4. Maintains zero dependencies on `cnf.py` or `dpll.py`.
5. Passes all tests (`python -m compileall -q src tests` and `pytest -q`).

Milestone M1 repairs for T03 are verified, sound, and ready for T04.

---

## 6. Verification Method

To independently reproduce and verify this review:
1. `python -m compileall -q src tests` (Must exit 0 with no errors)
2. `pytest -q tests/test_semantics.py` (Must report 29 passed)
3. `pytest -q` (Must report 73 passed)
4. Inspect `src/griductive/semantics.py` lines 27–41 (`_get_is_criminal`), lines 85–95 (`evaluate_cardinality`), and lines 126–152 (`validate_complete_assignment`).
