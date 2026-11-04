# Proposed architecture

This is a design for implementation, not existing code. `docs/requirements.md` separates assignment obligations from project choices. The current `src/` and `tests/` directories contain no implementation. The architecture uses Python modules under `src/griductive/`, a thin `src/main.py` launcher, and tests under `tests/`.

## Boundary and data flow

```text
Puzzle file ──> loader/validator ──> GameEngine [full puzzle, private statuses/clues]
                                      │ public_view() only
                                      ▼
GUI ── action ──> GameController ──> PublicState [face-up clues + known statuses]
                       │                      │
                       │                      ▼
                       │               LogicAgent / proof service
                       │                      │
                       │              CNF encoder ──> DPLL
                       │                      │
                       └── accepted verdict? ─┴──> GameEngine._reveal_proven(cell)
                                                   │
                                                   └── updated PublicState → GUI

Offline puzzle validation: GameEngine supplies complete clue set to a separate
PuzzleValidator → encoder/DPLL uniqueness check and semantic truth checks.
```

The **Logic Agent must be constructible from `PublicState` alone**. It receives no reference to `GameEngine`, `Puzzle`, hidden labels, unrevealed clue objects, or file loader. The controller is the only coordinator allowed to hold both the engine and agent. The engine keeps the complete puzzle private; only `public_view()` and a successful controller action expose clues. The controller asks the proof service to classify a proposed call **before** asking the engine to commit it through `_reveal_proven()`. The engine also checks the proposed status against its private answer when committing a reveal, so an implementation defect cannot silently corrupt game state; that private check never justifies a call or informs a hint. On any rejected verdict, neither engine nor public state changes.

`GameController` deliberately has no public engine accessor, and its supported reveal
operations are `make_call()`, `step()`, and `auto_solve()`. A leading underscore on
`GameEngine._reveal_proven()` is a Python trust-boundary convention, **not** a security
sandbox: code with direct object-memory access can ignore it. The application and GUI
must therefore retain only the controller/public state and never pass the engine to
untrusted or presentation code.

## Modular Monolith Architecture

The codebase is organized as a **Modular Monolith** under `src/griductive/` with high cohesion and explicit trust boundaries. Each subpackage exposes its public API through `__init__.py`:

```text
src/griductive/
├── domain/                    # [Module 1: Domain Entities & Independent Semantics]
│   ├── model.py               # Immutable coordinates, characters, clues, PublicState, Puzzle
│   ├── regions.py             # Board geometry (Row, Col, Neighbors, CommonNeighbors)
│   └── semantics.py           # Independent truth evaluators (ground truth verification)
│
├── solver/                    # [Module 2: Logic & SAT Engine]
│   ├── cnf.py                 # CNF encoding (Sequential counter cardinality, Tseitin parity)
│   ├── dpll.py                # Pure DPLL SAT solver with deterministic metrics
│   ├── kb.py                  # Public knowledge base builder
│   └── logic.py               # Proof service, entailment classification, hints
│
├── game/                      # [Module 3: Game Lifecycle & Interaction]
│   ├── engine.py              # GameEngine (encapsulates private truth, guarded reveal)
│   ├── controller.py          # GameController (coordinates gameplay, hints, auto-solve)
│   └── io.py                  # JSON schema validation and puzzle loading
│
├── analysis/                  # [Module 4: Offline Validation & Benchmarking]
│   ├── validation.py          # Solution uniqueness and playability simulation
│   └── experiments.py         # Performance evaluation pipeline and report exporter
│
├── ui/                        # [Module 5: Presentation]
│   └── gui.py                 # Interactive Tkinter desktop GUI
│
├── (model|cnf|...facades).py  # Top-level backward-compatibility facades
└── __init__.py                # Root package exports
```

### Modules and responsibilities

| Module | Subpackage | Responsibility | Inputs / outputs |
| --- | --- | --- | --- |
| `model.py` | `domain` | Immutable coordinates, characters, region expressions, typed clue variants, public statuses and clue IDs. | Validated value objects; no SAT or GUI imports. |
| `regions.py` | `domain` | Resolve row, column, eight-neighbors, explicit list, and common-neighbors into ordered distinct cell IDs; provide highlight targets. | Region expression + board geometry → tuple of cells. |
| `semantics.py` | `domain` | Independent truth evaluators for all six core templates and both extensions. | Clue + complete primary-status mapping → Boolean. Never imports `cnf.py`. |
| `io.py` | `game` | Read/version puzzle files; validate schema, coordinates, names, clue parameters, initial face-up cards. | File → private `Puzzle` or explicit validation errors. |
| `engine.py` | `game` | Own private puzzle, hidden solution, initial face-up set, reveal state; create immutable public views; restart. | Public views; controller-internal `_reveal_proven(cell, verdict)` → revealed clue/status. |
| `cnf.py` | `solver` | Deterministic primary-variable map, fresh auxiliary allocator, CNF of each typed clue and public known status, formula counts. | `PublicState` → immutable `CNF(num_vars, clauses, primary_map, counts)`. |
| `dpll.py` | `solver` | Custom SAT search, assumptions, complete model, deterministic trace counters and runtime. | CNF + temporary literals → `SAT(model, metrics)` or `UNSAT(metrics)`. |
| `kb.py` | `solver` | Public knowledge base compiled from revealed clues and known statuses at revision $t$. | `PublicState` → compiled `KnowledgeBase`. |
| `logic.py` | `solver` | Base consistency, entailment classification, deterministic forced-card selection, proof query records, hints, deduction steps. | Only `PublicState` + board metadata → classifications/hint/trace. |
| `validation.py` | `analysis` | Offline semantic truth and complete-clue uniqueness checks; optional no-guess playability check. | Private puzzle supplied by engine/tooling → validation report. Not imported by live agent. |
| `controller.py` | `game` | Manual call handling, rejection reason mapping, hint, restart/load/auto-solve, terminal states. | GUI action → updated public view + event/trace. |
| `gui.py` | `ui` | Render grid/clues/highlights and controls; display reasons, hint, progress and metrics. | Controller public view/events only. |
| `experiments.py` | `analysis` | Run fixed puzzle manifest and collect CSV/JSON metrics, failures, timeouts. | Puzzle files + run settings → reportable results. |
| `main.py` | (root) | Thin launch/CLI entry point. | `run`, `validate`, `solve`, and `experiment` commands. |

## Core contracts

- `CellId`: stable coordinate such as `C2`, with one row-major index; `Character`: cell, unique display name, profession. Keep display text separate from identity.
- `Puzzle` (private): grid metadata, all characters, complete `solution: Mapping[CellId, bool]`, all clue objects keyed by owner/ID, initial face-up cell IDs. It must never be passed to `LogicAgent`.
- `PublicState` (immutable snapshot): board metadata and public character labels, revealed clue objects/IDs, known statuses (initial face-up and accepted verdicts), revealed cell IDs, revision. It must contain no placeholder fields carrying hidden status or hidden clue data. A face-down card may be represented by its public character metadata and `revealed=False` only.
- `Clue`: discriminated structured variant. `FACT`, `SAME`, and `DIFFERENT` carry character IDs; count/parity clues carry `RegionExpr`. Each has an ID and owner cell so trace and GUI can identify it. Region resolution returns the counted/highlighted cells; binary and fact clues highlight their referenced cells.
- `CNF`: clauses as tuples of nonzero signed integer literals, deterministic primary map `CellId → 1..N²`, auxiliaries allocated above that range, recorded primary/auxiliary/clause counts. The encoder does not preserve or import private solution data.
- `SatResult`: `SAT` with a total assignment for all declared variables or `UNSAT`, plus decisions, propagations, backtracks, runtime. Calls with assumptions leave base CNF unchanged.
- `Classification`: `CRIMINAL`, `INNOCENT`, `UNKNOWN`, or `INCONSISTENT`, with SAT-query evidence. `CallResult`: accepted or rejected with `NOT_PROVABLE`, `CONTRADICTED`, or invalid/inconsistent state as applicable. The two assignment-prescribed rejection reasons retain their exact names.
- `DeductionStep`: step number, active clue IDs, query assumptions and SAT/UNSAT outcomes (with metrics), chosen cell/verdict, revealed clue ID or none. `Hint` identifies a forced cell and optionally relevant *revealed* clue IDs; relevance can be established by a deletion test or a clearly labeled simpler explanation. Never claim a specific clue alone proves a verdict without checking it.

## Logic pipeline

1. Load and validate structured puzzle data. Resolve references and evaluate **every** clue against the complete solution with `semantics.py`; reject false clues. This is an offline/private operation.
2. Start the engine with initial face-up cards. Publish only their statuses and clues alongside public board labels. Build `KB_t = CNF(revealed clues) ∧ units(known statuses)` on each state revision.
3. Solve `KB_t` once for consistency. If UNSAT, report `INCONSISTENT` and stop calls. For each unresolved cell, solve `KB_t` with temporary `¬C_i` and `C_i` assumptions as needed. An UNSAT opposite assumption proves the verdict; two SAT results give `UNKNOWN`. Record all executed queries and aggregate solver counters.
4. A manual call is classified by that same public proof. If its status is forced, the controller asks the engine to reveal, verifies the returned status, advances the public revision, and records the clue. If neither forced, return `NOT_PROVABLE`; if the opposite is forced, return `CONTRADICTED`. Rejections do not change the revision.
5. Auto Solve classifies all unresolved cards, chooses the first forced card in row-major order, commits and repeats. Stop on solved, inconsistent, or no forced card. Hint uses the same classification without mutation. The GUI renders only the returned public state.
6. Separately, a validator encodes **all** clues plus initial face-up statuses, solves once, adds a single blocking clause over the primary-variable assignment, and solves again. First UNSAT means zero solutions; second UNSAT means exactly one; second SAT means multiple. It never adds the hidden solution as clauses. A separate no-guess simulation checks whether the initial reveal path actually reaches solved.

## Encoding and solver choices

- Encode `FACT` as one unit; `SAME(a,b)` as `(¬a∨b)∧(a∨¬b)`; `DIFFERENT(a,b)` as `(a∨b)∧(¬a∨¬b)`. Reject degenerate references or define them explicitly in validation; the recommended choice is to reject the same participant on both sides.
- Encode `AT_MOST(k)` with a deterministic sequential counter for `0 < k < n`; use units for zero and a tautology for n. Encode `AT_LEAST(k)` by applying at-most to complemented literals with bound `n-k`; encode `EXACTLY(k)` as both. Each encoding call owns fresh auxiliary IDs. Derive a small counting example in the report and compare the CNF to the independent evaluator in tests.
- Encode `PARITY` by chaining XOR gates with Tseitin auxiliaries, then constrain the final parity bit. The evaluator counts true cells modulo 2 independently. `COMMON_NEIGHBORS` is resolved before encoding, so all counting/parity encoders reuse the same region pipeline.
- DPLL uses deterministic unit propagation to a fixed point, detects empty clauses/contradictory assignments, selects the lowest-numbered unassigned variable, tries a fixed truth order, recurses, and backtracks. A SAT leaf fills otherwise unconstrained variables deterministically so the model is total. Metrics count actual branches/forced assignments/backtracks; document the counting convention in code and experiments.
- Treat the base CNF and assumptions as immutable inputs. Rebuild per public revision initially; caching and advanced heuristics are optional later only if evidence justifies them.

## Testing and operational shape

- Unit tests cover region geometry, clue validation, six direct evaluators, parity/common-neighbors, CNF truth preservation against brute-force assignments (existentially quantifying auxiliaries), DPLL SAT/UNSAT/models/metrics, entailment and rejected-call immutability.
- Integration tests use at least one progressive puzzle and a stalled/ambiguous puzzle. Assert the Logic Agent can run from a serialized public view alone and cannot access private fields. Test the GUI controller behavior through public events; use a GUI smoke test where practical.
- Keep several 3×3 and 4×4 puzzle fixtures under `tests/fixtures/` or `puzzles/`, with a fixed experiment manifest. Experimental output should include all required metrics and failed/timeout cases. Add at least one optional 5×5 case only if time permits.
- **Assumption:** A versioned JSON puzzle schema is the recommended file format; the assignment does not prescribe one. **Assumption:** GUI toolkit, timeouts, and exact CLI flags are implementation choices. Record them in `README.md` and the report once selected.
