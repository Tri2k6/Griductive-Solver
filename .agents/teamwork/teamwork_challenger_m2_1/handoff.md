# Handoff Report: Challenger M2-1 (Adversarial Probing of Puzzle I/O)

## 1. Observation

- Conducted exhaustive adversarial probing of `src/griductive/io.py` across all assignment dimensions: malformed schema versions, top-level keys, grid sizes, character count mismatches, coordinate geometry, name uniqueness, clue references and self-comparisons, cardinality k bounds, region boundaries, initial face-up constraints, and offline semantic truth validation.
- Authored test suite `tests/test_io_adversarial.py` containing 16 test functions with zero flake8 warnings (`python -m flake8 tests/test_io_adversarial.py` exited with 0).
- Ran compilation:
  `python3 -m compileall -q src tests` succeeded with returncode 0.
- Executed pytest suite:
  `pytest -q` resulted in `2 failed, 137 passed in 0.20s`:
  - 137 tests passed.
  - 2 test failures observed verbatim:
    ```
    FAILED tests/test_io_adversarial.py::test_clue_id_invalid_empty_or_falsy_rejected
    FAILED tests/test_io_adversarial.py::test_load_puzzle_from_json_string_and_empty
    ```

### Detailed Observations of Failures

1. **Failure 1: Silent Acceptance of Falsy Clue IDs (`src/griductive/io.py:190-197`)**
   - Code in `src/griductive/io.py`:
     ```python
     190:    clue_id_raw = clue_data.get("id") or clue_data.get("clue_id")
     191:    if clue_id_raw is not None:
     192:        if not isinstance(clue_id_raw, str) or not clue_id_raw.strip():
     193:            raise ValueError(f"Clue ID for cell {owner} must be a non-empty string, got {clue_id_raw!r}")
     194:        clue_id = clue_id_raw.strip()
     195:    else:
     196:        clue_id = f"c_{owner.name}"
     ```
   - Observed behavior:
     When a puzzle clue provides `"id": ""` (empty string), `0`, `False`, `[]`, or `{}`:
     `clue_data.get("id") or clue_data.get("clue_id")` evaluates to `None` because the boolean `or` operator short-circuits falsy values.
     Because `clue_id_raw` is `None`, line 191 (`if clue_id_raw is not None:`) evaluates to `False`. Lines 192–194 are skipped.
     Line 196 silently executes and auto-assigns `c_{owner.name}`.
     In contrast, truthy invalid IDs like `"id": 123` or `"id": "   "` evaluate to truthy values, reach line 192, and raise `ValueError`.
   - Verbatim pytest error:
     ```
     E Failed: DID NOT RAISE any of (ValueError, TypeError)
     ```

2. **Failure 2: Unhandled `IsADirectoryError` on Empty String / Path in `load_puzzle_from_json` (`src/griductive/io.py:498-505`)**
   - Code in `src/griductive/io.py`:
     ```python
     498:    elif isinstance(path_or_json, str):
     499:        stripped = path_or_json.strip()
     500:        if stripped.startswith("{"):
     501:            data = json.loads(stripped)
     502:        else:
     503:            p = Path(path_or_json)
     504:            content = p.read_text(encoding="utf-8")
     505:            data = json.loads(content)
     ```
   - Observed behavior:
     When `load_puzzle_from_json("")` is invoked with an empty string or whitespace, `stripped.startswith("{")` is `False`.
     `Path("")` resolves to the current working directory (`.`).
     Line 504 `p.read_text()` attempts to open `.` as a file and crashes with unhandled OS-level error:
     `IsADirectoryError: [Errno 21] Is a directory: '.'`
     Additionally, non-object JSON strings like `"[1, 2, 3]"` fall through to `Path("[1, 2, 3]").read_text()` and raise `FileNotFoundError`.

## 2. Logic Chain

1. *Clue ID Validation Contract*:
   - Observation 1 demonstrates that explicit empty string, integer `0`, and boolean `False` values for `"id"` are treated as though the `"id"` key were omitted altogether, bypassing non-empty string validation.
   - Inference: A validator must differentiate between an omitted optional key (which triggers a default value) and an explicitly provided invalid value (which must be rejected).
   - Conclusion: Line 190 in `src/griductive/io.py` contains a defect that silently accepts malformed clue IDs.

2. *Input Boundary Validation in `load_puzzle_from_json`*:
   - Observation 2 demonstrates that passing an empty string or whitespace to `load_puzzle_from_json` causes an unexpected `IsADirectoryError`.
   - Inference: Clean boundary validation requires verifying that a string input is non-empty before attempting filesystem operations, and rejecting empty input with `ValueError`.
   - Conclusion: Lines 498–505 in `src/griductive/io.py` leak low-level OS errors due to missing upfront string validation.

3. *Robustness of Other Components*:
   - 137 other unit and adversarial tests pass completely:
     - Top-level schema version checks reject unsupported versions (`"2.0"`, `None`, etc.).
     - Missing required top-level keys raise `ValueError`.
     - Invalid grid sizes (`bool`, floats, strings, `< 2`, negatives) raise `TypeError` or `ValueError`.
     - Character counts (`!= N*N`) raise `ValueError`.
     - Out-of-bounds coordinates and duplicate coordinates (including case-insensitive) raise `ValueError`.
     - Duplicate display names (including whitespace-stripped) raise `ValueError`.
     - Cross-character duplicate clue IDs raise `ValueError`.
     - Self-comparison in SAME and DIFFERENT (by name, coordinate, or mixed) raise `ValueError`.
     - Cardinality k type errors and out-of-bounds bounds raise `TypeError` and `ValueError`.
     - Geometric region bounds (ROW, COL, NEIGHBORS, EXPLICIT, COMMON_NEIGHBORS with same cell) raise `ValueError`.
     - `initial_face_up` checks reject empty, duplicates, and out-of-bounds cells.
     - Offline truth validation rejects false clues for all 6 core templates and 2 extension templates.
     - Puzzle objects and internal collections are deeply immutable and isolated from input dictionary mutations.

## 3. Caveats

- Challenger operates in review-only mode and does not modify implementation code in `src/`.
- All tests are codified in `tests/test_io_adversarial.py` adhering to layout rules.

## 4. Conclusion

**Verdict: REQUEST_CHANGES**

Worker M2 must repair the 2 confirmed defects in `src/griductive/io.py`:

1. **Fix Clue ID Key Inspection (Line 190)**:
   Check key presence explicitly rather than using boolean `or`:
   ```python
   if "id" in clue_data:
       clue_id_raw = clue_data["id"]
   elif "clue_id" in clue_data:
       clue_id_raw = clue_data["clue_id"]
   else:
       clue_id_raw = None
   ```
   Ensure `clue_id_raw is not None` checks that it is a non-empty string.

2. **Fix `load_puzzle_from_json` String Validation (Lines 498–505)**:
   Validate that `path_or_json.strip()` is non-empty before processing:
   ```python
   elif isinstance(path_or_json, str):
       stripped = path_or_json.strip()
       if not stripped:
           raise ValueError("Empty puzzle path or JSON string")
       if stripped.startswith("{"):
           data = json.loads(stripped)
       elif stripped.startswith("["):
           raise TypeError("Puzzle JSON must be an object/dict, got array/list")
       else:
           p = Path(path_or_json)
           if not p.is_file():
               raise FileNotFoundError(f"Puzzle file not found: {path_or_json}")
           content = p.read_text(encoding="utf-8")
           data = json.loads(content)
   ```

## 5. Verification Method

To independently reproduce and verify the findings:
1. Run `python3 -m compileall -q src tests` (must exit with 0).
2. Run `python3 -m flake8 tests/test_io_adversarial.py` (must report 0 errors).
3. Run `pytest -v tests/test_io_adversarial.py` (reproduces the 2 exact failures).
4. Run `pytest -q` (reports 2 failed, 137 passed).
