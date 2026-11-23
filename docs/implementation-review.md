# Implementation review against assignment.pdf

Reviewed 2026-11-07 against all nine PDF pages, source, fixtures, and tests.
This is a source/test review, not a grade guarantee or confirmation of external deliverables.

## Update from instructor Q&A supplied by the user

The user subsequently supplied instructor clarification: six playable maps are
required, two each at 3x3, 4x4, and 5x5, all with unique solutions. Agent solving
must be animated. A map picker may replace the Load button; multiple initial
face-up cards are allowed. Consequently, the earlier PDF-only assessment below
is incomplete: the two 5x5 maps and solver animation are required,
not optional enhancements. Animation was subsequently implemented as described
below; the map work remains outstanding. Ambiguous/invalid test fixtures do not count
toward the six playable maps. See `references.md` for provenance and research.

## GUI (section 4.1, page 5)

| Requirement | Implementation and evidence | Result |
| --- | --- | --- |
| Grid, coordinates, public names/professions, known statuses, face-up clues, face-down cards | `GriductiveApp._rebuild_board`, `_refresh_ui`, public view model; `tests/test_gui.py` | Implemented |
| Criminal/Innocent calls | Manual verdict buttons route through `GameController.make_call` | Implemented |
| Proved verdict accepts and reveals only that card | Controller proof precedes engine reveal; GUI updates status and clue | Implemented |
| NOT_PROVABLE vs CONTRADICTED without revealing | Controller returns distinct reasons; GUI gives distinct feedback; rejection immutability tests | Implemented |
| Select revealed clues and highlight their referenced/counted cells | Card click and previous/next clue controls call `select_clue`; shared region resolver | Implemented |
| Load, Restart, Hint, Auto Solve | Top bar and action bar; Hint returns forced cell and revealed clue IDs | Implemented |
| Separate private engine and public agent | `GameEngine`, immutable `PublicState`, `LogicAgent`, boundary tests | Implemented |

Layout repair: long clues previously changed requested card sizes. Cards now have
fixed requested dimensions and disable child geometry propagation; equal grid
tracks keep rows/columns aligned. Read-only scrollable clue areas retain all text
on cards and in the inspector. The board has horizontal/vertical scrolling for
larger grids and small windows. Regression tests check long text, scrolling,
selection/highlighting, Auto Solve, and Restart on 3x3 and 4x4 boards.

## Remaining findings

1. **Experiment timeout/failure handling (section 4.5, page 7):**
   `ExperimentRunner.timeout_seconds` is stored and exported but not enforced in
   `run_puzzle`. Unexpected exceptions for normal manifest entries can abort the
   suite instead of preserving a failure row. The deliberately invalid fixture
   does get its own result. Add actual bounded execution and per-case error rows
   before claiming timeout support.
2. **Report (section 4.6, page 8):** No project report PDF was found. The assignment
   PDF and experimental Markdown summary do not substitute for the required
   report, contributions, encoding derivations, references, and AI-use appendix.
3. **Demo (section 4.7, page 8):** No submitted demo artifact/link was verified in
   this review. Need a narrated/subtitled 5-10 minute Drive video and verification
   that anyone with the link can view it.
4. **Submission (section 5, page 9):** No student-ID-named ZIP/RAR or final
   submission layout was found. Dependency/run instructions must be checked in
   a clean environment when preparing the package.
5. **GUI polish:** The later warm-theme redesign updates puzzle title, size and
   progress on Load. Hint used to overwrite the textual forced-verdict banner.
   This hint presentation
   has now been replaced with an evidence banner and explicit highlighting of
   clue-owner cards. The GUI Auto Solve now reveals one card per timer tick and
   supports Pause, with cancellation on Load/Restart. The original synchronous
   API remains for headless callers. A heavy individual SAT step can still block
   the UI thread; a background worker is a remaining improvement.
6. **Documentation status:** `TASKS.md` and the architecture introduction still
   describe much implemented work as pending/nonexistent. Reconcile them with
   verified acceptance checks; do not treat unchecked boxes alone as missing code.

## Other implemented sections

Sections 3.2 and 4.2: six core clue templates, parity and common-neighbor
extensions, automatic CNF, deterministic variable mapping, independent semantic
evaluators, and public-only KB construction are present with tests.

Sections 4.3-4.4: custom deterministic DPLL, complete models, counters,
entailment/UNKNOWN/INCONSISTENT classification, progressive no-guess reveal,
structured deduction traces, and separate full-clue uniqueness checking are
present with tests. GUI history is a short presentation of the structured trace;
the full trace records are maintained by the controller.

Section 4.5: stored CSV/JSON/Markdown experiment results and a fixed manifest are
present. There are three 3x3 cases, two 4x4 cases, and an intentionally invalid
case; only one puzzle of each size is progressively solvable. More playable
fixtures would strengthen evaluation. The PDF alone labels 5x5 optional, but
the subsequent instructor Q&A requires two 5x5 playable maps.

## Validation

Full suite: `python -m pytest -q --basetemp=.pytest_tmp_layout_final`
reported **379 passed, 1 skipped** (Tk display initialization unavailable for one
GUI test in that invocation). Both new layout parametrizations were then run
separately: **1 passed** for 3x3 and **1 passed** for 4x4 against real Tk windows.
Tests do not establish the existence or
sharing permissions of the report, demo, or final archive.

Animation/hint update: full suite
`python -m pytest -q --basetemp=.pytest_tmp_animated_final`:
**388 passed, 1 skipped** (Tk display initialization). New tests verify one reveal
per frame, sequential traces/metrics, cancellation including stale callbacks,
stalling without guessing, evidence-owner highlighting and independent exhaustive
semantic verification that hinted clue sets are sufficient and deletion-minimal.

Warm-theme GUI redesign: board centered, rounded cards, visible public portraits,
compact revealed headers, separate Evidence window, verdict and rejection dialogs.
Modal test verifies Cancel, both rejection reasons, single-card accepted reveal,
clue inspection and Restart. Full suite before unused-builder cleanup:
`python -m pytest -q --basetemp=.pytest_tmp_warm_final`: **389 passed, 1 skipped**;
the 4x4 long-clue GUI test also passed separately. Board/dialog screenshots were
captured and visually inspected at `tmp/gui/warm-board.png` and
`tmp/gui/warm-verdict.png`.
