## 2026-11-04T12:32:52Z
You are the Implementation Worker for Milestone M2 (T04: Puzzle I/O & T05: GameEngine).
Your working directory is: .agents/teamwork/teamwork_worker_m2/

MANDATORY FIRST STEP:
Read ORIGINAL_REQUEST.md at:
/mnt/windowdata/Uninversity Data/Curriculum/HocKy5/Cơ sở trí tuệ nhân tạo/Griductive-Solver/.agents/teamwork/ORIGINAL_REQUEST.md
Also read AGENTS.md, TASKS.md, progress.md, docs/requirements.md, docs/architecture.md, and docs/assignment.pdf (§3.1, §3.2, §4.1, §4.2, §4.4).
Inspect the completed M1 implementation in src/griductive/model.py, src/griductive/regions.py, and src/griductive/semantics.py.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

EXCLUSIVE FILE OWNERSHIP:
You own:
- src/griductive/io.py
- src/griductive/engine.py
- tests/test_io.py
- tests/test_engine.py
- tests/fixtures/ (and any subdirectories/files for fixtures)
- TASKS.md (update checkboxes for completed tasks T01, T03, T04, T05)
- progress.md (update progress log with verified results)

IMPLEMENTATION SPECIFICATIONS:

### 1. Task T04: Specify and Load Puzzle Files (src/griductive/io.py, fixtures, tests/test_io.py)
- **JSON Format & Schema**:
  - `schema_version`: e.g. "1.0"
  - `grid_size`: integer N >= 2
  - `characters`: list of N*N objects with fields:
    - `cell`: coordinate string (e.g. "A1")
    - `name`: unique character display name (e.g. "Alice")
    - `profession`: string (e.g. "Doctor")
    - `status`: "CRIMINAL" or "INNOCENT"
    - `clue`: JSON object for the character's clue
  - `initial_face_up`: list of coordinate strings (e.g. ["A1", "B2"])
- **Clue Formats**:
  - `FACT`: `{"type": "FACT", "target": "B1" | "Bob", "status": "CRIMINAL" | "INNOCENT"}`
  - `SAME`: `{"type": "SAME", "person_a": ..., "person_b": ...}`
  - `DIFFERENT`: `{"type": "DIFFERENT", "person_a": ..., "person_b": ...}`
  - `EXACTLY`: `{"type": "EXACTLY", "k": int, "region": {...}}`
  - `AT_LEAST`: `{"type": "AT_LEAST", "k": int, "region": {...}}`
  - `AT_MOST`: `{"type": "AT_MOST", "k": int, "region": {...}}`
  - `PARITY`: `{"type": "PARITY", "parity": "EVEN" | "ODD", "region": {...}}`
  - Regions:
    - `ROW`: `{"type": "ROW", "row": int}`
    - `COL`: `{"type": "COL", "col": "A"}`
    - `NEIGHBORS`: `{"type": "NEIGHBORS", "center": "B2"}`
    - `EXPLICIT`: `{"type": "EXPLICIT", "cells": ["A1", "B2"]}`
    - `COMMON_NEIGHBORS`: `{"type": "COMMON_NEIGHBORS", "cell_a": "A1", "cell_b": "C3"}`
- **Validation Pipeline**:
  - Validate JSON structure and schema keys.
  - Validate `grid_size >= 2` and `len(characters) == grid_size * grid_size`.
  - Validate every coordinate `1..N` x `1..N` is covered with no duplicates.
  - Validate unique character names.
  - Resolve character name references in FACT/SAME/DIFFERENT to `CellId`, ensuring target cell exists and rejecting self-comparison (`person_a == person_b`).
  - Validate regions via `resolve_region(region, grid_size)`.
  - Validate `k` is integer and `0 <= k <= len(region_cells)`.
  - Validate `initial_face_up` is a non-empty subset of valid grid cells.
  - **Offline Truth Validation**: Using `semantics.evaluate_clue`, check that EVERY clue evaluates to `True` under the puzzle's `solution`. If any clue evaluates to `False`, reject the puzzle as invalid/contradictory!
  - Return private, immutable `Puzzle(grid_size, characters, solution, clues, initial_face_up)`.
- **Functions in `io.py`**:
  - `load_puzzle_from_dict(data: dict) -> Puzzle`
  - `load_puzzle_from_json(path_or_json: str | Path) -> Puzzle`
  - `validate_puzzle_data(data: dict) -> None`
- **Fixtures**:
  - Provide minimal valid 3x3 puzzle fixture (e.g. `tests/fixtures/puzzle_3x3_valid.json`).
  - Provide invalid fixture variants or parameterized tests for bad coordinates, duplicate cells, duplicate names, false clues, out-of-bounds k, etc.
- **Tests**: `tests/test_io.py`.

### 2. Task T05: Implement Game Engine (src/griductive/engine.py, tests/test_engine.py)
- **`GameEngine` Class**:
  - Constructor `GameEngine(puzzle: Puzzle)`:
    - Stores `_puzzle: Puzzle` privately.
    - Initializes `_revealed_cells: set[CellId] = set(puzzle.initial_face_up)`.
    - Initializes `_revision: int = 0`.
  - **Properties**:
    - `grid_size -> int`: returns `_puzzle.grid_size`.
    - `revision -> int`: returns `_revision`.
    - `public_state -> PublicState` (or `get_public_state()`):
      - Constructs and returns a valid immutable `PublicState`.
      - Characters sorted alphabetically by name.
      - Revealed cards have `is_revealed=True`, status and clue populated from `_puzzle`.
      - Face-down cards have `is_revealed=False`, `status=None`, `clue=None`.
      - `known_statuses` contains only revealed cards.
      - `revealed_clues` contains only revealed cards' clues, sorted deterministically in row-major order of owner cell.
    - `is_solved -> bool`: returns `len(_revealed_cells) == len(_puzzle.characters)`.
  - **Operations**:
    - `reveal(cell: CellId, verdict: Status) -> tuple[Status, Clue]`:
      - Checks `cell` exists in grid.
      - Checks `cell not in _revealed_cells` (cannot re-reveal already revealed card).
      - Checks `verdict == self._puzzle.solution[cell]`.
      - If invalid, already revealed, or `verdict` does not match the hidden solution: raises `ValueError` (or specific exception). Critically: `_revealed_cells`, state, and `_revision` remain UNCHANGED.
      - If correct: adds `cell` to `_revealed_cells`, increments `_revision`, returns `(status, clue)`.
    - `restart() -> PublicState`:
      - Resets `_revealed_cells = set(self._puzzle.initial_face_up)`.
      - Increments `_revision` (or resets) so public state reflects initial view.
      - Returns fresh `public_state`.
- **Tests**: `tests/test_engine.py`:
  - Test initial state exposes exactly initial face-up cards and keeps all unrevealed cards hidden.
  - Test valid reveal exposes card and updates revision.
  - Test invalid reveal / incorrect verdict raises error and leaves state and revision untouched.
  - Test restart restores initial face-up state.
  - Test solve condition.

### 3. Updates to Checklist & Progress Log:
- Update `TASKS.md`: check off T01, T03, T04, T05 with verified evidence.
- Update `progress.md`: record audit pass for T01-T03, completion of T04 and T05, test commands and outcomes.

### 4. Verification:
- Run `python -m compileall -q src tests`
- Run `pytest -q`
Ensure ALL tests pass with zero errors, zero warnings.

Deliverables:
- Write your completion report to `.agents/teamwork/teamwork_worker_m2/handoff.md`.
- Send a completion message back to the orchestrator with test results and summary of changes.
