# Original User Request

## Initial Request — 2026-11-04T11:54:01Z

Use a multi-agent workflow:
- Implementation workers write Python code and tests.
- Independent reviewers inspect correctness and architecture.
- Challengers identify edge cases and missing tests.
- An auditor verifies actual test results.

Continue developing the existing Griductive Solver course project in the current repository: audit T01–T03, repair any failing criteria or dependencies within the 3-attempt limit, and implement T04–T05 once dependencies are satisfied.

Working directory: /mnt/windowdata/Uninversity Data/Curriculum/HocKy5/Cơ sở trí tuệ nhân tạo/Griductive-Solver
Integrity mode: demo
The team must NOT: copy code from existing open-source projects for core logic; use pre-built libraries or frameworks for core functionality.

Reference material:
- AGENTS.md, TASKS.md, progress.md (if present), docs/requirements.md, docs/architecture.md, and docs/assignment.pdf

## Requirements

### R1. Audit and Repair T01–T03 Implementation and Tests
- Read AGENTS.md, TASKS.md, progress.md, docs/requirements.md, docs/architecture.md, and docs/assignment.pdf.
- Audit the implementation and run tests for T01 (immutable domain types), T02 (regions and highlights), and T03 (independent clue semantics).
- If T01 or T03 has failing acceptance criteria or unresolved review blockers (such as mutable dictionary aliases or loose value handling), repair them (up to 3 repair attempts) so all acceptance criteria and tests pass before proceeding to T04–T05.

### R2. Implement T04–T05 If Dependencies and Acceptance Criteria Are Satisfied
- Once T01–T03 dependencies and acceptance criteria are satisfied, implement T04 (specify and load puzzle files, JSON schema, io.py, minimal fixture, tests) and T05 (implement Game Engine, engine.py, tests).
- Stop after T05; do not start later tasks.

### R3. Execution Constraints and Tracking
- Preserve the public/private Game Engine boundary: public snapshots must not expose hidden labels or face-down clues.
- Implement core algorithms directly; do not copy open-source code for core logic or use pre-built libraries for core functionality.
- Do not fabricate test results.
- Stop and report a blocker after three unsuccessful repair attempts.
- Do not modify the assignment PDF.
- Do not push, delete project files, or make destructive changes.
- Keep all work within the existing repository.
- Use existing planning documents rather than redesigning the project.
- After each task, update TASKS.md and progress.md based on verified evidence.

## Verification Resources
- Test commands: `pytest -q` on `tests/` and `python -m compileall -q src tests`
- Documentation and specification: `docs/assignment.pdf`, `AGENTS.md`, `TASKS.md`, `progress.md`, `docs/requirements.md`, `docs/architecture.md`

## Acceptance Criteria

### Audit and Repair (T01–T03)
- [ ] T01–T03 implementation and tests pass all checks under `pytest -q`.
- [ ] `python -m compileall -q src tests` succeeds with zero errors.
- [ ] T01 domain types guarantee deep immutability: public snapshots expose no hidden labels or face-down clues, and mapping aliases cannot mutate puzzle or public state.
- [ ] T03 evaluates all required clue templates independently without CNF/DPLL dependencies, enforcing valid types and integer cardinality.

### Puzzle I/O and Game Engine (T04–T05)
- [ ] T04 deliverables (versioned JSON schema, `src/griductive/io.py`, minimal fixture, tests) validate inputs, reject malformed coordinates/cells/names/references/k/regions/clues, and keep hidden solutions private.
- [ ] T05 deliverables (`src/griductive/engine.py`, tests) expose initial face-up status/clues, keep unrevealed contents hidden, leave state unchanged on invalid/rejected actions, and support reset/restart.
- [ ] All new tests for T04 and T05 pass under `pytest -q`.

### Documentation and Process Guardrails
- [ ] TASKS.md and progress.md are updated after each completed task with verified test commands and output.
- [ ] No assignment PDF modification, destructive changes, or git pushes are made.
- [ ] Work halts after T05 without starting subsequent tasks.
