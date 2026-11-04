# AGENTS.md — instructions for Griductive Solver coding agents

The official specification is `docs/assignment.pdf`. Read the relevant pages before implementation and consult `docs/requirements.md` and `docs/architecture.md`. The planning documents identify assignment requirements, project design recommendations, and assumptions separately. The module layout and conventions below are project design recommendations where the PDF does not prescribe a choice. If they conflict with the PDF, follow the PDF and update the documents. Do not modify the PDF.

## Workflow

1. Inspect the current `src/` layout and related tests before changing or adding code. Check `TASKS.md` dependencies and acceptance criteria; briefly state the planned algorithm or change before coding.
2. Implement one small task or a clearly related set. Keep all Python source in `src/` and tests in `tests/`. Use focused modules for domain model, region semantics, I/O, game engine, CNF, DPLL, agent, controller, GUI, and experiments. The exact file split may evolve, but their boundaries must remain clear.
3. Add unit tests for every new module and solving algorithm. Run the full test suite before marking any implementation task complete. Record the test command/result in the handoff. If tests cannot run, leave the task unchecked and describe the blocker.
4. Update the checkbox in `TASKS.md` only after its measurable acceptance checks pass. Update README/schema/architecture documentation when an interface or design choice changes. Do not check off dependent work just because a stub exists.
5. Keep code and reports explainable to the student team, including SAT-query reasoning and experiment conventions. The assignment permits AI tools but may assess understanding in an oral interview.

## Python conventions

- Follow PEP 8. Use type hints on public functions and methods, and docstrings that explain contracts and non-obvious logic. Prefer immutable data structures at the public-state and CNF boundaries.
- Use explicit, deterministic ordering: row-major cells, stable clue IDs, ordered region members, fixed DPLL branch order. Avoid hidden global state and nondeterministic iteration in solver-visible paths.
- Validate puzzle input at the boundary and report useful errors. Keep structured clues as data; do not parse GUI prose to recover logic. Never hand-write puzzle-specific CNF in source.
- Keep the main algorithms in project Python code. Supporting libraries for GUI, file handling, and testing are permitted by the PDF; SAT solving, entailment, and core encoding must be implemented here.
- Keep dependencies modest and document them in the eventual `requirements.txt` and README. Do not introduce a framework solely for module wiring or abstractions without a concrete need.

## Architectural rules

- **Private engine:** `GameEngine` owns the complete solution and all unrevealed clues. Only it (and explicit offline validation tooling) may read them. It publishes a `PublicState` containing visible character metadata, initial face-up statuses/clues, and accepted verdicts/revealed clues. Rejected calls do not mutate it.
- **Public agent:** `LogicAgent` and its hint/proof methods accept only public snapshots and board metadata. They must not import or hold `GameEngine`, private `Puzzle`, hidden labels, or unrevealed clue content. The controller coordinates proof and reveal but must never use the hidden solution as evidence for a verdict.
- **Independent semantics:** Direct clue evaluators inspect a complete assignment without using CNF or DPLL. Use them for puzzle truth checks and encoding tests. Region resolution is shared by evaluators, encoder, and highlighting, so all three agree on referenced cells.
- **Sound verdicts:** Check base-KB satisfiability before entailment. Use UNSAT under the opposite temporary literal to prove a status. Two SAT results mean `UNKNOWN`; base UNSAT means `INCONSISTENT`. Never accept or auto-select an unproved call. Preserve `NOT_PROVABLE` and `CONTRADICTED` semantics for rejected manual calls.
- **CNF and DPLL:** Allocate primary variables deterministically and auxiliaries separately. Encode all six required templates and the selected parity/common-neighbor extensions automatically. Keep SAT assumptions temporary. DPLL must return a complete satisfying model or UNSAT and record decisions, propagations, backtracks, and runtime.
- **Offline validation:** Check clue truth and uniqueness separately from live deduction. Full-clue uniqueness uses all clues and initial public statuses without injecting the hidden solution. Report no-guess playability separately; uniqueness alone does not establish it.
- **GUI and experiments:** Render from public state only. Show all required controls, reveal behavior, rejection reasons, and highlights. Experiment on a fixed set of several 3×3 and 4×4 puzzles; retain failure/timeout rows and all assigned metrics.

## Test expectations

- Test geometry at corners, edges, and interior; all six core clue evaluators and both extensions; malformed references and k bounds; CNF equivalence to independent semantics on small exhaustive cases (allowing auxiliary assignments); DPLL against brute force; SAT entailment, inconsistency, and call immutability.
- Include integration tests for a progressive reveal path and a stalled/ambiguous state. Check that hints, auto solve, and the GUI/controller do not reveal or inspect hidden data early.
- Run the repository's full `pytest` or `unittest` suite as established by the implementation. Use the same fixed fixture set for experimental comparisons. Do not treat a zero-test discovery as evidence that implementation works.

## Delivery notes

The PDF also requires a PDF report, a narrated/subtitled 5–10 minute Google Drive demo, and a student-ID-named ZIP/RAR submission. Consult `docs/requirements.md` and T19–T21 before final delivery. Record team contributions fairly; never invent student IDs, completion percentages, a deadline, or video permission verification.
