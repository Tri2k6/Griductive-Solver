"""Coordinate Griductive's public board and launch the Tkinter window."""

from __future__ import annotations

from pathlib import Path
import sys
import time
import tkinter as tk
from tkinter import messagebox
from typing import Any

from griductive.domain.model import CellId, Clue
from griductive.domain.regions import get_clue_highlight_cells
from griductive.game.controller import AutoSolveReport, CallResult, GameController, Hint, RejectionReason
from griductive.game.io import load_puzzle_from_json
from griductive.ui import formatting
from griductive.ui.actions import _SolverActions
from griductive.ui.board import _BoardView
from griductive.ui.dialogs import _GameDialogs
from griductive.ui.formatting import (
    CellViewData,
    PROFESSION_ICONS as PROFESSION_ICONS,
    format_clue_text as format_clue_text,
    format_region_text as format_region_text,
    get_profession_icon as get_profession_icon,
)
from griductive.ui.panels import _SidePanels
from griductive.ui.theme import (
    AUTO_SOLVE_LABEL as AUTO_SOLVE_LABEL,
    CHECK_BOARD_LABEL as CHECK_BOARD_LABEL,
    LOGS_LABEL as LOGS_LABEL,
    READING_FONT as READING_FONT,
    THEME as THEME,
)
from griductive.ui.widgets import (
    CharacterCard as CharacterCard,
    GameButton as GameButton,
    RoundedCard as RoundedCard,
)
from griductive.ui.window import _WindowLayout


class GriductiveApp(_WindowLayout, _BoardView, _SidePanels, _GameDialogs, _SolverActions):
    """Own the UI state for both Tkinter and headless use.

    The view renders public state only. Gameplay goes through GameController.
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
        self.reduced_motion = False
        self.puzzles_dir = Path(__file__).resolve().parents[3] / "puzzles"
        self.current_clue_index: int = 0
        self.log_filter: str = "All"
        self._start_time: float = time.time()

        # Feedback & notifications
        self.status_message: str = "Select a card to make your first call."
        self.status_subtitle: str = "Use the revealed clues to decide each verdict."
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

    def load_puzzle(self, puzzle_or_path: str | Path | Any) -> None:
        """Load a new puzzle from file path or Puzzle object."""
        self._dismiss_dialog()
        self.stop_auto_solve()
        try:
            if isinstance(puzzle_or_path, (str, Path)):
                puzzle = load_puzzle_from_json(puzzle_or_path, allow_public_conflict=True)
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
            msg = "Puzzle loaded. Select a card to begin."
            self.status_message = msg
            self.status_subtitle = ""
            self.trace_log = [msg]
            self._structured_logs = [("info", "Loaded puzzle", f"{self.controller.grid_size}×{self.controller.grid_size}", "T+00:00")]

            if self.root is not None:
                self._rebuild_board()
                self._refresh_ui()
        except Exception as e:
            err_msg = f"Failed to load puzzle: {e}"
            self.status_message = "Could not open the puzzle."
            self.status_subtitle = "Choose a valid puzzle JSON file."
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
        msg = "Puzzle restarted."
        self.status_message = msg
        self.status_subtitle = "The board shows the starting clues again."
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
        self.hinted_cell = None
        self.last_hint = None
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
        self.status_message = f"Clue on {found_clue.owner}"
        self.status_subtitle = formatting.format_clue_text(found_clue, self.controller.public_state)

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
        self.hinted_cell = None
        self.last_hint = None
        if self.root is not None:
            self._refresh_ui()

    def get_cell_view_data(self, cell: CellId) -> CellViewData:
        """Compute the view data dictionary for a given cell."""
        state = self.controller.public_state
        card = state.cards[cell]
        is_revealed = card.is_revealed
        status = card.status if is_revealed else None

        if is_revealed:
            status_label = status.value if status else "REVEALED"
            clue = card.clue
            clue_text = formatting.format_clue_text(clue, state) if clue else ""
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
                    "text": formatting.format_clue_text(clue, state),
                    "is_selected": (clue.clue_id == self.selected_clue_id),
                }
            )
        return res

    def _refresh_ui(self) -> None:
        """Update the window from the public board and user selections."""
        if self.root is None:
            return

        self._refresh_window_status()
        self._refresh_banner()
        self._refresh_inspector()
        self._refresh_clues()
        self._refresh_cards()
        self._refresh_logs()



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
        puzzle = load_puzzle_from_json(puzzle_path, allow_public_conflict=True)

    controller = GameController(puzzle)
    if sys.platform == "win32":
        # This script has no application manifest. Opt out of Windows bitmap
        # upscaling before creating the first native Tk window.
        from ctypes import windll

        windll.user32.SetProcessDPIAware()
    root = tk.Tk()
    app = GriductiveApp(controller=controller, root=root, puzzle_source_path=puzzle_path)
    return app
