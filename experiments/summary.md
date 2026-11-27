# Griductive Solver — Experimental Performance Report

- **Execution Timestamp:** `2026-11-27T00:24:58.521693+00:00`
- **Platform:** `Linux 7.2.15+kali-amd64 (x86_64)`
- **Python Version:** `3.14.10`
- **Timing Repetitions:** `5 runs per puzzle`
- **Per-Puzzle Wall-Clock Timeout:** `30.0s`

## 1. Summary Metrics Table

| Puzzle ID | Grid | Uniqueness | Playability | Status | Steps | Prim / Aux | Clauses | SAT Calls | Dec | Prop | Back | DPLL Time (ms) | E2E Time (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `puzzle_3x3_progressive` | 3×3 | UNIQUE | SOLVABLE_NO_GUESS | `SOLVED` | 8/8 | 9 / 33 | 85 | 76 | 0 | 610 | 0 | 1.35 ± 0.09 | 2.38 ± 0.13 |
| `puzzle_3x3_stalled` | 3×3 | UNIQUE | STALLED | `STALLED` | 1/1 | 9 / 48 | 98 | 28 | 124 | 1390 | 0 | 11.75 ± 0.18 | 12.12 ± 0.18 |
| `puzzle_3x3_ambiguous` | 3×3 | MULTIPLE | STALLED | `STALLED` | 0/0 | 9 / 0 | 2 | 17 | 0 | 17 | 0 | 0.03 ± 0.00 | 0.12 ± 0.01 |
| `puzzle_4x4_progressive` | 4×4 | UNIQUE | SOLVABLE_NO_GUESS | `SOLVED` | 15/15 | 16 / 44 | 128 | 248 | 0 | 4622 | 0 | 20.36 ± 0.23 | 23.90 ± 0.32 |
| `puzzle_4x4_stalled` | 4×4 | UNIQUE | STALLED | `STALLED` | 0/0 | 16 / 16 | 33 | 31 | 132 | 586 | 0 | 2.33 ± 0.18 | 2.55 ± 0.20 |
| `puzzle_invalid_false_clue` | 3×3 | ZERO | SKIPPED | `INVALID_PUZZLE` | - | - | - | - | - | - | - | - | - |
| `puzzle_3x3_chain_1` | 3×3 | UNIQUE | SOLVABLE_NO_GUESS | `SOLVED` | 8/8 | 9 / 7 | 36 | 77 | 0 | 557 | 0 | 0.84 ± 0.04 | 1.79 ± 0.07 |
| `puzzle_4x4_chain_1` | 4×4 | UNIQUE | SOLVABLE_NO_GUESS | `SOLVED` | 15/15 | 16 / 14 | 67 | 248 | 0 | 2363 | 0 | 4.34 ± 0.05 | 7.19 ± 0.17 |
| `puzzle_5x5_chain_0` | 5×5 | UNIQUE | SOLVABLE_NO_GUESS | `SOLVED` | 24/24 | 25 / 15 | 96 | 615 | 0 | 8178 | 0 | 19.39 ± 0.37 | 25.90 ± 0.49 |
| `puzzle_5x5_chain_1` | 5×5 | UNIQUE | SOLVABLE_NO_GUESS | `SOLVED` | 24/24 | 25 / 19 | 100 | 614 | 0 | 8091 | 0 | 17.05 ± 0.13 | 23.56 ± 0.18 |

## 2. Key Experimental Findings and Analysis

### A. Determinism & Accounting Verification
- Deterministic search counters verified on `9/9` measured cases (`total_sat_calls`, `dpll_decisions`, `dpll_propagations`, `dpll_backtracks`, `total_steps` invariant across all repetitions).
- Overall manifest breakdown (`10` total cases): `6` solved without guessing, `3` halted cleanly as `STALLED` without guessing, and `1` retained as invalid/error/timeout diagnostic rows.

### B. Progressive Deduction, Stalled States & Retained Failure/Timeout Rows
- **Progressively Solvable Puzzles (`SOLVED`):** Every hidden card was proved strictly via refutation (`UNSAT` under opposite temporary assumption) before reveal.
- **Stalled & Ambiguous Puzzles (`STALLED`):** Unique-but-stalled fixtures (`UNIQUE`) and under-constrained fixtures (`MULTIPLE`) both terminated safely without guessing once neither `C_i` nor `¬C_i` was entailed.
- **Retained Failure / Timeout / Invalid Cases (never omitted from exports):**
  - `puzzle_invalid_false_clue` (`INVALID_PUZZLE`): Puzzle validation failed: clue c_A1 for cell A1 (FactClue) evaluates to FALSE under the hidden solution.

### C. Theoretical Complexity vs. Empirical Measurements
- **Theoretical Bound:** Worst-case DPLL search over $V = N^2 + N_{\text{aux}}$ variables is $\mathcal{O}(2^V)$, and each deduction wave issues up to $2U + 1$ SAT queries for $U \le N^2$ unresolved cards.
- **Empirical Scaling Across Grid Sizes:**
  - **3×3 (2 solved puzzle(s)):** mean SAT calls = `76.5`, mean DPLL time = `1.10 ms`, mean end-to-end time = `2.08 ms`.
  - **4×4 (2 solved puzzle(s)):** mean SAT calls = `248.0`, mean DPLL time = `12.35 ms`, mean end-to-end time = `15.55 ms`.
  - **5×5 stress cases (2 solved puzzle(s)):** mean SAT calls = `614.5`, mean DPLL time = `18.22 ms`, mean end-to-end time = `24.73 ms`.
- **Timing Convention:** Per-puzzle wall-clock timeout bounds worker execution, while reported `e2e_runtime` and `dpll_runtime` measure pure solving repetitions excluding subprocess spawn and offline uniqueness validation.
