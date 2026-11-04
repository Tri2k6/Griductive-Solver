# Forensic Audit Report: Milestone M2 (T04 & T05)

**Work Product**: Milestone M2 (`src/griductive/io.py`, `src/griductive/engine.py`, `schema/puzzle_schema_v1.json`, `tests/fixtures/puzzle_3x3_valid.json`, `tests/test_io.py`, `tests/test_engine.py`, `TASKS.md`, `progress.md`)  
**Profile**: General Project (Demo Mode)  
**Verdict**: **CLEAN**

---

## 1. Observation

### 1.1 Direct Source Code Inspection
- **`src/griductive/io.py`**:
  - Defines `PUZZLE_SCHEMA_VERSION = "1.0"` (line 33).
  - Implements dynamic reference resolution `_resolve_reference` (lines 36–69) resolving character names and coordinates, detecting out-of-bounds cells, empty strings, and type mismatches without hardcoding test-specific names.
  - Implements region parsing `_parse_region` (lines 71–170) covering `ROW`, `COL`, `NEIGHBORS`, `EXPLICIT`, and `COMMON_NEIGHBORS`.
  - Implements clue parsing `_parse_clue` (lines 172–332) validating all templates (`FACT`, `SAME`, `DIFFERENT`, `EXACTLY`, `AT_LEAST`, `AT_MOST`, `PARITY`), detecting self-comparisons (`cell_a == cell_b`), enforcing strict integer cardinality `k` (lines 282–283), and checking bounds against dynamically resolved regions.
  - Implements `load_puzzle_from_dict` (lines 334–490) validating grid dimensions ($N \ge 2$), exact cell coverage ($N \times N$), unique names and coordinates, and performing offline semantic truth checking (lines 476–481) via `semantics.evaluate_clue`.
  - Imports: Only Python standard library (`json`, `pathlib.Path`, `typing.Any`, `typing.Mapping`) and internal modules (`griductive.model`, `griductive.regions`, `griductive.semantics`).
- **`src/griductive/engine.py`**:
  - Implements `GameEngine` (lines 15–160) managing private state `_puzzle`, `_revealed_cells`, and `_revision`.
  - Implements `public_state` property (lines 52–96) and aliases `get_public_state()` / `public_view()`. Face-down cards strictly have `is_revealed=False`, `status=None`, `clue=None`. Characters are sorted alphabetically; revealed clues are sorted in row-major order.
  - Implements guarded `reveal` (lines 106–154) validating cell bounds and re-reveal attempts, checking verdict against private ground-truth `self._puzzle.solution`. On incorrect verdict, raises `ValueError` (lines 145–148) while leaving `_revealed_cells`, `_revision`, and `public_state` untouched.
  - Implements `restart` (lines 155–159) resetting revealed cells to initial face-up cards and revision to 0.
  - Imports: Only Python standard library (`__future__.annotations`) and internal `griductive.model`.
- **`schema/puzzle_schema_v1.json`**:
  - Full Draft-07 JSON schema enforcing structure, types, coordinate regex, and enum constraints.
- **`tests/fixtures/puzzle_3x3_valid.json`**:
  - Fully populated 3x3 puzzle with 9 characters, distinct coordinates, valid clue templates (`FACT`, `SAME`, `DIFFERENT`, `EXACTLY`, `AT_LEAST`, `AT_MOST`, `PARITY`), and 2 initial face-up cards (`A1`, `B2`).

### 1.2 Anti-Cheating & Integrity Checks
- **Hardcoded test returns**: None. All functions accept generic data structures and compute results algorithmically.
- **Facade implementations**: None. All classes and functions implement genuine business logic; no empty stubs or dummy return values exist.
- **Test tautologies**: `grep -rn "assert True\|assert 1 == 1" tests/` returned 0 matches. Every assertion in `tests/test_io.py` and `tests/test_engine.py` checks specific concrete values, return types, exceptions, or state invariance.
- **Pre-populated verification artifacts**: `find . -name '*.log' -o -name '*result*' -o -name '*output*'` returned 0 files.
- **Third-party library usage**: `grep -rn "^import \|^from " src/` confirmed only standard library imports. No external SAT or logic frameworks used.
- **Scope limitation**: Verified `TASKS.md` has only T01–T05 marked `[x]`, while T06–T21 remain `[ ]`. Directory `src/griductive/` contains only `model.py`, `regions.py`, `semantics.py`, `io.py`, and `engine.py`. No files for later milestones (`cnf.py`, `dpll.py`, `logic.py`, `controller.py`, `gui.py`, `experiments.py`) exist. Work strictly halted after T05.
- **Repository integrity**: `docs/assignment.pdf` is untouched (SHA-256: `d8825f309fea21aa65af38266efe1b86763d2e666d73a973709d63f728765742`, 6 pages, 356,386 bytes). Git status shows no deleted or modified assignment documents.

### 1.3 Independent Execution Results
- `python -m compileall -q src tests` exited with code 0.
- `pytest -q` output:
  ```
  ........................................................................ [ 67%]
  ...................................                                      [100%]
  107 passed in 0.12s
  ```
- `python -m flake8 --select=F src/griductive/io.py src/griductive/engine.py tests/test_io.py tests/test_engine.py` exited with code 0 (zero lint errors).

---

## 2. Logic Chain

1. **Integrity Mode & Ground-Truth Constraints**:
   - `ORIGINAL_REQUEST.md` specifies Demo Mode: standard library permitted, no third-party libraries for core functionality, no copying open-source code, no fabricated test results, private engine boundary maintained, work halted after T05.
2. **Evaluation of Source Code**:
   - Both `io.py` and `engine.py` rely entirely on Python standard library modules (`json`, `pathlib`, `typing`) and internal domain models.
   - All logic for JSON parsing, schema validation, reference resolution, offline truth checking, and game state mutation is genuine, original code.
3. **Public/Private Boundary & Immutability**:
   - `GameEngine` encapsulates `_puzzle` and never leaks unrevealed statuses or clues. Public snapshots return immutable mappings (`MappingProxyType`) and tuples.
   - Rejection semantics guarantee that incorrect manual calls or invalid inputs do not mutate the engine's internal state or increment its revision.
4. **Independent Test Execution**:
   - Running the test suite independently confirmed 107 passing tests covering unit and edge cases across model, regions, semantics, I/O, and game engine.
   - Adversarial testing confirmed deep immutability, case-insensitive duplicate coordinate rejection, and rejection of boolean/float values for integer cardinality `k`.
5. **Scope Compliance**:
   - Milestone M2 strictly ends with Task T05. No downstream tasks (T06–T21) have been started or checked off in `TASKS.md`.

---

## 3. Caveats

- No caveats. The implementation adheres strictly to the architectural constraints, integrity rules, and acceptance criteria of Milestone M2.

---

## 4. Conclusion

The work products delivered for Milestone M2 (`io.py`, `engine.py`, schema, fixture, and accompanying test suites) pass all integrity, structural, architectural, and behavioral checks without violation.

**Final Verdict**: **CLEAN**

---

## 5. Verification Method

To reproduce and independently verify this forensic audit verdict:

1. **Build & Syntax Verification**:
   ```bash
   python -m compileall -q src tests
   ```
   (Must complete with zero output and exit code 0.)

2. **Test Suite Execution**:
   ```bash
   pytest -q
   ```
   (Must report 107 passed in ~0.15s with zero failures.)

3. **Check Code Integrity & Lints**:
   ```bash
   python -m flake8 --select=F src/griductive/io.py src/griductive/engine.py tests/test_io.py tests/test_engine.py
   ```
   (Must report 0 lint errors.)

4. **Document Integrity**:
   ```bash
   sha256sum docs/assignment.pdf
   ```
   (Must match `d8825f309fea21aa65af38266efe1b86763d2e666d73a973709d63f728765742`.)
