# Griductive Solver implementation checklist

Tasks are in dependency order. Each is complete only after its deliverables and acceptance checks pass. For every source change, add focused tests and run the entire test suite before checking it off; record the command/result in the handoff. No source code is implemented yet. See `docs/requirements.md` and `docs/architecture.md` for details. Choices such as JSON, sequential counters, parity, common-neighbors, and fixture layout are **project design recommendations**, not extra PDF requirements.

## Planning

- [x] **P00 — Analyze and plan.** Dependencies: none. Deliverables: `docs/requirements.md`, `docs/architecture.md`, this checklist, `AGENTS.md`. Acceptance: all nine assignment pages and all 100 grading points are covered; requirements, recommendations, and assumptions are distinguished.

## Domain and input

- [x] **T01 — Define immutable domain types.** Dependencies: P00. Deliverables: `src/griductive/model.py`, tests. Acceptance: coordinate/row-major IDs round-trip; characters, typed clues, private puzzle, and public snapshot have clear types; public snapshots cannot expose hidden labels or face-down clue bodies.
- [x] **T02 — Resolve regions and highlights.** Dependencies: T01. Deliverables: `regions.py`, tests. Acceptance: row, column, corner/edge/interior eight-neighbors, explicit distinct cells, and common-neighbors yield correct ordered cell tuples; self is excluded; bad coordinates and duplicate explicit cells fail.
- [x] **T03 — Evaluate clue semantics independently.** Dependencies: T01–T02. Deliverables: `semantics.py`, tests. Acceptance: true/false cases for all six core templates, parity, and common-neighbors against complete assignments; boundary counts work; module does not import the CNF encoder.
- [ ] **T04 — Specify and load puzzle files.** Dependencies: T01–T03. Deliverables: versioned JSON schema, `io.py`, a minimal fixture, tests. Acceptance: stable IDs on valid input; malformed dimensions/cells/names/references/k/regions/clue IDs and false clues give specific errors; hidden solution remains private.
- [ ] **T05 — Implement Game Engine.** Dependencies: T04. Deliverables: `engine.py`, tests. Acceptance: initial face-up statuses/clues are public; face-down contents are absent; guarded reveal exposes exactly its card status/clue; invalid/rejected actions leave state and revision unchanged; restart restores initial view.

## CNF and SAT

- [ ] **T06 — Build CNF primitives and binary encoding.** Dependencies: T01. Deliverables: `cnf.py` allocator/CNF type and FACT/SAME/DIFFERENT encoders, tests. Acceptance: primary IDs are deterministic and distinct from auxiliaries; clauses use valid literals; binary CNF matches direct semantics on exhaustive small examples; counts are correct.
- [ ] **T07 — Encode cardinality.** Dependencies: T02, T06. Deliverables: sequential-counter AT_MOST, complemented AT_LEAST, EXACTLY, tests. Acceptance: bounds 0, n, and interior k agree with independent semantics on exhaustively enumerated small regions after existentially quantifying auxiliaries; fresh IDs and counts remain correct across clues.
- [ ] **T08 — Encode two extensions.** Dependencies: T02, T06–T07. Deliverables: Tseitin PARITY and COMMON_NEIGHBORS region support, tests. Acceptance: EVEN/ODD CNF matches semantics on small regions; common-neighbors works with count templates; empty-region behavior and counts are tested.
- [ ] **T09 — Implement custom DPLL.** Dependencies: T06. Deliverables: `dpll.py`, tests. Acceptance: unit chains, contradiction, branching, backtracking, empty CNF, and temporary assumptions return correct SAT/UNSAT; SAT models are complete and satisfy clauses; order is deterministic; decisions, propagations, backtracks, runtime are recorded; brute force agrees on small formulas.
- [ ] **T10 — Assemble public KB.** Dependencies: T05–T08. Deliverables: KB builder, tests. Acceptance: exactly revealed clues and public status units are included; changing a hidden clue cannot change the same public KB; counts and repeated builds are deterministic.
- [ ] **T11 — Implement entailment classification.** Dependencies: T09–T10. Deliverables: `logic.py` proof service, tests. Acceptance: base UNSAT gives INCONSISTENT; forced Criminal/Innocent and UNKNOWN match brute-force cases; all unresolved cards are classified; SAT query evidence/counts are recorded; no verdict relies on one model alone.

## Deduction and validation

- [ ] **T12 — Handle manual calls.** Dependencies: T05, T11. Deliverables: `controller.py` call action, tests. Acceptance: public proof precedes reveal; NOT_PROVABLE and CONTRADICTED have assignment meanings; rejects preserve state/revision/clues; inconsistent states cannot accept calls.
- [ ] **T13 — Implement hint, auto solve, and traces.** Dependencies: T11–T12. Deliverables: deduction loop and trace types, tests. Acceptance: forced selection is row-major; hints use public state without mutation; each trace step has active clue IDs, query outcomes, verdict, newly revealed clue; auto solve terminates as solved/stalled/inconsistent without guessing.
- [ ] **T14 — Validate puzzles and uniqueness offline.** Dependencies: T03–T05, T08–T09, T13. Deliverables: `validation.py`, tests. Acceptance: direct evaluators verify all clues against hidden solution; all-clue uniqueness reports zero/one/multiple via a primary-assignment blocking clause without hidden-label units; a unique but stalled opening is reported separately; live Logic Agent has no private-input path.
- [ ] **T15 — Build representative fixtures.** Dependencies: T04, T14. Deliverables: several 3×3 and several 4×4 puzzles, fixed manifest, expected validation results. Acceptance: intended valid cases have true clues and one solution; reveal outcome is documented; fixtures exercise six templates, both extensions, neighbor geometry, and rejection/UNKNOWN; invalid fixtures are labeled.

## GUI, experiments, submission

- [ ] **T16 — Render playable board.** Dependencies: T05, T15. Deliverables: `gui.py`, launcher, smoke check. Acceptance: 3×3 and 4×4 show grid/coordinates, alphabetically presented names, professions, known statuses, face-up clues and face-down cards; view model has no private data.
- [ ] **T17 — Connect GUI interactions.** Dependencies: T12–T13, T16. Deliverables: Load, Restart, manual verdict, clue highlight, Hint, Auto Solve, visible trace/progress; tests or manual test record. Acceptance: accepted calls flip; both rejection reasons appear without a flip; selecting a revealed clue highlights all referenced/counted cells; stalled/inconsistent outcomes are visible.
- [ ] **T18 — Run reproducible experiments.** Dependencies: T13, T15, T17. Deliverables: `experiments.py`, manifest, CSV/JSON results, reproduction instructions. Acceptance: each 3×3/4×4 case records primary/auxiliary variables, clauses, SAT calls, decisions, propagations, backtracks, steps/waves, runtime; failures/timeouts remain; comparisons, if made, use identical puzzle sets. Optional 5×5 is labeled optional.
- [ ] **T19 — Produce PDF report.** Dependencies: T07–T09, T13–T15, T18. Deliverables: well-formatted `Report.pdf` and editable source if used. Acceptance: fair team roles/tasks/completion percentages, formulation/reveal protocol, binary and counting CNF derivations, DPLL/entailment/uniqueness/deduction methods, experiment tables/charts and failures/limits, references and AI-use appendix are present and accurate.
- [ ] **T20 — Record and share demo.** Dependencies: T17, T19 draft. Deliverables: 5–10 minute narrated/subtitled Google Drive video and report URL. Acceptance: GUI, manual play, selected stage, solver run and solution appear; English/Vietnamese narration or subtitles; anyone-with-link access verified in incognito; no YouTube URL.
- [ ] **T21 — Package submission.** Dependencies: T18–T20. Deliverables: final README, dependency list, source, report, `StudentID1_StudentID2_...` ZIP/RAR. Acceptance: archive opens into clear `Source/` and `Report.pdf` layout, run guide works from a clean environment, full tests pass, actual IDs are used, >20 MB archive is shared via Drive, and nothing changes after the assigned deadline.

## Execution rule for future agents

Inspect `src/` and relevant tests, reread the PDF section, preserve the public/private boundary, implement one task and its focused tests, run the full suite, then update this checklist. Scaffolding alone does not complete downstream tasks.
