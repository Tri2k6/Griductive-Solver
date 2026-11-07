"""Playable GUI and presentation layer for Griductive Solver.

Architecture:
- The GUI has NO access to GameEngine, hidden solutions, or unrevealed clues.
- All actions (Call, Hint, Step, Auto Solve, Restart) are routed strictly through GameController.
- Render state is computed exclusively from PublicState and user UI selections.
- Operates both with Tkinter widgets (desktop/X11) and in headless presentation mode (unit/integration tests).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import time
from typing import Any, Mapping
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

from griductive.domain.model import (
    AtLeastClue,
    AtMostClue,
    CellId,
    Character,
    Clue,
    ColRegion,
    CommonNeighborsRegion,
    DifferentClue,
    ExactlyClue,
    ExplicitRegion,
    FactClue,
    NeighborsRegion,
    ParityClue,
    PublicCard,
    PublicState,
    RegionExpr,
    RowRegion,
    SameClue,
    Status,
)
from griductive.domain.regions import get_clue_highlight_cells, resolve_region
from griductive.game.controller import (
    AutoSolveReport,
    AutoSolveStatus,
    CallResult,
    DeductionStep,
    GameController,
    Hint,
    RejectionReason,
)
from griductive.game.io import load_puzzle_from_json
from griductive.solver.dpll import DpllMetrics


# =============================================================================
# Visual Theme Configuration (Warm detective card theme)
# =============================================================================

THEME = {
    "bg_root": "#211c18", "bg_header": "#211c18", "bg_card": "#2c251f",
    "bg_card_innocent": "#30392d", "bg_card_criminal": "#482925",
    "bg_card_selected": "#39312a", "bg_card_highlight": "#403725",
    "border_subtle": "#514940", "border_card": "#5c544b", "border_bright": "#8e8172",
    "border_innocent": "#77c79a", "border_criminal": "#f38578",
    "border_selected": "#d9c9a6", "border_highlight": "#dfb65f", "border_hint": "#9b82fa",
    "purple_accent": "#b89c77", "purple_bg": "#3b3247", "gold_accent": "#dfb65f",
    "text_primary": "#f0e8da", "text_secondary": "#c3b7a5", "text_muted": "#a99b87",
    "btn_bg": "#332b24", "btn_border": "#65594b",
    "crim_btn_bg": "#542c28", "crim_btn_border": "#f38578", "crim_btn_hover": "#6a3831",
    "inn_btn_bg": "#303e31", "inn_btn_border": "#77c79a", "inn_btn_hover": "#405641",
    "badge_innocent_bg": "#30392d", "badge_innocent_fg": "#9bd7ac",
    "badge_criminal_bg": "#482925", "badge_criminal_fg": "#ffab9b",
    "badge_unknown_bg": "#39312a", "badge_unknown_fg": "#d9c9a6",
    "badge_hidden_bg": "#2c251f", "badge_hidden_fg": "#a99b87",
}


class RoundedCard(tk.Frame):
    """Fixed-layout frame with a canvas-drawn rounded background and border."""

    def __init__(self, master, **kwargs):
        self._fill = kwargs.pop("bg", THEME["bg_card"])
        self._stroke = kwargs.pop("highlightbackground", THEME["border_card"])
        self._stroke_width = kwargs.pop("highlightthickness", 2)
        super().__init__(master, bg=THEME["bg_root"], highlightthickness=0, **kwargs)
        self._surface = tk.Canvas(self, bg=THEME["bg_root"], highlightthickness=0)
        self._surface.place(x=0, y=0, relwidth=1, relheight=1, bordermode="ignore")
        self._surface.tk.call("lower", self._surface._w)
        self.bind("<Configure>", self._paint)

    def config(self, cnf=None, **kwargs):
        self._fill = kwargs.pop("bg", self._fill)
        self._stroke = kwargs.pop("highlightbackground", self._stroke)
        self._stroke_width = kwargs.pop("highlightthickness", self._stroke_width)
        result = super().config(cnf, **kwargs)
        self._paint()
        return result

    configure = config

    def _paint(self, event=None):
        w, h, r = self.winfo_width() - 2, self.winfo_height() - 2, 14
        points = [r, 2, w-r, 2, w, 2, w, r, w, h-r, w, h,
                  w-r, h, r, h, 2, h, 2, h-r, 2, r, 2, 2]
        self._surface.delete("all")
        self._surface.create_polygon(points, smooth=True, splinesteps=24,
                                     fill=self._fill, outline=self._stroke,
                                     width=self._stroke_width)


PROFESSION_ICONS: dict[str, str] = {
    "librarian": "📖",
    "chemist": "⚗",
    "art dealer": "🎨",
    "botanist": "🌿",
    "developer": "💻",
    "detective": "🔍",
    "judge": "⚖",
    "doctor": "🩺",
    "engineer": "⚙",
    "teacher": "📚",
    "artist": "🎭",
    "student": "🎓",
    "writer": "✍",
}


def get_profession_icon(profession: str) -> str:
    """Return an appropriate emoji/symbol for a character profession."""
    p_lower = profession.strip().lower()
    for key, icon in PROFESSION_ICONS.items():
        if key in p_lower:
            return icon
    return "💼"


def format_region_text(region: RegionExpr) -> str:
    """Return a clean human-readable representation of a RegionExpr."""
    if isinstance(region, RowRegion):
        return f"Row {region.row}"
    if isinstance(region, ColRegion):
        return f"Column {region.col}"
    if isinstance(region, NeighborsRegion):
        return f"Neighbors of {region.center}"
    if isinstance(region, ExplicitRegion):
        cells_str = ", ".join(str(c) for c in region.cells)
        return f"the cells {cells_str}"
    if isinstance(region, CommonNeighborsRegion):
        return f"Common neighbors of {region.cell_a} & {region.cell_b}"
    return str(region)


def format_clue_text(clue: Clue, state: PublicState | None = None) -> str:
    """Format a Clue into clear, human-readable prose."""
    name_map: dict[CellId, str] = {}
    if state is not None:
        name_map = {c.cell: c.name for c in state.characters}

    if isinstance(clue, FactClue):
        target_name = clue.target_name or name_map.get(clue.target, str(clue.target))
        return f"{target_name} ({clue.target}) is {clue.status.value.lower()}."

    if isinstance(clue, SameClue):
        name_a = clue.name_a or name_map.get(clue.person_a, str(clue.person_a))
        name_b = clue.name_b or name_map.get(clue.person_b, str(clue.person_b))
        return f"{name_a} and {name_b} have the same status (both criminal or both innocent)."

    if isinstance(clue, DifferentClue):
        name_a = clue.name_a or name_map.get(clue.person_a, str(clue.person_a))
        name_b = clue.name_b or name_map.get(clue.person_b, str(clue.person_b))
        return f"{name_a} and {name_b} have different statuses (one criminal and one innocent)."

    if isinstance(clue, ExactlyClue):
        reg = format_region_text(clue.region)
        if clue.k == 0:
            return f"There are no criminals in {reg}."
        return f"Exactly {clue.k} of the people in {reg} are criminals."

    if isinstance(clue, AtLeastClue):
        reg = format_region_text(clue.region)
        return f"At least {clue.k} of the people in {reg} are criminals."

    if isinstance(clue, AtMostClue):
        reg = format_region_text(clue.region)
        return f"At most {clue.k} of the people in {reg} are criminals."

    if isinstance(clue, ParityClue):
        reg = format_region_text(clue.region)
        return f"The number of criminals in {reg} is {clue.parity.value.lower()}."

    return f"Clue {clue.clue_id}"


@dataclass(frozen=True)
class CellViewData:
    """Computed view data for rendering a single cell card."""

    cell: CellId
    character: Character
    is_revealed: bool
    status: Status | None
    status_label: str
    clue: Clue | None
    clue_text: str
    is_selected: bool
    is_highlighted: bool
    is_hinted: bool


class GriductiveApp:
    """Main application presenter and GUI coordinator.

    Maintains separation between logic and view. Can run in headless mode
    (root=None) for tests or with a Tkinter root window for desktop play.
    """

    def __init__(
        self,
        controller: GameController,
        root: tk.Tk | None = None,
        puzzle_source_path: str | Path | None = None,
    ) -> None:
        self.controller = controller
        self.root = root
        self.puzzle_source_path = str(puzzle_source_path) if puzzle_source_path else ""

        # UI selection & highlighting state
        self.selected_cell: CellId | None = None
        self.selected_clue_id: str | None = None
        self.highlighted_cells: frozenset[CellId] = frozenset()
        self.hinted_cell: CellId | None = None
        self.hint_clue_cells: frozenset[CellId] = frozenset()
        self.auto_running = False
        self._auto_after_id: str | None = None
        self._auto_generation = 0
        self._animation_reports: list[AutoSolveReport] = []
        self.animation_delay_ms = 650
        self.current_clue_index: int = 0
        self.log_filter: str = "All"
        self._start_time: float = time.time()

        # Feedback & notifications
        self.status_message: str = "Ready. Select a face-down card to call or use Hint / Auto Solve."
        self.status_subtitle: str = "Use logical deduction to expose all criminals without guessing."
        self.last_rejection_reason: RejectionReason | None = None
        self.last_call_result: CallResult | None = None
        self.last_hint: Hint | None = None
        self.last_auto_solve_report: AutoSolveReport | None = None
        self.trace_log: list[str] = [
            f"Game initialized. Grid size: {self.controller.grid_size}×{self.controller.grid_size}."
        ]
        self._structured_logs: list[tuple[str, str, str, str]] = [
            ("info", "Game initialized", f"Grid {self.controller.grid_size}×{self.controller.grid_size}", "T+00:00")
        ]

        # Tkinter widget references (populated when root is provided)
        self._cell_buttons: dict[CellId, tk.Widget] = {}
        self._status_label: tk.Label | None = None
        self._status_sub_label: tk.Label | None = None
        self._status_icon_label: tk.Label | None = None
        self._clues_listbox: tk.Listbox | None = None
        self._log_text: tk.Text | None = None

        if self.root is not None:
            self._build_ui()
            self._refresh_ui()

    def _get_time_stamp(self) -> str:
        """Return formatted elapsed time string (e.g. T+00:05)."""
        elapsed = int(time.time() - self._start_time)
        mins = elapsed // 60
        secs = elapsed % 60
        return f"T+{mins:02d}:{secs:02d}"

    def _add_log(self, category: str, title: str, detail: str) -> None:
        """Add a structured log item with category tag and timestamp."""
        ts = self._get_time_stamp()
        self._structured_logs.append((category, title, detail, ts))
        self.trace_log.append(f"{title}: {detail}")

    # =========================================================================
    # User Actions (All routed through GameController)
    # =========================================================================

    def load_puzzle(self, puzzle_or_path: str | Path | Any) -> None:
        """Load a new puzzle from file path or Puzzle object."""
        self._dismiss_dialog()
        self.stop_auto_solve()
        try:
            if isinstance(puzzle_or_path, (str, Path)):
                puzzle = load_puzzle_from_json(puzzle_or_path)
                self.puzzle_source_path = str(puzzle_or_path)
            else:
                puzzle = puzzle_or_path
                self.puzzle_source_path = ""

            self.controller = GameController(puzzle)
            self.selected_cell = None
            self.selected_clue_id = None
            self.highlighted_cells = frozenset()
            self.hinted_cell = None
            self.hint_clue_cells = frozenset()
            self.last_rejection_reason = None
            self.last_call_result = None
            self.last_hint = None
            self.last_auto_solve_report = None
            self.current_clue_index = 0
            self._start_time = time.time()
            msg = f"Loaded puzzle ({self.controller.grid_size}×{self.controller.grid_size}) successfully."
            self.status_message = msg
            self.status_subtitle = "New puzzle loaded. Select a card to begin deduction."
            self.trace_log = [msg]
            self._structured_logs = [("info", "Loaded puzzle", f"{self.controller.grid_size}×{self.controller.grid_size}", "T+00:00")]

            if self.root is not None:
                self._rebuild_board()
                self._refresh_ui()
        except Exception as e:
            err_msg = f"Failed to load puzzle: {e}"
            self.status_message = err_msg
            self.status_subtitle = "Please check that the JSON puzzle format is valid."
            self.trace_log.append(f"ERROR: {err_msg}")
            self._structured_logs.append(("error", "Load Error", str(e), self._get_time_stamp()))
            if self.root is not None:
                messagebox.showerror("Load Error", err_msg)
                self._refresh_ui()

    def restart(self) -> None:
        """Reset game to initial face-up view."""
        self._dismiss_dialog()
        self.stop_auto_solve()
        self.controller.restart()
        self.selected_cell = None
        self.selected_clue_id = None
        self.highlighted_cells = frozenset()
        self.hinted_cell = None
        self.hint_clue_cells = frozenset()
        self.last_rejection_reason = None
        self.last_call_result = None
        self.last_hint = None
        self.last_auto_solve_report = None
        self.current_clue_index = 0
        self._start_time = time.time()
        msg = "Puzzle restarted to initial face-up cards."
        self.status_message = msg
        self.status_subtitle = "All progress reset. You can begin solving again."
        self.trace_log = [msg]
        self._structured_logs = [("action", "Restarted", "Restored initial cards", "T+00:00")]
        if self.root is not None:
            self._refresh_ui()

    def select_cell(self, cell: CellId | str) -> None:
        """Select a grid cell for inspection or manual verdict call."""
        target = CellId(cell) if isinstance(cell, str) else cell
        self.selected_cell = target
        card = self.controller.public_state.cards.get(target)
        if card:
            if card.is_revealed and card.clue:
                self.select_clue(card.clue.clue_id)
            else:
                self.clear_highlights()
                self.status_message = f"Selected {target} — {card.character.name}"
                self.status_subtitle = f"{card.character.profession} · Card is currently face-down."
        if self.root is not None:
            self._refresh_ui()

    def select_clue(self, clue_id: str) -> None:
        """Select a revealed clue and highlight all referenced/counted cells."""
        self.hint_clue_cells = frozenset()
        found_clue: Clue | None = None
        rev_clues = list(self.controller.public_state.revealed_clues)
        for idx, c in enumerate(rev_clues):
            if c.clue_id == clue_id:
                found_clue = c
                self.current_clue_index = idx
                break

        if found_clue is None:
            self.status_message = f"Clue {clue_id} is not currently revealed."
            return

        self.selected_clue_id = clue_id
        targets = get_clue_highlight_cells(found_clue, self.controller.grid_size)
        self.highlighted_cells = frozenset(targets)
        self.status_message = f"Inspecting Clue: {found_clue.clue_id}"
        self.status_subtitle = format_clue_text(found_clue, self.controller.public_state)

        if self.root is not None:
            self._refresh_ui()

    def prev_clue(self) -> None:
        """Navigate to the previous revealed clue."""
        rev_clues = list(self.controller.public_state.revealed_clues)
        if not rev_clues:
            return
        self.current_clue_index = (self.current_clue_index - 1) % len(rev_clues)
        self.select_clue(rev_clues[self.current_clue_index].clue_id)

    def next_clue(self) -> None:
        """Navigate to the next revealed clue."""
        rev_clues = list(self.controller.public_state.revealed_clues)
        if not rev_clues:
            return
        self.current_clue_index = (self.current_clue_index + 1) % len(rev_clues)
        self.select_clue(rev_clues[self.current_clue_index].clue_id)

    def clear_highlights(self) -> None:
        """Clear all active clue and region cell highlights."""
        self.selected_clue_id = None
        self.highlighted_cells = frozenset()
        self.hint_clue_cells = frozenset()
        if self.root is not None:
            self._refresh_ui()

    def call_criminal(self) -> CallResult:
        """Submit a manual call that the selected cell is CRIMINAL."""
        return self._make_call(Status.CRIMINAL)

    def call_innocent(self) -> CallResult:
        """Submit a manual call that the selected cell is INNOCENT."""
        return self._make_call(Status.INNOCENT)

    def _make_call(self, proposed_status: Status) -> CallResult:
        """Handle a manual call submission with proper acceptance and rejection feedback."""
        self.stop_auto_solve()
        if self.selected_cell is None:
            self.last_rejection_reason = RejectionReason.INVALID_CELL
            self.status_message = "No cell selected"
            self.status_subtitle = "Please select a face-down character card before calling a verdict."
            res = CallResult(
                cell=CellId.from_coords(1, 1),
                proposed_status=proposed_status,
                accepted=False,
                rejection_reason=RejectionReason.INVALID_CELL,
                message="No cell selected.",
            )
            self.last_call_result = res
            return res

        target = self.selected_cell
        res = self.controller.make_call(target, proposed_status)
        self.last_call_result = res

        if res.accepted:
            self.last_rejection_reason = None
            clue_str = f"Revealed clue {res.revealed_clue.clue_id}" if res.revealed_clue else "No clue"
            self.status_message = f"ACCEPTED: {target} is {proposed_status.value}!"
            self.status_subtitle = f"{clue_str}. New evidence added to Knowledge Base."
            self._add_log("action", f"Action: Revealed {target}", f"as {proposed_status.value}")
            if self.controller.is_solved:
                self.status_message = "PUZZLE SOLVED!"
                self.status_subtitle = "Congratulations! All criminals have been deduced without guessing."
                self._add_log("deduction", "Game Solved", "All character cards have been deduced")
        else:
            self.last_rejection_reason = res.rejection_reason
            if res.rejection_reason == RejectionReason.NOT_PROVABLE:
                self.status_message = "NOT_PROVABLE: Not provable yet"
                self.status_subtitle = "The current information is consistent with both possibilities."
                self._add_log("sat", f"Assumed {target} = Criminal", "SAT (consistent)")
                self._add_log("sat", f"Assumed {target} = Innocent", "SAT (consistent)")
                self._add_log("info", "Result: Not provable yet", "(both cases are possible)")
            elif res.rejection_reason == RejectionReason.CONTRADICTED:
                self.status_message = "CONTRADICTED: Contradicted!"
                self.status_subtitle = f"Evidence proves that {target} CANNOT be {proposed_status.value}."
                self._add_log("sat", f"Assumed {target} = {proposed_status.value}", "UNSAT (contradicted)")
                self._add_log("info", "Result: Contradicted", f"Opposite verdict is forced for {target}")
            else:
                self.status_message = f"REJECTED: {res.rejection_reason.value if res.rejection_reason else 'Unknown'}"
                self.status_subtitle = res.message or ""

        if self.root is not None:
            self._refresh_ui()

        return res

    def hint(self) -> Hint:
        """Request a hint identifying a forced card without mutating game state."""
        self.stop_auto_solve()
        self.hinted_cell = None
        self.clear_highlights()

        h = self.controller.hint()
        self.last_hint = h

        if h.has_forced_cell and h.cell:
            self.hinted_cell = h.cell
            self.selected_cell = h.cell
            self.status_message = f"Hint: {h.cell} is forced to be {h.verdict.value if h.verdict else '?'}"
            self.status_subtitle = "This card can be safely called using current public clues."
            self._add_log("deduction", f"Deduction: {h.cell}", f"must be {h.verdict.value if h.verdict else '?'}")

            if h.relevant_clue_ids:
                rel_id = h.relevant_clue_ids[0]
                self.select_clue(rel_id)
                self.hint_clue_cells = frozenset(
                    clue.owner for clue in self.controller.public_state.revealed_clues
                    if clue.clue_id in h.relevant_clue_ids
                )
                self.status_message = "Hint: Read the highlighted clue cards together"
                self.status_subtitle = (
                    "Clues: " + ", ".join(h.relevant_clue_ids)
                    + ". Combine them with the known statuses to prove the next verdict."
                )
        else:
            self.selected_cell = None
            self.selected_clue_id = None
            self.highlighted_cells = frozenset()
            self.status_message = "No forced cards available without guessing"
            self.status_subtitle = "The puzzle is stalled; no cell can be uniquely proven right now."
            self._add_log("info", "Hint Check", "No forced deductions available")

        if self.root is not None:
            self._refresh_ui()

        return h

    def step(self) -> DeductionStep | None:
        """Execute a single deterministic deduction step."""
        self.stop_auto_solve()
        step_res = self.controller.step()
        if step_res is not None:
            self.status_message = (
                f"STEP {step_res.step_number}: {step_res.target_cell} -> {step_res.target_verdict.value}"
            )
            self.status_subtitle = f"Revealed clue {step_res.revealed_clue_id} after a SAT entailment proof."
            self._add_log(
                "deduction",
                f"Deduction: {step_res.target_cell}",
                f"must be {step_res.target_verdict.value} (from clue {step_res.revealed_clue_id})",
            )
            self.selected_cell = step_res.target_cell
            if self.controller.is_solved:
                self.status_message = "PUZZLE SOLVED!"
                self.status_subtitle = "Puzzle completely solved without guessing!"
                self._add_log("deduction", "Complete", "Puzzle solved successfully")
        else:
            if self.controller.is_solved:
                self.status_message = "Puzzle is already completely solved."
                self.status_subtitle = "All character cards have been exposed."
            else:
                terminal_report = self.controller.auto_solve()
                self.last_auto_solve_report = terminal_report
                if terminal_report.status == AutoSolveStatus.INCONSISTENT:
                    self.status_message = "INCONSISTENT: Public knowledge base is unsatisfiable."
                    self.status_subtitle = "A contradiction exists in public clue clauses."
                else:
                    self.status_message = "STALLED: No cards can be logically proven without guessing."
                    self.status_subtitle = "Solver has reached an ambiguous frontier."
            self._add_log("info", "Step Result", self.status_message)

        if self.root is not None:
            self._refresh_ui()

        return step_res

    def auto_solve(self, max_steps: int | None = None) -> AutoSolveReport:
        """Run the full deduction loop until solved, stalled, or inconsistent."""
        self.stop_auto_solve()
        report = self.controller.auto_solve(max_steps=max_steps)
        self.last_auto_solve_report = report

        for s in report.steps:
            self._add_log(
                "deduction",
                f"Step {s.step_number}: {s.target_cell}",
                f"forced {s.target_verdict.value} (clue: {s.revealed_clue_id})",
            )

        status_text = report.status.value
        self.status_message = f"AUTO SOLVE [{status_text}]: {report.message}"
        self.status_subtitle = f"Steps taken: {report.total_steps} · Total SAT queries: {report.total_sat_calls}"

        if self.root is not None:
            self._refresh_ui()

        return report

    def stop_auto_solve(self) -> None:
        """Cancel pending frames; invalidate callbacks across restart/load/pause."""
        self.auto_running = False
        self._auto_generation += 1
        if self._auto_after_id is not None and self.root is not None:
            self.root.after_cancel(self._auto_after_id)
        self._auto_after_id = None
        if hasattr(self, "_auto_button"):
            self._auto_button.config(text="Auto Solve")

    def toggle_auto_solve(self) -> None:
        """Animate actual public reveals, one proven card per timer callback."""
        if self.auto_running:
            self.stop_auto_solve()
            self.status_message = "Auto Solve paused"
            self._refresh_ui()
            return
        if self.root is None:
            return
        self.stop_auto_solve()
        self.clear_highlights()
        self.hinted_cell = None
        self.last_rejection_reason = None
        self.last_hint = None
        self.last_auto_solve_report = None
        self._animation_reports = []
        self.auto_running = True
        self._auto_button.config(text="Pause")
        generation = self._auto_generation
        self.status_message = "Auto Solve: revealing one proven card at a time"
        self._refresh_ui()
        self._auto_after_id = self.root.after(
            100, lambda: self._animate_next_card(generation)
        )

    def _animate_next_card(self, generation: int) -> None:
        """Never pre-solve hidden cards; each frame advances the controller once."""
        if not self.auto_running or generation != self._auto_generation:
            return
        self._auto_after_id = None
        try:
            report = self.controller.auto_solve(max_steps=1)
        except Exception as exc:
            self.stop_auto_solve()
            self.status_message = "Auto Solve stopped due to an error"
            self.status_subtitle = str(exc)
            self._add_log("error", "Auto Solve", str(exc))
            self._refresh_ui()
            return
        prior_steps = sum(r.total_steps for r in self._animation_reports)
        report = replace(report, steps=tuple(
            replace(step, step_number=prior_steps + index)
            for index, step in enumerate(report.steps, start=1)
        ))
        self._animation_reports.append(report)
        for step in report.steps:
            self.selected_cell = step.target_cell
            self._add_log(
                "deduction", f"Step {step.step_number}: {step.target_cell}",
                f"proved {step.target_verdict.value}; revealed {step.revealed_clue_id}",
            )
            self.status_message = f"Auto Solve: {step.target_cell} is {step.target_verdict.value}"
            self.status_subtitle = format_clue_text(step.revealed_clue, self.controller.public_state)
        self.last_auto_solve_report = replace(
            report,
            steps=tuple(s for r in self._animation_reports for s in r.steps),
            total_steps=sum(r.total_steps for r in self._animation_reports),
            total_sat_calls=sum(r.total_sat_calls for r in self._animation_reports),
            aggregate_metrics=DpllMetrics(
                sum(r.aggregate_metrics.decisions for r in self._animation_reports),
                sum(r.aggregate_metrics.propagations for r in self._animation_reports),
                sum(r.aggregate_metrics.backtracks for r in self._animation_reports),
                sum(r.aggregate_metrics.runtime for r in self._animation_reports),
            ),
        )
        if report.status == AutoSolveStatus.STEP_LIMIT_REACHED:
            assert self.root is not None
            self._auto_after_id = self.root.after(
                self.animation_delay_ms, lambda: self._animate_next_card(generation)
            )
        else:
            self.stop_auto_solve()
            self.status_message = f"AUTO SOLVE [{report.status.value}]: {report.message}"
        self._refresh_ui()

    # =========================================================================
    # Presentation View-Model Helpers
    # =========================================================================

    def get_cell_view_data(self, cell: CellId) -> CellViewData:
        """Compute the view data dictionary for a given cell."""
        state = self.controller.public_state
        card = state.cards[cell]
        is_revealed = card.is_revealed
        status = card.status if is_revealed else None

        if is_revealed:
            status_label = status.value if status else "REVEALED"
            clue = card.clue
            clue_text = format_clue_text(clue, state) if clue else ""
        else:
            status_label = "HIDDEN"
            clue = None
            clue_text = ""

        is_selected = (self.selected_cell == cell)
        is_highlighted = (cell in self.highlighted_cells)
        is_hinted = (self.hinted_cell == cell)

        return CellViewData(
            cell=cell,
            character=card.character,
            is_revealed=is_revealed,
            status=status,
            status_label=status_label,
            clue=clue,
            clue_text=clue_text,
            is_selected=is_selected,
            is_highlighted=is_highlighted,
            is_hinted=is_hinted,
        )

    def get_board_grid(self) -> list[list[CellViewData]]:
        """Return the N×N grid of CellViewData in row-major order."""
        grid: list[list[CellViewData]] = []
        n = self.controller.grid_size
        for row in range(1, n + 1):
            row_items: list[CellViewData] = []
            for col_idx in range(1, n + 1):
                cell = CellId.from_coords(row, col_idx)
                row_items.append(self.get_cell_view_data(cell))
            grid.append(row_items)
        return grid

    def get_revealed_clues_view(self) -> list[dict[str, Any]]:
        """Return structured list of revealed public clues for display."""
        state = self.controller.public_state
        res: list[dict[str, Any]] = []
        for clue in state.revealed_clues:
            res.append(
                {
                    "clue_id": clue.clue_id,
                    "owner": str(clue.owner),
                    "text": format_clue_text(clue, state),
                    "is_selected": (clue.clue_id == self.selected_clue_id),
                }
            )
        return res

    # =========================================================================
    # Tkinter UI Implementation (Warm detective card theme)
    # =========================================================================

    def _build_ui(self) -> None:
        """Keep the board central; move detailed evidence into its own window."""
        assert self.root is not None
        self.root.title("Griductive · A little mystery")
        self.root.geometry(f"1040x{min(880, self.root.winfo_screenheight() - 70)}")
        self.root.minsize(740, 640)
        self.root.config(bg=THEME["bg_root"])
        self.root.protocol("WM_DELETE_WINDOW", self._close_window)
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        for direction in ("Vertical", "Horizontal"):
            style.configure(f"Warm.{direction}.TScrollbar", background=THEME["btn_bg"],
                            troughcolor=THEME["bg_root"], arrowcolor=THEME["text_muted"],
                            bordercolor=THEME["bg_root"], lightcolor=THEME["btn_bg"],
                            darkcolor=THEME["btn_bg"], arrowsize=12)
        self._dialog = None
        header = tk.Frame(self.root, bg=THEME["bg_root"], padx=28, pady=8)
        header.pack(fill=tk.X)
        tk.Label(header, text="Griductive", font=("Georgia", 22, "bold"),
                 bg=THEME["bg_root"], fg=THEME["text_primary"]).pack(side=tk.LEFT)
        self._meta_stats_lbl = tk.Label(header, font=("Segoe UI", 10),
                                       bg=THEME["bg_root"], fg=THEME["text_muted"])
        self._meta_stats_lbl.pack(side=tk.RIGHT)
        self._puzzle_title_lbl = tk.Label(self.root, font=("Segoe UI", 10),
                                         bg=THEME["bg_root"], fg=THEME["text_muted"])
        self._puzzle_title_lbl.pack(pady=(0, 4))
        toolbar = tk.Frame(self.root, bg=THEME["bg_root"])
        toolbar.pack(pady=(0, 6))
        for label, action in [("Load puzzle", self._on_load_button),
                              ("Restart", self.restart), ("Hint", self.hint),
                              ("Auto Solve", self.toggle_auto_solve),
                              ("Evidence", self._show_evidence)]:
            button = tk.Button(toolbar, text=label, command=action,
                               font=("Segoe UI", 10, "bold"), bg=THEME["btn_bg"],
                               fg=THEME["text_primary"], activebackground=THEME["btn_border"],
                               activeforeground=THEME["text_primary"], relief=tk.FLAT,
                               borderwidth=0, padx=18, pady=9, cursor="hand2")
            button.pack(side=tk.LEFT, padx=4)
            if label == "Auto Solve":
                self._auto_button = button
        tk.Label(self.root, text="Read the clues. Prove a verdict. Uncover the next lead.",
                 font=("Segoe UI", 10), bg=THEME["bg_root"],
                 fg=THEME["text_secondary"]).pack(pady=(0, 4))
        self._board_status = tk.Label(self.root, font=("Segoe UI", 10),
                                      bg=THEME["bg_root"], fg=THEME["text_secondary"],
                                      wraplength=800, pady=12)
        self._board_status.pack(side=tk.BOTTOM, fill=tk.X)
        self._left_col = tk.Frame(self.root, bg=THEME["bg_root"])
        self._left_col.pack(fill=tk.BOTH, expand=True, padx=20)

        self._evidence_window = tk.Toplevel(self.root)
        self._evidence_window.withdraw()
        self._evidence_window.title("Evidence · Griductive")
        self._evidence_window.geometry("500x820")
        self._evidence_window.config(bg=THEME["bg_root"])
        self._evidence_window.protocol("WM_DELETE_WINDOW", self._evidence_window.withdraw)
        self._right_col = tk.Frame(self._evidence_window, bg=THEME["bg_root"], padx=14, pady=14)
        self._right_col.pack(fill=tk.BOTH, expand=True)
        self._build_notification_banner()
        self._build_inspector_panel()
        self._build_manual_verdict_bar()
        self._build_action_button_bar()
        self._build_deduction_history_panel()
        # The visible toolbar owns the animation control.
        self._auto_button = toolbar.winfo_children()[3]
        self._rebuild_board()

    def _show_evidence(self) -> None:
        self._evidence_window.deiconify()
        self._evidence_window.lift()

    def _dismiss_dialog(self) -> None:
        dialog = getattr(self, "_dialog", None)
        if dialog is not None and dialog.winfo_exists():
            dialog.grab_release()
            dialog.destroy()
        self._dialog = None

    def _new_dialog(self, title: str) -> tk.Frame:
        self._dismiss_dialog()
        assert self.root is not None
        dialog = tk.Toplevel(self.root)
        self._dialog = dialog
        dialog.withdraw()
        dialog.transient(self.root)
        dialog.title(title)
        dialog.config(bg=THEME["bg_root"])
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", self._dismiss_dialog)
        dialog.bind("<Escape>", lambda e: self._dismiss_dialog())
        panel = RoundedCard(dialog, bg=THEME["bg_card"], padx=28, pady=24)
        panel.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        return panel

    def _present_dialog(self) -> None:
        assert self.root is not None and self._dialog is not None
        self._dialog.update_idletasks()
        width, height = 480, max(300, self._dialog.winfo_reqheight())
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
        self._dialog.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        self._dialog.deiconify()
        self._dialog.grab_set()
        self._dialog.focus_set()

    def _dialog_text(self, panel: tk.Frame, text: str, heading: bool = False) -> None:
        tk.Label(panel, text=text, wraplength=390, justify=tk.CENTER,
                 font=("Georgia", 19, "bold") if heading else ("Segoe UI", 11),
                 bg=THEME["bg_card"], fg=THEME["text_primary"] if heading else THEME["text_secondary"],
                 pady=10).pack(fill=tk.X)

    def _on_card_click(self, cell: CellId) -> None:
        """Inspect a public clue or ask for a verdict without revealing anything."""
        self.stop_auto_solve()
        self.select_cell(cell)
        card = self.controller.public_state.cards[cell]
        panel = self._new_dialog(card.character.name)
        portrait = tk.Canvas(panel, width=88, height=88, bg=THEME["bg_card"], highlightthickness=0)
        portrait.pack()
        portrait.update_idletasks()
        self._draw_avatar(portrait, card.is_revealed, card.status == Status.CRIMINAL,
                          False, card.character.name, card.character.profession)
        self._dialog_text(panel, card.character.name, heading=True)
        self._dialog_text(panel, f"{cell}  ·  {card.character.profession}")
        if card.is_revealed:
            self._dialog_text(panel, card.status.value.title(), heading=True)
            clue = ScrolledText(panel, width=38, height=5, wrap=tk.WORD,
                                font=("Segoe UI", 12), bg=THEME["bg_card"],
                                fg=THEME["text_primary"], relief=tk.FLAT)
            clue.insert("1.0", format_clue_text(card.clue, self.controller.public_state))
            clue.config(state=tk.DISABLED)
            clue.pack(fill=tk.X, pady=10)
        else:
            self._dialog_text(panel, "Innocent or criminal?", heading=True)
            self._dialog_text(panel, "Choose a verdict the revealed clues can prove.\nAn accepted verdict flips this card and reveals its clue.")
            choices = tk.Frame(panel, bg=THEME["bg_card"])
            choices.pack(fill=tk.X, pady=12)
            for label, status, bg, fg in [
                ("Innocent", Status.INNOCENT, THEME["inn_btn_bg"], THEME["border_innocent"]),
                ("Criminal", Status.CRIMINAL, THEME["crim_btn_bg"], THEME["border_criminal"]),
            ]:
                tk.Button(choices, text=label, command=lambda verdict=status: self._dialog_verdict(verdict),
                          font=("Segoe UI", 12, "bold"), bg=bg, fg=fg,
                          activebackground=bg, activeforeground=fg, relief=tk.FLAT,
                          padx=24, pady=14, cursor="hand2").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        tk.Button(panel, text="Close" if card.is_revealed else "Cancel",
                  command=self._dismiss_dialog, bg=THEME["bg_card"], fg=THEME["text_muted"],
                  font=("Segoe UI", 10, "bold"), relief=tk.FLAT, pady=8).pack(pady=(8, 0))
        self._present_dialog()

    def _dialog_verdict(self, status: Status) -> None:
        self._dismiss_dialog()
        result = self._make_call(status)
        if result.accepted:
            return
        panel = self._new_dialog("Verdict not accepted")
        contradicted = result.rejection_reason == RejectionReason.CONTRADICTED
        self._dialog_text(panel, "The clues say otherwise" if contradicted else "Conclusion not possible", heading=True)
        self._dialog_text(panel, result.rejection_reason.value if result.rejection_reason else "Rejected")
        target = self.controller.public_state.cards[result.cell].character.name if result.cell else "This person"
        explanation = (
            f"The revealed clues prove the opposite verdict for {target}. Revisit the revealed evidence."
            if contradicted else
            f"The revealed clues do not yet prove that {target} is {status.value.lower()}. Both statuses are still possible. Open another lead or ask for a hint."
        )
        self._dialog_text(panel, explanation)
        tk.Button(panel, text="Keep looking", command=self._dismiss_dialog,
                  bg=THEME["border_criminal"], fg=THEME["bg_root"],
                  font=("Segoe UI", 11, "bold"), relief=tk.FLAT, padx=26, pady=12).pack(pady=12)
        self._present_dialog()

    def _close_window(self) -> None:
        """Stop queued animation before disposing Tk widgets."""
        self.stop_auto_solve()
        assert self.root is not None
        self.root.destroy()

    def _build_notification_banner(self) -> None:
        """Build top notification alert container in the sidebar."""
        self._banner_frame = tk.Frame(
            self._right_col,
            bg=THEME["purple_bg"],
            highlightbackground=THEME["border_hint"],
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        self._banner_frame.pack(fill=tk.X, pady=(0, 10))

        # Icon left
        self._status_icon_label = tk.Label(
            self._banner_frame,
            text="ⓘ",
            font=("Helvetica", 16, "bold"),
            bg=THEME["purple_bg"],
            fg=THEME["purple_accent"],
        )
        self._status_icon_label.pack(side=tk.LEFT, padx=(0, 10), anchor="n")

        # Texts right
        text_box = tk.Frame(self._banner_frame, bg=THEME["purple_bg"])
        text_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._status_label = tk.Label(
            text_box,
            text=self.status_message,
            font=("Helvetica", 11, "bold"),
            bg=THEME["purple_bg"],
            fg=THEME["text_primary"],
            anchor="w",
            justify=tk.LEFT,
        )
        self._status_label.pack(fill=tk.X)

        self._status_sub_label = tk.Label(
            text_box,
            text=self.status_subtitle,
            font=("Helvetica", 9, "italic"),
            bg=THEME["purple_bg"],
            fg=THEME["text_secondary"],
            anchor="w",
            justify=tk.LEFT,
            wraplength=360,
        )
        self._status_sub_label.pack(fill=tk.X, pady=(2, 0))

    def _build_inspector_panel(self) -> None:
        """Build side-by-side Selected Character and Current Clue inspector cards."""
        insp_container = tk.Frame(self._right_col, bg=THEME["bg_root"])
        insp_container.pack(fill=tk.X, pady=(0, 10))

        # Left Card: Selected Character
        char_card = tk.Frame(
            insp_container,
            bg=THEME["bg_card"],
            highlightbackground=THEME["border_subtle"],
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        char_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        tk.Label(
            char_card,
            text="👤  Selected Character",
            font=("Helvetica", 8, "bold"),
            bg=THEME["bg_card"],
            fg=THEME["text_muted"],
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 4))

        char_body = tk.Frame(char_card, bg=THEME["bg_card"])
        char_body.pack(fill=tk.BOTH, expand=True)

        self._char_avatar_canvas = tk.Canvas(
            char_body,
            width=38,
            height=38,
            bg=THEME["btn_bg"],
            highlightthickness=0,
        )
        self._char_avatar_canvas.pack(side=tk.LEFT, padx=(0, 8), pady=2)

        char_text = tk.Frame(char_body, bg=THEME["bg_card"])
        char_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._insp_char_title = tk.Label(
            char_text,
            text="None selected",
            font=("Helvetica", 9, "bold"),
            bg=THEME["bg_card"],
            fg=THEME["text_primary"],
            anchor="w",
        )
        self._insp_char_title.pack(fill=tk.X)

        self._insp_char_prof = tk.Label(
            char_text,
            text="Click a card to inspect",
            font=("Helvetica", 8),
            bg=THEME["bg_card"],
            fg=THEME["text_muted"],
            anchor="w",
        )
        self._insp_char_prof.pack(fill=tk.X)

        self._insp_char_badge = tk.Label(
            char_text,
            text="UNKNOWN",
            font=("Helvetica", 7, "bold"),
            bg=THEME["badge_unknown_bg"],
            fg=THEME["badge_unknown_fg"],
            padx=5,
            pady=1,
        )
        self._insp_char_badge.pack(anchor="w", pady=(2, 0))

        # Right Card: Current Clue with Pagination
        clue_card = tk.Frame(
            insp_container,
            bg=THEME["bg_card"],
            highlightbackground=THEME["border_subtle"],
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        clue_card.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        clue_header = tk.Frame(clue_card, bg=THEME["bg_card"])
        clue_header.pack(fill=tk.X, pady=(0, 4))

        tk.Label(
            clue_header,
            text="📄  Current Clue",
            font=("Helvetica", 8, "bold"),
            bg=THEME["bg_card"],
            fg=THEME["text_muted"],
        ).pack(side=tk.LEFT)

        nav_box = tk.Frame(clue_header, bg=THEME["bg_card"])
        nav_box.pack(side=tk.RIGHT)

        tk.Button(
            nav_box,
            text="‹",
            font=("Helvetica", 9, "bold"),
            bg=THEME["btn_bg"],
            fg=THEME["text_secondary"],
            activebackground=THEME["border_bright"],
            activeforeground="white",
            relief=tk.FLAT,
            bd=0,
            padx=4,
            pady=0,
            command=self.prev_clue,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=1)

        self._clue_page_lbl = tk.Label(
            nav_box,
            text="0 / 0",
            font=("Helvetica", 7),
            bg=THEME["bg_card"],
            fg=THEME["text_muted"],
            padx=3,
        )
        self._clue_page_lbl.pack(side=tk.LEFT)

        tk.Button(
            nav_box,
            text="›",
            font=("Helvetica", 9, "bold"),
            bg=THEME["btn_bg"],
            fg=THEME["text_secondary"],
            activebackground=THEME["border_bright"],
            activeforeground="white",
            relief=tk.FLAT,
            bd=0,
            padx=4,
            pady=0,
            command=self.next_clue,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=1)

        self._clue_prose_lbl = ScrolledText(
            clue_card,
            font=("Helvetica", 8, "italic"),
            bg=THEME["bg_card"],
            fg=THEME["text_primary"],
            width=1, height=3, wrap=tk.WORD, state=tk.DISABLED,
            relief=tk.FLAT, borderwidth=0, highlightthickness=0,
        )
        self._clue_prose_lbl.pack(fill=tk.X, pady=(2, 0))

        self._clue_refs_lbl = tk.Label(
            clue_card,
            text="👁  Referenced cells: None",
            font=("Helvetica", 7, "bold"),
            bg=THEME["bg_card"],
            fg=THEME["gold_accent"],
            anchor="w",
        )
        self._clue_refs_lbl.pack(fill=tk.X, pady=(2, 0))

    def _build_manual_verdict_bar(self) -> None:
        """Build Call Criminal and Call Innocent action buttons."""
        bar = tk.Frame(
            self._right_col,
            bg=THEME["bg_card"],
            highlightbackground=THEME["border_subtle"],
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        bar.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            bar,
            text="⚖  Manual Verdict",
            font=("Helvetica", 8, "bold"),
            bg=THEME["bg_card"],
            fg=THEME["text_muted"],
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 6))

        btn_box = tk.Frame(bar, bg=THEME["bg_card"])
        btn_box.pack(fill=tk.X)

        self._call_crim_btn = tk.Button(
            btn_box,
            text="🎭  Call Criminal",
            bg=THEME["crim_btn_bg"],
            fg="white",
            activebackground=THEME["crim_btn_hover"],
            activeforeground="white",
            highlightbackground=THEME["crim_btn_border"],
            highlightthickness=1,
            relief=tk.FLAT,
            bd=0,
            font=("Helvetica", 10, "bold"),
            padx=12,
            pady=8,
            command=self.call_criminal,
            cursor="hand2",
        )
        self._call_crim_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self._call_inn_btn = tk.Button(
            btn_box,
            text="✓  Call Innocent",
            bg=THEME["inn_btn_bg"],
            fg="white",
            activebackground=THEME["inn_btn_hover"],
            activeforeground="white",
            highlightbackground=THEME["inn_btn_border"],
            highlightthickness=1,
            relief=tk.FLAT,
            bd=0,
            font=("Helvetica", 10, "bold"),
            padx=12,
            pady=8,
            command=self.call_innocent,
            cursor="hand2",
        )
        self._call_inn_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(6, 0))

    def _build_action_button_bar(self) -> None:
        """Build Hint, Step, Auto Solve, and Restart button row."""
        bar = tk.Frame(self._right_col, bg=THEME["bg_root"])
        bar.pack(fill=tk.X, pady=(0, 10))

        actions = [
            ("💡 Hint", self.hint),
            ("⏭ Step", self.step),
            ("⚡ Auto Solve", self.toggle_auto_solve),
            ("🔄 Restart", self.restart),
        ]

        for idx, (label, cmd) in enumerate(actions):
            b = tk.Button(
                bar,
                text=label,
                bg=THEME["btn_bg"],
                fg=THEME["text_primary"],
                activebackground=THEME["border_bright"],
                activeforeground="white",
                relief=tk.FLAT,
                bd=0,
                font=("Helvetica", 9, "bold"),
                padx=10,
                pady=7,
                command=cmd,
                cursor="hand2",
            )
            b.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0 if idx == 0 else 4, 0))
            if idx == 2:
                self._auto_button = b

    def _build_deduction_history_panel(self) -> None:
        """Build Deduction History & Solver Evidence panel with filter tabs."""
        panel = tk.Frame(
            self._right_col,
            bg=THEME["bg_card"],
            highlightbackground=THEME["border_subtle"],
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        panel.pack(fill=tk.BOTH, expand=True)

        header = tk.Frame(panel, bg=THEME["bg_card"])
        header.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            header,
            text="📚  Deduction History / Evidence",
            font=("Helvetica", 8, "bold"),
            bg=THEME["bg_card"],
            fg=THEME["text_muted"],
        ).pack(side=tk.LEFT)

        # Filter Pills
        tabs_box = tk.Frame(header, bg=THEME["bg_card"])
        tabs_box.pack(side=tk.RIGHT)

        for tab_name in ["All", "SAT", "Deductions", "Actions"]:
            lbl = tk.Label(
                tabs_box,
                text=tab_name,
                font=("Helvetica", 7, "bold"),
                bg=THEME["purple_accent"] if tab_name == "All" else THEME["btn_bg"],
                fg="white" if tab_name == "All" else THEME["text_secondary"],
                padx=6,
                pady=1,
                cursor="hand2",
            )
            lbl.pack(side=tk.LEFT, padx=1)
            lbl.bind("<Button-1>", lambda e, name=tab_name: self._set_log_filter(name))

        # Hidden clue listbox maintained for 100% test contract compatibility
        self._clues_listbox = tk.Listbox(panel, height=1)
        # Text log widget styled dark glass
        self._log_text = tk.Text(
            panel,
            bg=THEME["bg_card"],
            fg=THEME["text_secondary"],
            insertbackground="white",
            relief=tk.FLAT,
            bd=0,
            font=("Consolas", 8),
            wrap=tk.WORD,
            highlightthickness=0,
            spacing1=3,
            spacing3=3,
        )
        self._log_text.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

    def _set_log_filter(self, filter_name: str) -> None:
        """Set active log filter tab and refresh display."""
        self.log_filter = filter_name
        self._refresh_ui()

    # =========================================================================
    # Character Board Rendering
    # =========================================================================

    def _rebuild_board(self) -> None:
        """Reconstruct the interactive grid cards matching the design."""
        assert self.root is not None
        for w in self._left_col.winfo_children():
            w.destroy()

        self._cell_buttons.clear()
        n = self.controller.grid_size

        # A scrollable viewport keeps large boards usable in smaller windows.
        viewport = tk.Canvas(self._left_col, bg=THEME["bg_root"], highlightthickness=0)
        vertical = ttk.Scrollbar(self._left_col, orient=tk.VERTICAL, command=viewport.yview,
                                 style="Warm.Vertical.TScrollbar")
        horizontal = ttk.Scrollbar(self._left_col, orient=tk.HORIZONTAL, command=viewport.xview,
                                   style="Warm.Horizontal.TScrollbar")
        vertical.pack(side=tk.RIGHT, fill=tk.Y)
        horizontal.pack(side=tk.BOTTOM, fill=tk.X)
        viewport.pack(fill=tk.BOTH, expand=True)
        viewport.config(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        board_grid_frame = tk.Frame(viewport, bg=THEME["bg_root"])
        board_window = viewport.create_window((0, 0), window=board_grid_frame, anchor="nw")
        board_grid_frame.bind(
            "<Configure>", lambda e: viewport.config(scrollregion=viewport.bbox("all"))
        )
        def fit_board(event):
            height = max(128, min(190, (event.height - 32) // n - 12))
            width = max(n * 170 + 30, min(event.width - 20, n * 195 + 30))
            for card in self._cell_buttons.values():
                card.config(height=height)
            viewport.itemconfigure(board_window, width=width)
            viewport.coords(board_window, max(0, (event.width - width) / 2), 0)
        viewport.bind("<Configure>", fit_board)

        # Coordinate column headers (A, B, C...)
        for c in range(1, n + 1):
            col_letter = chr(ord("A") + c - 1)
            lbl = tk.Label(
                board_grid_frame,
                text=col_letter,
                font=("Helvetica", 11, "bold"),
                bg=THEME["bg_root"],
                fg=THEME["text_muted"],
            )
            lbl.grid(row=0, column=c, padx=6, pady=(0, 6))

        # Coordinate row headers (1, 2, 3...)
        for r in range(1, n + 1):
            lbl = tk.Label(
                board_grid_frame,
                text=str(r),
                font=("Helvetica", 11, "bold"),
                bg=THEME["bg_root"],
                fg=THEME["text_muted"],
            )
            lbl.grid(row=r, column=0, padx=(0, 8), pady=6)

        # Create character card widget for each cell
        for r in range(1, n + 1):
            for c in range(1, n + 1):
                cell = CellId.from_coords(r, c)

                card_frame = RoundedCard(
                    board_grid_frame,
                    bg=THEME["bg_card"],
                    highlightbackground=THEME["border_card"],
                    highlightthickness=2,
                    padx=10,
                    pady=8,
                    cursor="hand2",
                    width=168,
                    height=190,
                )
                card_frame.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")
                card_frame.pack_propagate(False)
                card_frame._surface.bind("<Button-1>", lambda e, cell=cell: self._on_card_click(cell))
                card_frame.bind("<Button-1>", lambda e, cell=cell: self._on_card_click(cell))

                # 1. Top row: Coordinate pill
                top_row = tk.Frame(card_frame, bg=THEME["bg_card"])
                top_row.pack(fill=tk.X, anchor="w")
                top_row.bind("<Button-1>", lambda e, cell=cell: self._on_card_click(cell))

                coord_lbl = tk.Label(
                    top_row,
                    text=str(cell),
                    font=("Helvetica", 8, "bold"),
                    bg=THEME["btn_bg"],
                    fg=THEME["text_secondary"],
                    padx=5,
                    pady=1,
                )
                coord_lbl.pack(side=tk.LEFT)
                coord_lbl.bind("<Button-1>", lambda e, cell=cell: self._on_card_click(cell))

                identity = tk.Frame(top_row, bg=THEME["bg_card"])
                identity.bind("<Button-1>", lambda e, cell=cell: self._on_card_click(cell))
                compact_name = tk.Label(identity, font=("Segoe UI", 10, "bold"),
                                        bg=THEME["bg_card"], fg=THEME["text_primary"])
                compact_name.pack(anchor="e")
                compact_prof = tk.Label(identity, font=("Segoe UI", 8),
                                        bg=THEME["bg_card"], fg=THEME["text_muted"])
                compact_prof.pack(anchor="e")
                for label in (compact_name, compact_prof):
                    label.bind("<Button-1>", lambda e, cell=cell: self._on_card_click(cell))

                # 2. Avatar Canvas (procedural silhouette / portrait)
                avatar_canvas = tk.Canvas(
                    card_frame,
                    width=80,
                    height=75,
                    bg=THEME["bg_card"],
                    highlightthickness=0,
                )
                avatar_canvas.pack(fill=tk.X, pady=(2, 2))
                avatar_canvas.bind("<Button-1>", lambda e, cell=cell: self._on_card_click(cell))
                avatar_canvas.bind("<Configure>", lambda e, cell=cell: self._redraw_cell_avatar(cell))

                # 3. Name Label
                name_lbl = tk.Label(
                    card_frame,
                    text="",
                    font=("Segoe UI", 11, "bold"),
                    bg=THEME["bg_card"],
                    fg=THEME["text_primary"],
                    anchor="center",
                )
                name_lbl.pack(fill=tk.X)
                name_lbl.bind("<Button-1>", lambda e, cell=cell: self._on_card_click(cell))

                # 4. Profession Label with icon
                prof_lbl = tk.Label(
                    card_frame,
                    text="",
                    font=("Helvetica", 8),
                    bg=THEME["bg_card"],
                    fg=THEME["text_muted"],
                    anchor="center",
                )
                prof_lbl.pack(fill=tk.X)
                prof_lbl.bind("<Button-1>", lambda e, cell=cell: self._on_card_click(cell))

                # 5. Status Badge Pill
                status_badge = tk.Label(
                    card_frame,
                    text="?",
                    font=("Helvetica", 8, "bold"),
                    bg=THEME["badge_hidden_bg"],
                    fg=THEME["badge_hidden_fg"],
                    padx=8,
                    pady=2,
                )
                status_badge.pack(pady=(4, 0))
                status_badge.bind("<Button-1>", lambda e, cell=cell: self._on_card_click(cell))

                # Only public clues are placed on the face of revealed cards.
                clue_snippet = tk.Text(
                    card_frame, font=("Segoe UI", 10, "bold"),
                    bg=THEME["bg_card"], fg=THEME["text_primary"],
                    width=1, height=4, wrap=tk.WORD, relief=tk.FLAT,
                    borderwidth=0, highlightthickness=0, state=tk.DISABLED,
                    cursor="hand2", takefocus=False,
                )
                clue_snippet.tag_configure("center", justify=tk.CENTER)
                clue_snippet.bind("<Button-1>", lambda e, cell=cell: self._on_card_click(cell))

                card_frame._widgets = {  # type: ignore[attr-defined]
                    "top_row": top_row,
                    "coord": coord_lbl,
                    "canvas": avatar_canvas,
                    "name": name_lbl,
                    "prof": prof_lbl,
                    "badge": status_badge,
                    "clue": clue_snippet,
                    "identity": identity,
                    "compact_name": compact_name,
                    "compact_prof": compact_prof,
                }
                self._cell_buttons[cell] = card_frame

        # Configure responsive grid expansion
        for i in range(1, n + 1):
            board_grid_frame.grid_columnconfigure(i, weight=1, uniform="cards")
            board_grid_frame.grid_rowconfigure(i, weight=1, uniform="cards")

    def _redraw_cell_avatar(self, cell: CellId) -> None:
        """Redraw avatar for a specific cell after layout configure."""
        if cell not in self._cell_buttons:
            return
        card_frame = self._cell_buttons[cell]
        w = card_frame._widgets  # type: ignore[attr-defined]
        view_data = self.get_cell_view_data(cell)
        is_crim = (view_data.status == Status.CRIMINAL)
        self._draw_avatar(
            w["canvas"],
            is_revealed=view_data.is_revealed,
            is_criminal=is_crim,
            is_selected=view_data.is_selected,
            name=view_data.character.name,
            profession=view_data.character.profession,
        )

    def _redraw_inspector_avatar(self) -> None:
        """Redraw the avatar inside the Selected Character inspector card."""
        if not hasattr(self, "_char_avatar_canvas") or self._char_avatar_canvas is None:
            return
        if self.selected_cell is not None:
            card = self.controller.public_state.cards.get(self.selected_cell)
            if card:
                is_crim = (card.status == Status.CRIMINAL)
                self._draw_avatar(
                    self._char_avatar_canvas,
                    is_revealed=card.is_revealed,
                    is_criminal=is_crim,
                    is_selected=True,
                    name=card.character.name,
                    profession=card.character.profession,
                    size_override=38,
                )
                return
        self._char_avatar_canvas.delete("all")

    def _draw_avatar(
        self,
        canvas: tk.Canvas,
        is_revealed: bool,
        is_criminal: bool,
        is_selected: bool,
        name: str,
        profession: str = "",
        size_override: int | None = None,
    ) -> None:
        """Render a stylish illustrated character portrait or mysterious silhouette."""
        canvas.delete("all")
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w <= 1:
            w = size_override or int(canvas.cget("width"))
        if h <= 1:
            h = size_override or int(canvas.cget("height"))
        cx = w / 2
        cy = h / 2

        radius = min(32, int(min(w, h) * 0.44))

        # Circular outer container halo
        border_color = (
            THEME["border_criminal"]
            if is_criminal
            else (THEME["border_selected"] if is_selected else (THEME["border_innocent"] if is_revealed else THEME["border_card"]))
        )
        bg_circle = (
            "#2a1017"
            if is_criminal
            else (THEME["bg_card_selected"] if is_selected else ("#102820" if is_revealed else THEME["bg_card"]))
        )

        canvas.create_oval(
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
            fill=bg_circle,
            outline=border_color,
            width=2,
        )

        # Stylized character portrait based on name and profession
        skin = "#ecc7ad"
        hair = "#222026"
        clothes = "#334155"
        has_glasses = False
        has_beard = False
        style = "short"

        n_low = name.lower()
        p_low = profession.lower()

        if "evan" in n_low or "chemist" in p_low or "bob" in n_low:
            skin = "#ecc7ad"
            hair = "#222026"
            clothes = "#475569"
            has_glasses = True
            style = "wavy"
        elif "marin" in n_low or "art" in p_low or "alice" in n_low:
            skin = "#f0cbb5"
            hair = "#8c3623"
            clothes = "#5b1d28"
            style = "wavy_long"
        elif "rowan" in n_low or "botanist" in p_low or "david" in n_low:
            skin = "#deb397"
            hair = "#cbd5e1"
            clothes = "#2d3e33"
            has_glasses = True
            has_beard = True
            style = "parted"
        elif "nora" in n_low or "developer" in p_low or "eve" in n_low:
            skin = "#e8beac"
            hair = "#18181b"
            clothes = "#1e293b"
            style = "bob"
        elif "iris" in n_low or "librarian" in p_low or "grace" in n_low:
            skin = "#ebd0be"
            hair = "#3b2219"
            clothes = "#4a3b32"
            style = "bun"
        else:
            h_val = sum(ord(c) for c in name)
            skin_tones = ["#ebd0be", "#ecc7ad", "#e2b196", "#d49b78", "#baa088"]
            hair_tones = ["#18181b", "#3b2219", "#78350f", "#b45309", "#94a3b8"]
            clothes_tones = ["#334155", "#475569", "#1e293b", "#3b4252", "#2e3440"]
            skin = skin_tones[h_val % len(skin_tones)]
            hair = hair_tones[(h_val // 2) % len(hair_tones)]
            clothes = clothes_tones[(h_val // 3) % len(clothes_tones)]
            if (h_val % 3) == 0:
                has_glasses = True
            if (h_val % 4) == 0:
                has_beard = True

        r_scale = radius / 32.0

        # Clothes / Torso
        canvas.create_arc(
            cx - 25 * r_scale,
            cy + 8 * r_scale,
            cx + 25 * r_scale,
            cy + 46 * r_scale,
            start=0,
            extent=180,
            fill=clothes,
            outline="",
        )
        # Neck / Collar
        canvas.create_polygon(
            cx - 6 * r_scale,
            cy + 8 * r_scale,
            cx + 6 * r_scale,
            cy + 8 * r_scale,
            cx + 4 * r_scale,
            cy + 20 * r_scale,
            cx - 4 * r_scale,
            cy + 20 * r_scale,
            fill=skin,
            outline="",
        )

        # Back hair for long styles
        if style in ("wavy_long", "bun"):
            if style == "bun":
                canvas.create_oval(
                    cx - 14 * r_scale,
                    cy - 28 * r_scale,
                    cx + 14 * r_scale,
                    cy - 12 * r_scale,
                    fill=hair,
                    outline="",
                )
            else:
                canvas.create_oval(
                    cx - 21 * r_scale,
                    cy - 14 * r_scale,
                    cx + 21 * r_scale,
                    cy + 21 * r_scale,
                    fill=hair,
                    outline="",
                )

        # Head / Face oval
        canvas.create_oval(
            cx - 13 * r_scale,
            cy - 16 * r_scale,
            cx + 13 * r_scale,
            cy + 14 * r_scale,
            fill=skin,
            outline="",
        )

        # Beard if applicable
        if has_beard:
            canvas.create_arc(
                cx - 12 * r_scale,
                cy,
                cx + 12 * r_scale,
                cy + 18 * r_scale,
                start=180,
                extent=180,
                fill=hair,
                outline="",
            )

        # Eyes
        canvas.create_oval(
            cx - 8 * r_scale,
            cy - 3 * r_scale,
            cx - 4 * r_scale,
            cy + 1 * r_scale,
            fill="#1e293b",
            outline="",
        )
        canvas.create_oval(
            cx + 4 * r_scale,
            cy - 3 * r_scale,
            cx + 8 * r_scale,
            cy + 1 * r_scale,
            fill="#1e293b",
            outline="",
        )

        # Hair front
        if style == "wavy":
            canvas.create_oval(
                cx - 15 * r_scale,
                cy - 23 * r_scale,
                cx + 15 * r_scale,
                cy - 7 * r_scale,
                fill=hair,
                outline="",
            )
            canvas.create_arc(
                cx - 16 * r_scale,
                cy - 20 * r_scale,
                cx + 5 * r_scale,
                cy - 2 * r_scale,
                start=30,
                extent=120,
                fill=hair,
                outline="",
            )
            canvas.create_arc(
                cx - 5 * r_scale,
                cy - 20 * r_scale,
                cx + 16 * r_scale,
                cy - 2 * r_scale,
                start=30,
                extent=120,
                fill=hair,
                outline="",
            )
        elif style == "wavy_long":
            canvas.create_oval(
                cx - 16 * r_scale,
                cy - 23 * r_scale,
                cx + 16 * r_scale,
                cy - 7 * r_scale,
                fill=hair,
                outline="",
            )
            canvas.create_polygon(
                cx - 14 * r_scale,
                cy - 10 * r_scale,
                cx - 19 * r_scale,
                cy + 12 * r_scale,
                cx - 12 * r_scale,
                cy + 19 * r_scale,
                cx - 10 * r_scale,
                cy + 5 * r_scale,
                fill=hair,
                smooth=True,
            )
            canvas.create_polygon(
                cx + 14 * r_scale,
                cy - 10 * r_scale,
                cx + 19 * r_scale,
                cy + 12 * r_scale,
                cx + 12 * r_scale,
                cy + 19 * r_scale,
                cx + 10 * r_scale,
                cy + 5 * r_scale,
                fill=hair,
                smooth=True,
            )
        elif style == "bob":
            canvas.create_oval(
                cx - 15 * r_scale,
                cy - 22 * r_scale,
                cx + 15 * r_scale,
                cy - 5 * r_scale,
                fill=hair,
                outline="",
            )
            canvas.create_arc(
                cx - 16 * r_scale,
                cy - 14 * r_scale,
                cx - 7 * r_scale,
                cy + 14 * r_scale,
                start=90,
                extent=180,
                fill=hair,
                outline="",
            )
            canvas.create_arc(
                cx + 7 * r_scale,
                cy - 14 * r_scale,
                cx + 16 * r_scale,
                cy + 14 * r_scale,
                start=270,
                extent=180,
                fill=hair,
                outline="",
            )
        else:
            canvas.create_oval(
                cx - 14 * r_scale,
                cy - 22 * r_scale,
                cx + 14 * r_scale,
                cy - 7 * r_scale,
                fill=hair,
                outline="",
            )

        # Glasses
        if has_glasses:
            canvas.create_oval(
                cx - 10 * r_scale,
                cy - 5 * r_scale,
                cx - 3 * r_scale,
                cy + 3 * r_scale,
                outline="#94a3b8",
                width=1,
            )
            canvas.create_oval(
                cx + 3 * r_scale,
                cy - 5 * r_scale,
                cx + 10 * r_scale,
                cy + 3 * r_scale,
                outline="#94a3b8",
                width=1,
            )
            canvas.create_line(
                cx - 3 * r_scale,
                cy - 2 * r_scale,
                cx + 3 * r_scale,
                cy - 2 * r_scale,
                fill="#94a3b8",
                width=1,
            )

    def _refresh_ui(self) -> None:
        """Update widget displays to reflect current PublicState and UI selections."""
        if self.root is None:
            return

        if hasattr(self, "_board_status"):
            self._board_status.config(text=self.status_message)
            n = self.controller.grid_size
            self._meta_stats_lbl.config(text=f"{n} × {n}  ·  {len(self.controller.public_state.revealed_cells)}/{n*n} revealed")
            title = Path(self.puzzle_source_path).stem.replace("_", " ").title() if self.puzzle_source_path else "A little mystery"
            self._puzzle_title_lbl.config(text=title)

        # 1. Update Notification Banner
        if self._status_label is not None and self._status_icon_label is not None:
            headline = self.status_message
            if "NOT_PROVABLE" in headline:
                headline = "Not provable yet"
            elif "CONTRADICTED" in headline:
                headline = "Contradiction detected"
            elif "SOLVED" in headline:
                headline = "Puzzle Solved!"
            elif "ACCEPTED" in headline:
                headline = "Verdict Accepted"
            elif "INCONSISTENT" in headline:
                headline = "Knowledge Base Inconsistent"
            elif "STALLED" in headline:
                headline = "Solver Frontier Stalled"
            elif "Inspecting Clue" in headline:
                headline = f"Clue {self.selected_clue_id}"

            self._status_label.config(text=headline)
            if self._status_sub_label is not None:
                self._status_sub_label.config(text=self.status_subtitle)

            if self.last_rejection_reason == RejectionReason.NOT_PROVABLE:
                bg = "#251430"
                border = "#a855f7"
                icon = "ⓘ"
            elif self.last_rejection_reason == RejectionReason.CONTRADICTED:
                bg = "#2e1017"
                border = "#ef4444"
                icon = "⚠"
            elif self.controller.is_solved:
                bg = "#0f2820"
                border = "#10b981"
                icon = "★"
            elif self.last_hint and self.last_hint.has_forced_cell:
                bg = "#221336"
                border = "#c084fc"
                icon = "💡"
            else:
                bg = THEME["purple_bg"]
                border = THEME["border_hint"]
                icon = "ⓘ"

            self._banner_frame.config(bg=bg, highlightbackground=border)
            self._status_icon_label.config(bg=bg, text=icon)
            self._status_label.config(bg=bg)
            if self._status_sub_label:
                self._status_sub_label.config(bg=bg)

        # 2. Update Inspector Card (Selected Character)
        if self.selected_cell is not None:
            card = self.controller.public_state.cards.get(self.selected_cell)
            if card:
                self._insp_char_title.config(text=f"{self.selected_cell} — {card.character.name}")
                p_icon = get_profession_icon(card.character.profession)
                self._insp_char_prof.config(text=f"{p_icon} {card.character.profession}")

                if card.is_revealed and card.status:
                    if card.status == Status.CRIMINAL:
                        self._insp_char_badge.config(
                            text="🎭 CRIMINAL",
                            bg=THEME["badge_criminal_bg"],
                            fg=THEME["badge_criminal_fg"],
                        )
                    else:
                        self._insp_char_badge.config(
                            text="✓ INNOCENT",
                            bg=THEME["badge_innocent_bg"],
                            fg=THEME["badge_innocent_fg"],
                        )
                else:
                    self._insp_char_badge.config(
                        text="? UNKNOWN",
                        bg=THEME["badge_unknown_bg"],
                        fg=THEME["badge_unknown_fg"],
                    )
        else:
            self._insp_char_title.config(text="None selected")
            self._insp_char_prof.config(text="Click a card on the grid")
            self._insp_char_badge.config(
                text="NO CARD",
                bg=THEME["badge_hidden_bg"],
                fg=THEME["badge_hidden_fg"],
            )

        self._redraw_inspector_avatar()

        # 3. Update Current Clue Card
        rev_clues = list(self.controller.public_state.revealed_clues)
        if rev_clues:
            if self.current_clue_index >= len(rev_clues):
                self.current_clue_index = max(0, len(rev_clues) - 1)
            c = rev_clues[self.current_clue_index]
            self._clue_page_lbl.config(text=f"{self.current_clue_index + 1} / {len(rev_clues)}")
            prose = format_clue_text(c, self.controller.public_state)

            ref_cells = get_clue_highlight_cells(c, self.controller.grid_size)
            if ref_cells:
                refs_text = ", ".join(str(cell) for cell in ref_cells)
                self._clue_refs_lbl.config(text=f"👁  Referenced cells: {refs_text}")
            else:
                self._clue_refs_lbl.config(text="👁  Referenced cells: None")
        else:
            self._clue_page_lbl.config(text="0 / 0")
            prose = "No revealed clues available yet."
            self._clue_refs_lbl.config(text="👁  Referenced cells: None")

        if self._clue_prose_lbl.get("1.0", "end-1c") != prose:
            self._clue_prose_lbl.config(state=tk.NORMAL)
            self._clue_prose_lbl.delete("1.0", tk.END)
            self._clue_prose_lbl.insert("1.0", prose)
            self._clue_prose_lbl.config(state=tk.DISABLED)

        # Sync clues in hidden listbox for test contract
        if self._clues_listbox is not None:
            self._clues_listbox.delete(0, tk.END)
            for clue in rev_clues:
                self._clues_listbox.insert(tk.END, f"{clue.clue_id}: {format_clue_text(clue, self.controller.public_state)}")

        # 4. Update Grid Cards
        for cell, card_frame in self._cell_buttons.items():
            view_data = self.get_cell_view_data(cell)
            w = card_frame._widgets  # type: ignore[attr-defined]

            # Coordinate
            w["coord"].config(text=str(cell))

            is_crim = (view_data.status == Status.CRIMINAL)
            is_revealed = view_data.is_revealed
            is_selected = view_data.is_selected

            # Determine colors & labels based on state
            if is_revealed:
                if is_crim:
                    card_bg = THEME["bg_card_criminal"]
                    border_color = THEME["border_criminal"]
                    badge_bg = THEME["badge_criminal_bg"]
                    badge_fg = THEME["badge_criminal_fg"]
                    badge_text = "CRIMINAL"
                else:
                    card_bg = THEME["bg_card_innocent"]
                    border_color = THEME["border_innocent"]
                    badge_bg = THEME["badge_innocent_bg"]
                    badge_fg = THEME["badge_innocent_fg"]
                    badge_text = "INNOCENT"

                p_icon = get_profession_icon(view_data.character.profession)
                name_text = view_data.character.name
                prof_text = view_data.character.profession
                prof_fg = THEME["text_muted"]
                show_badge = True
            elif is_selected:
                card_bg = THEME["bg_card_selected"]
                border_color = THEME["border_selected"]
                badge_bg = THEME["badge_unknown_bg"]
                badge_fg = THEME["badge_unknown_fg"]
                badge_text = "? UNKNOWN"

                p_icon = get_profession_icon(view_data.character.profession)
                name_text = view_data.character.name
                prof_text = view_data.character.profession
                prof_fg = THEME["text_muted"]
                show_badge = True
            else:
                card_bg = THEME["bg_card"]
                border_color = THEME["border_card"]
                badge_bg = THEME["badge_hidden_bg"]
                badge_fg = THEME["badge_hidden_fg"]
                badge_text = "HIDDEN"

                name_text = view_data.character.name
                prof_text = view_data.character.profession
                prof_fg = THEME["text_muted"]
                show_badge = False

            # Priority Borders: Selected > Hinted > Highlighted > Default
            if cell in self.hint_clue_cells:
                card_bg = THEME["purple_bg"]
                border_color = THEME["border_hint"]
            elif view_data.is_selected:
                card_bg = THEME["bg_card_selected"]
                border_color = THEME["border_selected"]
            elif view_data.is_hinted:
                border_color = THEME["border_hint"]
            elif view_data.is_highlighted:
                card_bg = THEME["bg_card_highlight"]
                border_color = THEME["border_highlight"]

            # Apply styling to container frame
            card_frame.config(
                bg=card_bg, highlightbackground=border_color,
                highlightthickness=4 if cell in self.hint_clue_cells else 2,
            )

            # Sync child widget backgrounds
            w["top_row"].config(bg=card_bg)
            w["coord"].config(bg=THEME["btn_bg"])
            w["canvas"].config(bg=card_bg)
            w["name"].config(text=name_text, bg=card_bg)
            w["prof"].config(text=prof_text, bg=card_bg, fg=prof_fg)
            w["badge"].config(text=badge_text, bg=badge_bg, fg=badge_fg)
            w["clue"].config(bg=card_bg)
            w["identity"].config(bg=card_bg)
            w["compact_name"].config(text=name_text, bg=card_bg)
            w["compact_prof"].config(text=view_data.character.profession, bg=card_bg)
            clue_text = view_data.clue_text if is_revealed else ""
            if w["clue"].get("1.0", "end-1c") != clue_text:
                w["clue"].config(state=tk.NORMAL)
                w["clue"].delete("1.0", tk.END)
                w["clue"].insert("1.0", clue_text, "center")
                w["clue"].config(state=tk.DISABLED)
                # Force Tk to measure wrapped lines before the first scroll.
                w["clue"].count("1.0", tk.END, "displaylines")

            if is_revealed:
                w["canvas"].pack_forget()
                w["name"].pack_forget()
                w["prof"].pack_forget()
                w["identity"].pack(side=tk.RIGHT)
                w["badge"].pack(pady=(4, 0))
                w["clue"].pack(fill=tk.BOTH, expand=True, pady=(6, 2))
            else:
                w["identity"].pack_forget()
                w["canvas"].config(height=36)
                w["clue"].pack_forget()
                w["canvas"].pack(fill=tk.X, pady=(2, 2), after=w["top_row"])
                w["name"].pack(fill=tk.X, after=w["canvas"])
                w["prof"].pack(fill=tk.X, after=w["name"])

            if show_badge:
                w["badge"].pack(pady=(4, 0))
            else:
                w["badge"].pack_forget()

            # Draw procedural avatar portrait
            self._draw_avatar(
                w["canvas"],
                is_revealed=is_revealed,
                is_criminal=is_crim,
                is_selected=is_selected,
                name=view_data.character.name,
                profession=view_data.character.profession,
            )

        # 5. Update Deduction Log Text
        if self._log_text is not None:
            self._log_text.config(state=tk.NORMAL)
            self._log_text.delete("1.0", tk.END)

            self._log_text.tag_configure("icon_action", foreground="#60a5fa", font=("Helvetica", 9, "bold"))
            self._log_text.tag_configure("icon_deduction", foreground="#34d399", font=("Helvetica", 9, "bold"))
            self._log_text.tag_configure("icon_sat", foreground="#c084fc", font=("Helvetica", 9, "bold"))
            self._log_text.tag_configure("icon_info", foreground="#38bdf8", font=("Helvetica", 9, "bold"))
            self._log_text.tag_configure("icon_error", foreground="#f87171", font=("Helvetica", 9, "bold"))
            self._log_text.tag_configure("title", foreground="#f8fafc", font=("Helvetica", 9, "bold"))
            self._log_text.tag_configure("detail", foreground="#94a3b8", font=("Helvetica", 8))
            self._log_text.tag_configure("ts", foreground="#64748b", font=("Consolas", 8))

            for cat, title, detail, ts in self._structured_logs:
                if self.log_filter != "All":
                    if self.log_filter == "SAT" and cat != "sat":
                        continue
                    if self.log_filter == "Deductions" and cat != "deduction":
                        continue
                    if self.log_filter == "Actions" and cat != "action":
                        continue

                icon = "▶"
                icon_tag = "icon_action"
                if cat == "deduction":
                    icon = "✓"
                    icon_tag = "icon_deduction"
                elif cat == "sat":
                    icon = "⚗"
                    icon_tag = "icon_sat"
                elif cat == "info":
                    icon = "ⓘ"
                    icon_tag = "icon_info"
                elif cat == "error":
                    icon = "⚠"
                    icon_tag = "icon_error"

                self._log_text.insert(tk.END, f"{icon}  ", icon_tag)
                self._log_text.insert(tk.END, f"{title}: ", "title")
                self._log_text.insert(tk.END, f"{detail:<32} ", "detail")
                self._log_text.insert(tk.END, f" {ts}\n", "ts")

            self._log_text.see(tk.END)
            self._log_text.config(state=tk.DISABLED)

    def _on_load_button(self) -> None:
        """Handle Load Puzzle button click with a file dialog."""
        assert self.root is not None
        puzzles_dir = Path(__file__).resolve().parents[3] / "puzzles"
        initial_dir = str(puzzles_dir) if puzzles_dir.is_dir() else None

        fpath = filedialog.askopenfilename(
            parent=self.root,
            title="Load Griductive Puzzle",
            initialdir=initial_dir,
            filetypes=[("JSON Puzzles", "*.json"), ("All Files", "*.*")],
        )
        if fpath:
            self.load_puzzle(fpath)


# =============================================================================
# Application Entry Point
# =============================================================================


def launch_gui(
    puzzle_path: str | Path | None = None,
    puzzle: Any | None = None,
) -> GriductiveApp:
    """Launch the interactive desktop Tkinter GUI application."""
    if puzzle is None:
        if puzzle_path is None:
            default_p = Path(__file__).resolve().parents[3] / "puzzles" / "puzzle_3x3_progressive.json"
            if default_p.is_file():
                puzzle_path = default_p
            else:
                alt_p = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "puzzle_3x3_valid.json"
                puzzle_path = alt_p
        puzzle = load_puzzle_from_json(puzzle_path)

    controller = GameController(puzzle)
    root = tk.Tk()
    app = GriductiveApp(controller=controller, root=root, puzzle_source_path=puzzle_path)
    return app
