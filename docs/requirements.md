# Griductive Solver requirements

Source of truth: `docs/assignment.pdf` (9 pages, Project 2, CSC14003). Page numbers below refer to the printed PDF pages. **Required** means stated by the assignment. **Design recommendation** and **Assumption** identify choices made for this project; they are not extra assignment rules.

## Scope and grading

| Area | Points | Required outcome |
| --- | ---: | --- |
| Reimplement the game | 10 | Playable GUI, public proof checks, reveal behavior, highlighting, controls (§4.1, p. 5) |
| Automatic logic and CNF | 10 | Deterministic variables, validation, all clues encoded, public KB, counts, independent evaluators (§4.2, p. 6) |
| DPLL SAT solver | 10 | Unit propagation, conflicts, deterministic branching, backtracking, complete SAT model/UNSAT, metrics (§4.3, p. 6) |
| Deductive agent | 20 | Classify all unresolved cards, only forced calls, reveal loop, trace, separate uniqueness check (§4.4, p. 7) |
| Experiments | 10 | Several 3×3 and 4×4 puzzles and specified metrics (§4.5, p. 7) |
| PDF report | 30 | Planning/contributions, formulation, derivations, algorithms, experiments, references/appendix (§4.6, p. 8) |
| Demo video | 10 | 5–10 minute narrated/subtitled GUI and functionality demo, Drive sharing (§4.7, p. 8) |

## Game and knowledge rules

- **Required (pp. 1–2):** An N×N grid (typically N = 3, 4, or 5) contains one character per cell, each with a hidden Criminal/Innocent status and one structured clue. Rows increase top to bottom; columns use letters left to right (e.g. `C2`). Characters are ordered alphabetically by display name. Names and professions have no logical meaning unless a clue explicitly references them.
- **Required (p. 2):** Some cards start face-up. Their statuses **and** clues are public. A revealed clue is true regardless of its owner's status. Only revealed clues and previously proved/public statuses belong in the step-t KB; hidden statuses and face-down clues must never enter it.
- **Required (pp. 2, 5):** A verdict is accepted only if entailed by the current public KB. Accepting it marks the status and flips the card, making its clue public. A rejected call leaves all state unchanged and reports `NOT_PROVABLE` when both statuses are possible or `CONTRADICTED` when the opposite status is forced. If no verdict is forced, the agent returns `UNKNOWN` and reveals nothing.
- **Required (pp. 2, 7):** A valid puzzle has exactly one complete status assignment; the agent continues until solved or another terminal state. Multiple forced cards must be selected deterministically (row-major is an example). Hint uses public knowledge only.
- **Design recommendation:** Treat an inconsistent public KB as a distinct `INCONSISTENT` result before attempting any entailment, to avoid the vacuous consequence of UNSAT. Treat no forced unresolved card as a stalled/unknown terminal state rather than inventing a guess.
- **Assumption:** “Character order alphabetically” governs display/list order; cell coordinates remain fixed by the input file, and deterministic variable IDs use row-major cell order. This avoids silently changing clue coordinates.
- **Assumption:** Uniqueness of the complete assignment does not guarantee a no-guess reveal path from the initial face-up cards. Puzzle validation should check both separately and report a stalled unique puzzle honestly.

## Clue language and regions

One primary Boolean `C_i` represents character i: true = Criminal, false = Innocent (p. 3). The six **required** structured clue templates (§3.2, p. 3) are:

| Template | Meaning |
| --- | --- |
| `FACT(person, status)` | A named person has the specified status. |
| `SAME(person_a, person_b)` | Their statuses are equal. |
| `DIFFERENT(person_a, person_b)` | Their statuses differ. |
| `EXACTLY(k, region)` | Exactly k criminals in the region. |
| `AT_LEAST(k, region)` | At least k criminals in the region. |
| `AT_MOST(k, region)` | At most k criminals in the region. |

- **Required (pp. 2–3):** Counting regions support row, column, eight-direction neighbors of a cell (excluding itself), and an explicit list of distinct cells. Validate `k` as an integer in `0..|region|`. `NO` may be displayed as `EXACTLY(0, region)`; it is not an additional logical template. An independent direct evaluator must evaluate each of the six templates against a complete assignment without invoking the encoder (§4.2, p. 6).
- **Required (p. 3):** Implement at least two distinct extensions. **Chosen design:** `PARITY(region, EVEN|ODD)` and `COMMON_NEIGHBORS(cell_a, cell_b)` as an advanced region expression usable by counting and parity clues. The latter is an intersection of the two eight-neighbor sets; its semantics must be documented and tested. Other extensions listed in the PDF are examples, not requirements.
- **Design recommendation:** Store clues as typed structured data with stable clue IDs. Validate references, distinct explicit-list members, region bounds, and owner-cell references at load time. Reject malformed data rather than silently correcting it.
- **Assumption:** Empty common-neighbor regions are valid with count 0 and even parity; empty explicit lists are rejected as an input-format choice. `FACT`, `SAME`, and `DIFFERENT` reference unique display names or stable character IDs. Duplicate names are rejected to make named references unambiguous.

## CNF, SAT, and entailment

- **Required (pp. 3–4, 6):** Map characters to primary variables deterministically; keep auxiliary variables separate. Convert every active clue automatically to CNF rather than hard-code puzzle formulas. Add public known statuses as unit clauses. Report primary-variable, auxiliary-variable, and clause counts for each puzzle/KB.
- **Required (p. 4):** First check whether `KB` is SAT. For unresolved i, `KB ∧ ¬C_i` UNSAT proves Criminal; `KB ∧ C_i` UNSAT proves Innocent; both SAT means `UNKNOWN`; unsatisfiable `KB` means `INCONSISTENT`. A single satisfying model is not a proof of a verdict.
- **Required (p. 6):** Implement DPLL in project Python code with unit propagation, conflict detection, deterministic variable selection, recursive branching and backtracking, SAT plus a **complete** assignment or UNSAT, and recorded decisions, propagations, backtracks, and runtime. Direct assumptions or temporary unit clauses are both allowed. Pure-literal elimination and advanced heuristics are optional.
- **Design recommendation:** Use a sequential-counter encoding for cardinalities, including `AT_LEAST(k)` as `AT_MOST(n-k)` over negated literals and `EXACTLY(k)` as both bounds. Handle `k=0` and `k=n` directly. Use a Tseitin XOR chain for parity. This keeps larger explicit regions tractable while preserving a reusable encoder; it is not mandated by the PDF.
- **Design recommendation:** Query the same immutable CNF with temporary assumptions and cache only within a specific public-KB revision. Include the base SAT check in every classification batch; never infer both verdicts from an inconsistent KB.
- **Required (p. 7):** The deduction trace records step number, active clue IDs, SAT queries, verdict, and newly revealed clue. Uniqueness checking is separate from live deduction.
- **Assumption:** The separate uniqueness check uses **all** clues plus initially face-up statuses, but no hidden-solution unit clauses. It finds one complete model, then blocks its primary-variable assignment and solves again; zero/one/multiple models are reported. This is an offline puzzle-validation operation; the live Logic Agent receives only public state.

## GUI and user behavior

- **Required (§4.1, p. 5):** Provide a web or desktop GUI. Show grid and row/column coordinates, character names/professions, known statuses, visible clues, and face-down cards. Let the user call Criminal/Innocent. Show accepted flips and rejected calls with the two specified reasons. Selecting a revealed clue highlights all referenced/counted cells. Provide Load, Restart, Hint, and Auto Solve controls. Hint identifies a relevant revealed clue and/or a currently provable card, using public state only.
- **Design recommendation:** Keep GUI presentation independent of SAT logic; the UI receives a public view and sends actions to a controller. Auto Solve should surface trace, stalled and inconsistent results instead of looping.

## Experiments, report, and delivery

- **Required (§4.5, p. 7):** Evaluate several 3×3 and 4×4 puzzles; 5×5 is optional stress testing. For every case record primary/auxiliary variables, CNF clauses, SAT calls, decisions, propagations, backtracks, deduction steps or reveal waves, and runtime. Use the same puzzle set for every comparison, including failures and timeouts.
- **Required (§4.6, p. 8):** Submit a well-formatted PDF report with member responsibilities, assigned tasks, and each member's completion percentage (fairly assessed); problem formulation; derivations for at least one binary and one counting clue; DPLL, entailment, uniqueness and deduction algorithms; experiment tables/charts, observations, failures, limitations; references; and an appendix such as LLM usage/prompts. The assignment gives an example of individual score = group score × completion percentage.
- **Required (§4.7, p. 8):** Create an approximately 5–10 minute video showing the GUI, manual play, and solver run (including selected stage and found solution). Provide English or Vietnamese narration/subtitles. Upload to Google Drive, allow anyone with the link to view, verify in a private/incognito window, and include the video URL in the report. Do not submit a YouTube link.
- **Required (§5, p. 9):** Package source and report in `.zip` or `.rar`, named `StudentID1_StudentID2_...`. If over 20 MB, upload it to Google Drive and share a link. Make no modifications after the deadline. The example delivery layout has `Source/main.py`, `Source/README.md` (run instructions), `Source/requirements.txt`, and `Report.pdf`.
- **Required (§4 and §6, pp. 5, 9):** Use Python; supporting libraries are allowed, but implement the main algorithms yourselves. This is a group assignment lasting approximately three weeks. AI tools are allowed, but students may face an oral interview; plagiarism/dishonesty/misconduct has a zero-grade consequence.
- **Design recommendation:** Keep development source under repository `src/` and package it into the example `Source/` layout at submission time. Capture reproducible puzzle inputs and machine/environment details for experiments. The PDF does not prescribe a puzzle-file format, GUI framework, test framework, timeout, or deadline date; those must be chosen or supplied by the team.
