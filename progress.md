# Progress Log — Griductive Solver

## Review and Repair of T01–T03

Review date: 2026-11-04. Scope: `docs/assignment.pdf`, `AGENTS.md`, `TASKS.md`, `docs/architecture.md`, and all source and tests for T01–T03.

### Status

- **T01 — PASS.** Deep immutability enforced for `Puzzle.solution`, `Puzzle.clues`, `PublicState.cards`, and `PublicState.known_statuses` using `MappingProxyType(dict(...))` and `tuple(...)`. Pre-construction defensive copying prevents source-alias mutation. Invariant enforcement in `PublicState` guarantees that face-down cards cannot expose status or clue and that known statuses/clues match revealed cells exactly. All tests pass.
- **T02 — PASS.** Row, column, corner/edge/interior eight-neighbors, explicit regions, common-neighbor intersections, deterministic row-major ordering, self-exclusion, invalid region coordinates, duplicate explicit cells, and highlight targets behave as specified.
- **T03 — PASS.** Clue evaluators for all templates strictly reject non-integer / boolean `k` and invalid assignment value types (enforcing `Status` or `bool`). Complete N×N assignment validation and boundary counts verified independently without CNF/DPLL dependencies.

### Prior Test Evidence
- Command: `pytest -q`
- Result: 73 passed in 0.08s.

---

## Milestone M2: Implementation of T04 & T05

Implementation date: 2026-11-04. Scope: `src/griductive/io.py`, `src/griductive/engine.py`, `schema/puzzle_schema_v1.json`, `tests/fixtures/puzzle_3x3_valid.json`, `tests/test_io.py`, `tests/test_engine.py`.

### Status

- **T04 — PASS.**
  - Implemented versioned JSON schema ("1.0") and formal specification in `schema/puzzle_schema_v1.json`.
  - Implemented `src/griductive/io.py` with `load_puzzle_from_dict`, `load_puzzle_from_json`, and `validate_puzzle_data`.
  - Comprehensive input validation: grid bounds (N >= 2), exact cell coverage, duplicate coordinate and name detection, character reference resolution (by name or cell ID), self-comparison rejection for SAME/DIFFERENT, region validation, cardinality k bounds and type checks, non-empty distinct initial face-up cards.
  - Offline semantic truth validation: every clue is evaluated against the puzzle's ground truth solution using `semantics.evaluate_clue`. Puzzles containing false clues are rejected.
  - Minimal valid 3x3 fixture provided at `tests/fixtures/puzzle_3x3_valid.json` covering all core clue templates and extensions.
  - Tested via 24 unit tests in `tests/test_io.py`.

- **T05 — PASS.**
  - Implemented `GameEngine` in `src/griductive/engine.py`.
  - Complete private ownership of `_puzzle`, hidden solution, and unrevealed clues.
  - Emits immutable `PublicState` snapshots with alphabetically sorted characters, face-down cards hiding status and clue, and revealed clues sorted deterministically in row-major order.
  - Guarded `reveal(cell, verdict)`: validates cell existence, prevents re-revealing cards, checks proposed verdict against private solution.
  - State immutability on rejection: invalid or wrong verdict raises `ValueError` while leaving `_revealed_cells`, public state, and `revision` strictly untouched.
  - Supported `restart()` returning fresh public state restoring initial face-up view.
  - Tested via 10 unit tests in `tests/test_engine.py`.

### Final Verification Results

- Compilation: `python -m compileall -q src tests` -> 0 errors.
- Test Suite: `pytest -q` -> **139 passed in 0.16s** (zero failures, zero errors).
  - Includes 32 adversarial edge-case tests in `tests/test_io_adversarial.py` and `tests/test_engine_adversarial.py`.
  - Remediated 2 edge cases in `src/griductive/io.py`: falsy clue ID validation bypass (`""`, `0`, `False`) and empty string / directory path handling in `load_puzzle_from_json`.
- Immutability & Boundary Guarantees:
  - `Puzzle` and `PublicState` enforce defensive copying and frozen dictionary views (`MappingProxyType`).
  - `GameEngine` strictly encapsulates private solution and hidden clues; invalid verdicts preserve state/revision.
- Lint & Code Quality: Clean across all modules in `src/griductive/` and `tests/`.

### Readiness

Milestone M2 is fully complete and verified. Tasks T01, T02, T03, T04, and T05 are complete and PASS with 139 passing tests. As required by user instruction, all work stops after T05 without starting subsequent tasks (T06+).

---

## Milestone M3: Implementation of T06

Implementation date: 2026-11-04. Scope: `src/griductive/cnf.py`, `tests/test_cnf.py`.

### Status

- **T06 — PASS.**
  - Implemented `src/griductive/cnf.py` providing:
    - `PrimaryVarMap(grid_size)` — deterministic row-major bijection `CellId ↔ 1..N²`
    - `AuxAllocator(start_after)` — fresh auxiliary variable counter, strictly above primary range
    - `CNFFormula(clauses, primary_map, num_aux)` — immutable container with zero-literal guard
    - `encode_fact`, `encode_same`, `encode_different` — FACT (1 unit), SAME (2 clauses), DIFFERENT (2 clauses)
    - `encode_known_status` — 1 unit clause per known cell status
    - `build_cnf_from_public_state` — builds full CNF from PublicState; raises `NotImplementedError` for T07/T08 clue types
  - `cnf.py` imports only `model.py`; does not import `engine`, `semantics`, `dpll`, `logic`, `controller`, `gui`, or `validation`.
  - Exhaustive CNF↔semantics equivalence tests for all 2⁴ = 16 assignments on all distinct cell pairs in a 2×2 grid.
  - Architecture isolation verified by AST import analysis in tests.

### Final Verification Results

- Compilation: `python -m compileall src/` → 0 errors
- Test Suite: `python -m pytest tests/ -v` → **176 passed in 0.34s** (0 failed, 0 errors)
  - 37 new tests in `tests/test_cnf.py`; all prior 139 tests still pass

### Readiness

T06 complete and verified. Next task: **T07 — Encode cardinality** (depends on T02, T06).

---

## Milestone M4: Implementation of T07

Implementation date: 2026-11-04. Scope: `src/griductive/cnf.py` (cardinality encoders added), `tests/test_cnf_cardinality.py`.

### Status

- **T07 — PASS.**
  - Added `_encode_at_most_literals` — internal Sinz (2005) sequential counter over a literal sequence.
  - Added `encode_at_most(clue, pmap, aux, grid_size)` — AT_MOST(k): k=0 → n unit clauses; k=n → 0 clauses; interior → sequential counter with n×k auxiliaries; clause count = 1+(n−1)×(2k+1).
  - Added `encode_at_least(clue, pmap, aux, grid_size)` — AT_LEAST(k) = AT_MOST(n−k) over negated literals; n×(n−k) auxiliaries.
  - Added `encode_exactly(clue, pmap, aux, grid_size)` — EXACTLY(k) = AT_MOST(k) ∧ AT_LEAST(k) with independent fresh auxiliaries; n×k + n×(n−k) total.
  - Updated `build_cnf_from_public_state` to dispatch AtMostClue, AtLeastClue, ExactlyClue to new encoders; ParityClue still raises NotImplementedError (T08).
  - Updated stale `test_cnf.py` placeholder tests (ExactlyClue/AtLeastClue NotImplementedError → success assertions).

### Encoding Verification (Lead Reviewer)
- AT_MOST(1, n=3): 7 clauses = 1+(3−1)×(2×1+1) ✓; aux=3×1=3 ✓
- AT_LEAST(1, n=3)=AT_MOST(2,neg): 11 clauses=1+(3−1)×(2×2+1) ✓; aux=3×2=6 ✓
- EXACTLY(1, n=3): 7+11=18 counter clauses; aux=3+6=9 ✓
- Exhaustive 2^4 × 5 (all k) correctness verified against `evaluate_cardinality` ✓

### Final Verification Results

- Compilation: `python -m compileall src/` → 0 errors
- Test Suite: `python -m pytest tests/ -v` → **212 passed in 0.41s** (0 failed, 0 errors)
  - 36 new tests in `tests/test_cnf_cardinality.py`; all prior 176 tests still pass

### Readiness

T07 complete and verified. Next task: **T08 — Encode two extensions** (PARITY via Tseitin XOR chain, COMMON_NEIGHBORS region support; depends on T02, T06–T07).

---

## Milestone M5: Implementation of T08

Implementation date: 2026-11-04. Scope: `src/griductive/cnf.py` (parity encoder added), `tests/test_cnf_parity.py`.

### Status

- **T08 — PASS.**
  - Implemented `encode_parity(clue, pmap, aux, grid_size)` using a Tseitin XOR chain:
    - Empty region ($n=0$): `EVEN` produces 0 clauses (tautology), `ODD` produces 1 empty clause `()` (UNSAT).
    - Single cell ($n=1$): `EVEN` produces 1 negative unit clause $(-x_0,)$, `ODD` produces 1 positive unit clause $(+x_0,)$. 0 auxiliaries.
    - General $n \ge 2$: Allocates exactly $n-1$ fresh auxiliaries $p_0 \dots p_{n-2}$.
      - First gate: $p_0 \leftrightarrow (x_0 \oplus x_1)$ (4 Tseitin clauses).
      - Subsequent gates: $p_i \leftrightarrow (p_{i-1} \oplus x_{i+1})$ (4 Tseitin clauses each).
      - Parity unit clause on $p_{n-2}$: $(-p_{n-2},)$ for `EVEN`, $(+p_{n-2},)$ for `ODD`.
      - Total clauses: exactly $4(n-1) + 1$. Total auxiliaries: $n-1$.
  - Integrated `CommonNeighborsRegion`:
    - Evaluated before encoding for both cardinality and parity clues.
    - Verified behavior for empty intersections ($n=0$) and non-empty intersections ($n=1, 2, 3$).
  - Updated `build_cnf_from_public_state` to dispatch `ParityClue` directly.
  - Comprehensive unit tests in `tests/test_cnf_parity.py` (31 new tests).
  - All tests verified against independent semantic evaluator `evaluate_parity`.

### Final Verification Results

- Compilation: `python -m compileall src/ tests/` → 0 errors
- Test Suite: `python -m pytest tests/ -v` → **243 passed in 0.42s** (0 failed, 0 errors)

### Readiness

T08 complete and verified. Next task: **T09 — Implement custom DPLL** (depends on T06).

---

## Milestone M6: Implementation of T09

Implementation date: 2026-11-04. Scope: `src/griductive/dpll.py`, `tests/test_dpll.py`.

### Status

- **T09 — PASS.**
  - Implemented custom deterministic DPLL SAT solver from scratch in `src/griductive/dpll.py`:
    - `DpllMetrics`: immutable tracking of decisions, propagations, backtracks, and wall-clock runtime.
    - `SatResult`: immutable outcome returning `is_sat: bool`, `model: Mapping[int, bool] | None` (via `MappingProxyType`), and `metrics: DpllMetrics`.
    - `solve_dpll(cnf, assumptions, branch_preference)`:
      - Deterministic unit propagation to a fixed point.
      - Conflict detection (empty clause or conflicting assignments).
      - Deterministic variable selection: lowest-numbered unassigned variable ($1 \dots \text{num\_vars}$).
      - Deterministic branching order: configurable via `branch_preference` (default `False` then `True`).
      - Recursive search with backtracking counters.
      - Temporary non-destructive assumptions: applied as initial unit constraints without mutating the base `CNFFormula`.
      - Total assignment completion: deterministic filling of any unconstrained variables so that the returned model is complete for all declared variables $1 \dots \text{num\_vars}$.
  - Implementation verified with 26 unit tests in `tests/test_dpll.py`:
    - Unit propagation and propagation chains.
    - Conflict detection and immediate UNSAT for empty clauses or contradictory units.
    - Branching and backtracking metrics verification.
    - Temporary assumption scoping (isolation, multiple queries, contradictory assumptions, out-of-bounds checks).
    - Edge cases: empty formula (0 clauses), empty clause `()`, unconstrained variables.
    - Cross-checked against an independent exhaustive brute-force SAT oracle across various formula classes.
    - Integration test with `build_cnf_from_public_state` on a multi-card public game state.
    - Architecture isolation verified: `dpll.py` has no imports from `engine`, `semantics`, `logic`, `controller`, `gui`, or `validation`.

### Final Verification Results

- Compilation: `python -m compileall src/ tests/` → 0 errors
- Test Suite: `python -m pytest tests/ -v` → **269 passed in 0.38s** (0 failed, 0 errors)
- Subagent State: 0 active subagents.

### Readiness

Tasks T01 through T09 are fully complete, passing, and verified. Work strictly stops before starting T10 or downstream tasks as instructed.

---

## Milestone M7: Implementation of T10

Implementation date: 2026-11-04. Scope: `src/griductive/kb.py`, `tests/test_kb.py`.

### Status

- **T10 — PASS.**
  - Implemented `KnowledgeBase` and `KnowledgeBaseBuilder` in `src/griductive/kb.py`:
    - Constructs `KnowledgeBase` strictly and exclusively from `PublicState`.
    - Holds compiled immutable `formula: CNFFormula`, `state_revision: int`, `active_clue_ids: tuple[str, ...]`, and `known_statuses: Mapping[CellId, Status]`.
    - Directly exposes properties: `num_primary`, `num_aux`, `num_vars`, `num_clauses`, `clauses`, and `primary_map`.
    - Guarantees complete isolation from hidden puzzle data: verified that two games with identical public state but different hidden solutions/clues produce identical knowledge bases.
    - Deterministic rebuilds: identical public states produce identical formulas, active clue IDs, and counts.
    - Updated `solve_dpll` in `dpll.py` to seamlessly accept `KnowledgeBase` or `CNFFormula`.
  - Comprehensive unit test suite in `tests/test_kb.py` (8 new tests):
    - Public/private isolation verified against private `Puzzle` and `GameEngine`.
    - Deterministic rebuild tests across repeated builds.
    - Empty (0 revealed cards) and partial reveal scenarios.
    - Mixed core and extension clues count and ID checks.
    - Exhaustive semantic satisfaction equivalence.
    - Architecture isolation verified (no forbidden imports).

### Final Verification Results

- Compilation: `python -m compileall src/ tests/` → 0 errors
- Test Suite: `python -m pytest tests/ -q` → **277 passed in 0.26s** (0 failed, 0 errors)

### Readiness

T10 complete and verified. Next task: **T11 — Implement entailment classification** (depends on T09, T10).

---

## Milestone M8: Implementation of T11

Implementation date: 2026-11-04. Scope: `src/griductive/logic.py`, `tests/test_logic.py`.

### Status

- **T11 — PASS.**
  - Implemented `SatQueryRecord`, `CellClassification`, `ProofReport`, `ProofService`, and `LogicAgent` in `src/griductive/logic.py`:
    - Strict public boundary: `LogicAgent` and `ProofService` consume only `PublicState` snapshots, with zero access to `GameEngine`, private `Puzzle`, hidden labels, or unrevealed clues.
    - Sound refutation-based entailment:
      1. Base consistency check: queries `KB_t` for satisfiability once at root.
      2. If `KB_t` is UNSAT: base is marked inconsistent; all unresolved cards are classified as `Verdict.INCONSISTENT`; search halts immediately with exactly 1 SAT call (preventing vacuous deductions).
      3. If `KB_t` is SAT: tests each unresolved card in deterministic row-major order:
         - Query $\text{KB}_t \land \neg C_i$: if UNSAT, refutation proves $C_i$ is forced True $\rightarrow$ `Verdict.CRIMINAL`.
         - Else query $\text{KB}_t \land C_i$: if UNSAT, refutation proves $C_i$ is forced False $\rightarrow$ `Verdict.INNOCENT`.
         - If both assumptions are SAT $\rightarrow$ `Verdict.UNKNOWN`.
    - No single-model reliance: a card is never classified based on one satisfying model alone.
    - Complete query tracing: records each individual `SatQueryRecord` (assumptions, SAT outcome, and `DpllMetrics`), tracks `total_sat_calls`, and sums `aggregate_metrics` (decisions, propagations, backtracks, runtime).
    - `ProofReport` helpers: provides `forced_cells` (ordered row-major) and `first_forced_cell` for downstream deduction and hints (T12/T13).
  - Comprehensive unit test suite in `tests/test_logic.py` (19 new tests):
    - Forced Criminal cases (refutation of negated literal).
    - Forced Innocent cases (refutation of positive literal).
    - Ambiguous UNKNOWN cases (both branches satisfiable) on unconstrained and partially constrained states.
    - Inconsistent KB cases with early termination and exactly 1 SAT call.
    - Multi-card grids verifying row-major order and `first_forced_cell`.
    - Cross-checked against an independent semantic brute-force oracle across 5 diverse puzzle states.
    - Public/private isolation verified: two puzzles with different hidden solutions yield identical `LogicAgent` proof reports.
    - Architecture isolation verified: `logic.py` contains no imports from forbidden modules (`engine`, `semantics`, `controller`, `gui`, `validation`).

### Final Verification Results

- Compilation: `python -m compileall src/ tests/` → 0 errors
- Test Suite: `python -m pytest tests/ -q` → **296 passed in 0.30s** (0 failed, 0 errors)
- Subagent State: 0 active subagents.

### Readiness

Tasks T01 through T11 are fully complete, passing, and verified. Work strictly stops before starting T12 or downstream tasks as instructed.

---

## Milestone M9: Audit Remediation (FIX-01, FIX-02, FIX-03)

Remediation date: 2026-11-04. Scope: `src/griductive/cnf.py`, `src/griductive/logic.py`, `src/griductive/dpll.py`, `tests/test_cnf.py`, `tests/test_logic.py`, `tests/test_dpll.py`.

### Status

- **FIX-01 (High) — PASS.**
  - File: `src/griductive/cnf.py`
  - Defect: `CNFFormula.__post_init__` previously converted literals with `int(lit)`, permitting non-integers (floats, booleans) and allowing variable IDs exceeding `num_vars`.
  - Fix: Added strict type validation:
    - Rejects boolean literals (`isinstance(lit, bool)` -> `TypeError`).
    - Rejects non-integer literals (`not isinstance(lit, int)` -> `TypeError`).
    - Rejects literal 0 (`lit == 0` -> `ValueError`).
    - Rejects variable IDs exceeding total declared variables (`abs(lit) > num_vars` where `num_vars = num_primary + num_aux` -> `ValueError`).
    - Rejects boolean/non-integer `num_aux` (`TypeError`).
  - Regression tests: Added `test_rejects_boolean_literals`, `test_rejects_non_integer_literals`, `test_rejects_literal_exceeding_num_vars`, `test_rejects_non_integer_num_aux` in `tests/test_cnf.py`.

- **FIX-02 (Medium) — PASS.**
  - File: `src/griductive/logic.py`
  - Defect: `ProofService.classify_cell()` previously returned the known status of a revealed cell before checking base-KB satisfiability, incorrectly returning `CRIMINAL`/`INNOCENT` instead of `INCONSISTENT` on contradictory knowledge bases.
  - Fix: Base consistency check moved to the start of `classify_cell()`. If `solve_dpll(kb.formula, assumptions=())` is UNSAT, immediately returns `Verdict.INCONSISTENT`. Only consistent states proceed to return known status or evaluate refutation queries.
  - Regression tests: Added `test_classify_revealed_cell_on_inconsistent_state_returns_inconsistent` and `test_classify_state_and_cell_semantic_consistency` in `tests/test_logic.py`.

- **FIX-03 (Low) — PASS.**
  - File: `src/griductive/dpll.py`
  - Defect: DPLL solver previously counted caller-supplied initial assumptions as unit propagations (`self.propagations += 1`), inflating propagation metrics.
  - Fix: Removed `self.propagations += 1` from the assumption assignment loop in `_DpllSolver.solve()`. Documented in `DpllMetrics` and `solve_dpll` that only assignments derived via clause unit propagation are counted. Also added type validation rejecting boolean/non-integer assumption literals.
  - Regression tests: Added `test_assumptions_excluded_from_propagation_count` and `test_assumption_type_validation` in `tests/test_dpll.py`.

### Final Verification Results

- Compilation: `python -m compileall -q src tests` → 0 errors
- Test Suite: `python -m pytest -q tests/` → **304 passed in 0.29s** (0 failed, 0 errors)
- Subagent State: 0 active subagents.

### Readiness

All three audit findings are completely resolved with zero regressions. Tasks T01 through T11 are verified PASS. Ready for T12 (Manual calls).

---

## Milestone M10: Implementation of T12, T13 & T14

Implementation date: 2026-11-04. Scope: `src/griductive/controller.py`, `src/griductive/validation.py`, `src/griductive/logic.py`, `tests/test_controller.py`, `tests/test_validation.py`.

### Status

- **T12 — PASS.**
  - Implemented `GameController` and manual verdict calling in `src/griductive/controller.py`:
    - Strict public boundary: uses only public KB entailment via `ProofService.classify_cell(public_state, cell)`. The hidden solution is never inspected to decide whether a call is provable.
    - Sound rejection semantics:
      - `RejectionReason.NOT_PROVABLE`: returned when neither verdict is logically forced (`Verdict.UNKNOWN`).
      - `RejectionReason.CONTRADICTED`: returned when the opposite status is logically forced.
      - `RejectionReason.INCONSISTENT`: returned when the base public KB is unsatisfiable.
      - `RejectionReason.ALREADY_REVEALED`: returned when the cell has already been revealed.
      - `RejectionReason.INVALID_CELL`: returned when coordinate format is malformed or out of bounds.
    - Immutability guarantee: on any rejected call, `_engine.reveal()` is never called, strictly leaving game state, revision, and revealed cells unchanged.
    - Defense-in-depth: on accepted calls, `_engine.reveal()` internally asserts status matches private solution.
  - Tested via 9 focused unit tests in `tests/test_controller.py`.

- **T13 — PASS.**
  - Implemented no-guess deduction loop, auto solve, hint service, and deduction traces in `src/griductive/controller.py`:
    - `step()`: executes a single deduction step by finding the first forced unresolved card in deterministic row-major order, reveals it, and rebuilds public KB.
    - `auto_solve()`: runs progressive deduction loop without guessing until `AutoSolveStatus.SOLVED`, `AutoSolveStatus.STALLED`, or `AutoSolveStatus.INCONSISTENT`.
    - `hint()`: non-mutating hint derivation reporting provable card and necessary clue IDs via CNF-level omission testing.
    - Structured trace: `DeductionStep` records step number, active clue IDs, target cell, target verdict, SAT refutation queries, revealed status, revealed clue/ID, DPLL metrics, and revisions before/after.
  - Tested via 10 focused unit tests in `tests/test_controller.py`.

- **T14 — PASS.**
  - Implemented offline puzzle validation in `src/griductive/validation.py`:
    - `check_clues_truth()`: evaluates every clue against `puzzle.solution` using independent semantic evaluators (`semantics.evaluate_clue`) without invoking CNF or DPLL.
    - `check_solution_uniqueness()`: encodes all clues and initial face-up statuses into CNF (without injecting hidden-solution units). Uses a single blocking clause over PRIMARY variables ($1..N^2$) to test for multiple satisfying models. Correctly distinguishes `UniquenessResult.ZERO`, `UniquenessResult.UNIQUE`, and `UniquenessResult.MULTIPLE`.
    - `check_playability()`: runs progressive no-guess simulation from initial face-up cards, separating offline uniqueness from progressive reveal playability (`PlayabilityResult.SOLVABLE_NO_GUESS` vs `PlayabilityResult.STALLED`).
    - `validate_puzzle()`: comprehensive validation report combining semantic truth, uniqueness, and playability.
    - Strict architectural isolation: live logic agent and solver modules do not import `validation.py`.
  - Tested via 11 focused unit tests in `tests/test_validation.py`.

### Final Verification Results

- Compilation: `python -m compileall -q src tests` → 0 errors
- Test Suite: `python -m pytest -q tests/` → **334 passed in 0.36s** (0 failed, 0 errors)
  - 30 new unit tests (19 in `test_controller.py`, 11 in `test_validation.py`); all 304 prior tests continue to pass.
- Subagent State: 0 active subagents.

### Readiness

Tasks T01 through T14 are fully complete, passing, and verified. Work strictly stops before starting T15 as instructed. Ready for T15 (Representative fixtures).

---

## Milestone M11: Audit Remediation of T12–T14 (FIX-01 through FIX-06)

Remediation date: 2026-11-04. Scope: `src/griductive/controller.py`, `src/griductive/validation.py`, `src/griductive/engine.py`, `tests/test_controller.py`, `tests/test_validation.py`.

### Status

- **FIX-01 (High) — PASS.**
  - File: `src/griductive/controller.py`
  - Defect: Structural fallback in `find_relevant_clue_ids()` incorrectly called `resolve_region(clue.region, state.grid_size, clue.owner)` with 3 arguments instead of 2.
  - Fix: Corrected interface usage to `resolve_region(clue.region, state.grid_size)`. Verified all other call sites across the codebase.
  - Regression Test: Added `TestHintRedundantRegionalClues.test_hint_with_redundant_regional_clues_does_not_crash` in `tests/test_controller.py`, asserting Hint handles redundant regional clues and returns valid result without mutating public state.

- **FIX-02 (High) — PASS.**
  - Files: `src/griductive/validation.py`, `src/griductive/engine.py`
  - Defect: `validate_puzzle()` executed progressive playability on puzzles with false clues, triggering an unhandled exception when public deduction conflicted with private solution.
  - Fix: Added `PlayabilityResult.SKIPPED`. `validate_puzzle()` skips progressive simulation when `not clues_truth`, returning structured `ValidationReport` with `is_valid=False`, `clues_truth=False`, `false_clue_ids`, `playability=PlayabilityResult.SKIPPED`, and `playability_steps=0`. Direct calls to `check_playability()` on false clues also handle internal conflicts safely (`PlayabilityResult.INCONSISTENT`) without unhandled crashes.
  - Regression Tests: Added `test_validate_puzzle_on_false_clues_skips_playability_safely` and `test_check_playability_directly_on_false_clues_handled_safely` in `tests/test_validation.py`.

- **FIX-03 (Medium) — PASS.**
  - Files: `src/griductive/controller.py`, `src/griductive/engine.py`
  - Defect: For invalid directly constructed puzzles, engine exception messages disclosed the hidden expected status.
  - Fix: Public-facing controller methods (`make_call`, `step`, `auto_solve`) safely catch internal `ValueError` from reveal attempts without leaking hidden solution labels in messages or return values. State and revision are strictly preserved.
  - Regression Test: Added `TestHiddenStatusLeakPrevention.test_controller_never_leaks_hidden_solution_status` in `tests/test_controller.py`.

- **FIX-04 (Medium) — PASS.**
  - File: `src/griductive/controller.py`
  - Defect: `DeductionStep` stored only the target cell's queries instead of all SAT work performed during that deduction step, leading to metric discrepancies.
  - Fix: `DeductionStep` now records `base_query`, `all_queries`, `step_sat_calls`, `step_metrics` (aggregating all SAT calls in the wave), and `all_classifications`, while distinguishing target-cell proof evidence in `classification`. `AutoSolveReport` tracks `terminal_sat_calls` and `terminal_metrics`, reconciling run metrics exactly with individual step metrics.
  - Regression Tests: Added `test_step_trace_captures_all_sat_evidence_and_metrics` and `test_auto_solve_metrics_reconcile_with_steps_and_terminal_checks` in `tests/test_controller.py`.

- **FIX-05 (Medium) — PASS.**
  - File: `src/griductive/controller.py`
  - Defect: Reaching `max_steps` incorrectly reported `STALLED` even when more forced moves remained.
  - Fix: Added `AutoSolveStatus.STEP_LIMIT_REACHED`. Consistently handles `max_steps <= 0` (stops immediately with 0 steps) and positive step limits without guessing whether moves remain.
  - Regression Tests: Added `test_max_steps_reports_step_limit_reached_when_moves_remain` and `test_max_steps_zero_and_negative` in `tests/test_controller.py`.

- **FIX-06 (Low) — PASS.**
  - Files: `src/griductive/controller.py`, `src/griductive/validation.py`
  - Defect: Initially solved puzzles (all cards face-up) were marked as `STALLED` by validation.
  - Fix: `check_playability()` recognizes `AutoSolveStatus.ALREADY_SOLVED` as `PlayabilityResult.SOLVABLE_NO_GUESS` with 0 steps. `validate_puzzle()` reports `is_playable_no_guess=True` and `PlayabilityResult.SOLVABLE_NO_GUESS`.
  - Regression Test: Added `test_initially_solved_puzzle_marked_as_solvable_no_guess` in `tests/test_validation.py`.

### Final Verification Results

- Compilation: `python -m compileall -q src tests` → 0 errors
- Test Suite: `python -m pytest -q tests/` → **343 passed in 0.41s** (0 failed, 0 errors)
  - 9 new regression tests added across `test_controller.py` and `test_validation.py`. All 334 prior tests pass.
- Subagent State: 0 active subagents.

### Readiness

All six audit findings are completely resolved, tested, and verified. Tasks T01 through T14 are verified PASS with 343 passing tests. Ready for T15 (Representative fixtures).

---

## Milestone M12: Full T01–T14 Audit Repair (P0–P2)

Remediation date: 2026-11-04. Scope: public engine boundary, puzzle-schema/loader consistency, and duplicate-literal DPLL propagation. No T15 or later work was started.

### P0 — Public Engine Boundary: PASS

- Removed the public `GameController.engine` accessor. The supported public reveal
  operations are now `make_call()`, `step()`, and `auto_solve()`, all of which
  obtain public SAT proof before committing a reveal.
- Renamed the engine transition to the controller-internal
  `GameEngine._reveal_proven()`. It remains a defense-in-depth private-solution
  integrity check and no longer has a public `reveal()` API.
- Sanitized an internal incorrect-verdict error from a hidden-status message to
  `Verdict for cell <cell> cannot be committed.` Rejected transitions preserve
  state and revision.
- Documented the trust boundary in `docs/architecture.md`: Python leading
  underscores are a convention, not a memory-security sandbox; presentation code
  must retain only the controller and public state.
- Regression coverage: controller has no `.engine` attribute; the initially
  `UNKNOWN` but secretly correct `C1=CRIMINAL` call is rejected as
  `NOT_PROVABLE` without changing state; sanitized engine errors contain neither
  hidden status label.

### P1 — JSON Schema and Loader Consistency: PASS

- `load_puzzle_from_dict()` now requires `schema_version` to be a string before
  comparison. Numeric `1.0` is rejected with `TypeError` instead of silently
  coercing to the supported version.
- Expanded `schema/puzzle_schema_v1.json` to Draft-07 definitions for every
  clue (`FACT`, `SAME`, `DIFFERENT`, `EXACTLY`, `AT_LEAST`, `AT_MOST`, `PARITY`)
  and region (`ROW`, `COL`, `NEIGHBORS`, `EXPLICIT`, `COMMON_NEIGHBORS`) variant,
  including their type-specific required fields.
- Regression coverage checks non-string schema versions and verifies the schema's
  variant/required-field structure. An independent available Draft-07 validation
  check accepted the existing fixture and rejected numeric schema versions and a
  `FACT` missing `target`/`status`.

### P2 — Duplicate-Literal Unit Propagation: PASS

- Updated DPLL unit propagation to count distinct unassigned literals. `(x OR x)`
  now propagates as unit `(x)` without rewriting the immutable input formula.
- Regression coverage verifies duplicate-unit propagation (`0` decisions, `1`
  propagation), duplicate conflicting clauses (`UNSAT` without branching), and
  contradictory temporary assumptions that leave the source formula unchanged.

### Verification Evidence

- Focused P0 suite: `python -m pytest -q tests/test_engine.py tests/test_engine_adversarial.py tests/test_controller.py` → **52 passed**.
- Focused P1 suite: `python -m pytest -q tests/test_io.py tests/test_io_adversarial.py` → **41 passed**.
- Focused P2 suite: `python -m pytest -q tests/test_dpll.py` → **29 passed**.
- Full suite: `python -m pytest -q tests/` → **346 passed in 0.54s**.
- Compilation: `python -m compileall -q src tests` → **0 errors**.
- Independent counterexamples rerun:
  - public controller has no `.engine`; UNKNOWN `C1` call returns `NOT_PROVABLE` and preserves state;
  - engine has no public `reveal`; sanitized internal failure does not contain `INNOCENT`;
  - numeric `schema_version=1.0` raises `TypeError`;
  - `(1, 1)` yields SAT with `decisions=0`, `propagations=1`, and a duplicated contradiction yields UNSAT without branching.


---

## Milestone M13: Implementation of T15, T16, & T17

Implementation date: 2026-11-04. Scope: `puzzles/`, `tests/test_fixtures.py`, `src/griductive/gui.py`, `src/main.py`, `tests/test_gui.py`.

### Status

- **T15 — Build representative fixtures: PASS.**
  - Created standardized fixtures under `puzzles/`:
    - `puzzles/puzzle_3x3_progressive.json`: 3×3, unique complete solution, all clues semantically true, progressively solvable without guessing in 8 steps.
    - `puzzles/puzzle_3x3_stalled.json`: 3×3, unique complete solution, all clues semantically true, stalls progressively after 1 step.
    - `puzzles/puzzle_3x3_ambiguous.json`: 3×3, all clues true under solution, underconstrained with multiple complete solutions.
    - `puzzles/puzzle_4x4_progressive.json`: 4×4, unique complete solution, all clues true, progressively solvable without guessing in 15 steps.
    - `puzzles/puzzle_4x4_stalled.json`: 4×4, unique complete solution, all clues true, stalls progressively with 0 steps.
    - `puzzles/puzzle_invalid_false_clue.json`: 3×3, invalid puzzle containing a false clue contradicting the ground truth solution.
    - `puzzles/manifest.json`: versioned manifest cataloging all fixtures, expected uniqueness, playability, step count, clue truth, templates, and regions.
  - Comprehensive coverage verified across fixtures:
    - All 6 core templates: `FACT`, `SAME`, `DIFFERENT`, `EXACTLY`, `AT_MOST`, `AT_LEAST`.
    - Both extensions: `PARITY` (EVEN/ODD) and `COMMON_NEIGHBORS`.
    - Region geometry: `ROW`, `COL`, `NEIGHBORS`, `EXPLICIT`, `COMMON_NEIGHBORS`.
  - Tested via 7 unit/integration tests in `tests/test_fixtures.py`.

- **T16 — Render playable board: PASS.**
  - Implemented GUI module in `src/griductive/gui.py` and CLI/launcher in `src/main.py`.
  - Public/private boundary preserved: GUI receives exclusively `PublicState` snapshots from `GameController`. It has no reference to `GameEngine`, private `Puzzle`, hidden statuses, or unrevealed clues.
  - View model renders:
    - N×N grid with row coordinates (1..N) and column coordinates (A..N).
    - Alphabetically ordered characters by display name, with coordinate and profession.
    - Clear visual distinction between Face-Down (`[ ? ]`, neutral gray), Criminal (`CRIMINAL`, red badge / tint), and Innocent (`INNOCENT`, green badge / tint).
    - Selected card styling (gold border) and Clue/Hint highlight styling (blue/purple borders).
    - Revealed clues displayed with formatted human-readable prose.

- **T17 — Connect GUI interactions: PASS.**
  - Fully wired user interactions:
    - **Load Puzzle:** file picker / path loader into a fresh `GameController`.
    - **Restart:** resets public state back to initial face-up cards, clearing selections.
    - **Manual Call:** calls `controller.make_call(selected_cell, verdict)`. If accepted, flips card and reveals clue. If unprovable, displays `NOT_PROVABLE` banner without mutating state. If contradicted, displays `CONTRADICTED` banner without mutating state.
    - **Clue Selection & Highlighting:** clicking a revealed clue calls `regions.get_clue_highlight_cells()` and visually highlights all counted/referenced cells.
    - **Hint:** queries `controller.hint()`. Highlights forced card and relevant clues without mutating state.
    - **Step & Auto Solve:** executes deterministic deduction loops with visible activity logs, displaying `SOLVED`, `STALLED`, `INCONSISTENT`, or `STEP_LIMIT_REACHED`.
  - Clean headless execution: `GriductiveApp` presentation architecture supports both headless testing and live desktop Tkinter windows.
  - Tested via 14 unit and integration tests in `tests/test_gui.py` (including live Tk widget verification under `xvfb-run -a`).

### Verification Evidence

- Compilation: `python3 -m compileall -q src tests` → **0 errors**.
- Headless test suite: `python3 -m pytest -q tests/` → **366 passed, 1 skipped in 0.63s**.
- Live Tk suite under virtual display: `xvfb-run -a python3 -m pytest -q tests/` → **367 passed in 0.74s**.
- CLI Smoke tests:
  - `python3 src/main.py validate puzzles/puzzle_3x3_progressive.json` → PASS (Valid: True, Uniqueness: UNIQUE, Playability: SOLVABLE_NO_GUESS).
  - `python3 src/main.py solve puzzles/puzzle_3x3_progressive.json` → PASS (Solved in 8 steps).
  - `python3 src/main.py solve puzzles/puzzle_4x4_progressive.json` → PASS (Solved in 15 steps).

### Readiness

T15, T16, and T17 are fully implemented, verified, and complete. All 367 tests pass. Ready for T18 (reproducible experiments). No T18 work started.

---

## Milestone M14: T01–T17 Integration Re-Audit Repairs

Repair date: 2026-11-05. Scope: integration-audit findings only; no T18 work started.

### Fixes

- **JSON schema/loader normalization: PASS.** The Draft-07 schema now requires
  string discriminator fields and accepts the same case-insensitive,
  whitespace-normalized schema version, statuses, clue types, region types,
  parity values, coordinates, and references as the loader. Type-specific
  required fields remain enforced for all seven clue and five region variants.
- **Load/Restart trace reset: PASS.** Successful puzzle load and restart now
  replace the activity trace and clear transient selection, hint, highlight,
  rejection, and report state. Failed loads continue to preserve the active
  controller and board.
- **Step terminal status: PASS.** A no-reveal Step now distinguishes an
  inconsistent public KB from a genuine no-guess stall and preserves public
  state in both cases.
- **Hint visual cleanup: PASS.** Every Hint request first clears the previous
  hint/clue highlight state, so a later no-hint result cannot leave stale
  visual evidence on the board.
- **Fixture manifest accuracy: PASS.** Manifest entries now distinguish schema
  validity from semantic validity. Coverage lists match each raw fixture, and
  the false-clue fixture is correctly recorded as schema-valid,
  semantically invalid, and having zero satisfying assignments.

### Regression and Independent Verification

- Focused suite:
  `python3 -m pytest -q tests/test_io.py tests/test_io_adversarial.py tests/test_gui.py tests/test_fixtures.py`
  → **66 passed, 1 skipped**.
- Full headless suite: `python3 -m pytest -q tests/` → **371 passed, 1 skipped**.
- Full Tk suite: `xvfb-run -a python3 -m pytest -q tests/` → **372 passed**.
- Compilation: `python3 -m compileall -q src tests` → **0 errors**.
- Independent Draft-07 check: all **6** puzzle fixtures validate; normalized
  lowercase/whitespace input validates; a non-string clue discriminator is
  rejected.
- Independent bounded fixture oracle: expected clue truth, solution counts
  (`1`, `1`, `256`, `1`, `1`, `0`), progressive statuses, step counts
  (`8`, `1`, `0`, `15`, `0`, `0`), templates, and regions all match the
  corrected manifest with **0 discrepancies**.
- GUI adversarial replay: successful Load/Restart leave no stale trace;
  contradictory public clues report `INCONSISTENT` without mutation; fixed-seed
  interaction sequence (`20261105`, 120 actions) completed without error.

### Readiness

All integration-audit findings addressed and regression-tested. T01–T17 remain
complete and the project is ready to begin T18. Python underscore privacy is a
trust boundary convention, not a security sandbox.


---

## Milestone M15: Implementation and Verification of T18

Implementation date: 2026-11-05. Scope: `src/griductive/experiments.py`, `src/main.py`, `experiments/`, `tests/test_experiments.py`.

### Status

- **T18 — Run reproducible experiments: PASS.**
  - Implemented `src/griductive/experiments.py` with `ExperimentRunner`, `ExperimentResult`, `ExperimentSuiteReport`, and `TimingStats`.
  - Wired `experiment` subcommand into `src/main.py` CLI (`python3 src/main.py experiment [--manifest PATH] [--output-dir DIR] [--repetitions N] [--print-summary]`).
  - Evaluated representative 3×3 and 4×4 fixtures under `puzzles/manifest.json`:
    - Progressive puzzles (`puzzle_3x3_progressive`, `puzzle_4x4_progressive`): verified 0 branching decisions, 0 backtracks, exact step counts (8 and 15), millisecond runtime.
    - Unique-but-stalled puzzles (`puzzle_3x3_stalled`, `puzzle_4x4_stalled`): verified `UNIQUE` solution, correctly halted without guessing, captured search effort (124 and 132 branching decisions during refutation queries).
    - Ambiguous puzzle (`puzzle_3x3_ambiguous`): verified `MULTIPLE` solution reporting, halted with 0 steps.
    - Invalid puzzle (`puzzle_invalid_false_clue`): captured as `INVALID_PUZZLE` with `SKIPPED` playability, preserving error diagnostics without halting the suite.
  - Repetition and variability: Repeated timing across $R=10$ runs per puzzle. Proved deterministic counter invariance (`std = 0.0` for decisions, propagations, backtracks, sat calls, steps) while reporting empirical wall-clock mean, std, min, and max.
  - Exported complete artifacts to `experiments/`:
    - `experiments/results.csv`: machine-readable CSV table of all metrics.
    - `experiments/results.json`: complete hierarchical JSON schema including per-step breakdown and system metadata.
    - `experiments/summary.md`: human-readable Markdown summary with analysis distinguishing theoretical $\mathcal{O}(2^V)$ bounds from realized millisecond unit-propagation performance.
  - Tested via 6 unit/integration tests in `tests/test_experiments.py`.

### Verification Evidence

- Compilation: `python3 -m compileall -q src tests` → **0 errors**.
- Headless test suite: `python3 -m pytest -q tests/` → **377 passed, 1 skipped in 1.14s**.
- Virtual display test suite: `xvfb-run -a python3 -m pytest -q tests/` → **378 passed in 1.24s**.
- Experiment benchmark: `python3 src/main.py experiment --repetitions 10 --print-summary` → completed with 0 errors, generated CSV, JSON, and Markdown files.

### Readiness

T18 is fully complete and verified. Tasks T01 through T18 are complete and PASS. Do not begin T19 or later tasks.
