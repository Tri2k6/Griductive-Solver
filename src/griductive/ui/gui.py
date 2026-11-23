"""Playable GUI and presentation layer for Griductive Solver.

Architecture:
- The GUI has NO access to GameEngine, hidden solutions, or unrevealed clues.
- All actions (Call, Hint, Step, Auto Solve, Restart) are routed strictly through GameController.
- Render state is computed exclusively from PublicState and user UI selections.
- Operates both with Tkinter widgets (desktop/X11) and in headless presentation mode (unit/integration tests).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path
import re
import sys
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
from griductive.solver.cnf import PrimaryVarMap
from griductive.solver.dpll import DpllMetrics
from griductive.solver.logic import SatQueryRecord


# =============================================================================
# Visual Theme Configuration (Warm detective card theme)
# =============================================================================

THEME = {
    "bg_root": "#191d23", "bg_header": "#191d23", "bg_card": "#252b34",
    "bg_card_innocent": "#253b35", "bg_card_criminal": "#412e35",
    "bg_card_selected": "#354251", "bg_card_highlight": "#443a2c",
    "border_subtle": "#514940", "border_card": "#62646a", "border_bright": "#8e8172",
    "border_innocent": "#77c79a", "border_criminal": "#f38578",
    "border_selected": "#ffd697", "border_highlight": "#dfb65f", "border_hint": "#9b82fa",
    "purple_accent": "#e8b46d", "purple_bg": "#3b3247", "gold_accent": "#dfb65f",
    "text_primary": "#f6efe4", "text_secondary": "#ddd3c4", "text_muted": "#b9b5b2",
    "btn_bg": "#2d3540", "btn_border": "#4a5360",
    "crim_btn_bg": "#542c28", "crim_btn_border": "#f38578", "crim_btn_hover": "#6a3831",
    "inn_btn_bg": "#303e31", "inn_btn_border": "#77c79a", "inn_btn_hover": "#405641",
    "badge_innocent_bg": "#253b35", "badge_innocent_fg": "#9bd7ac",
    "badge_criminal_bg": "#412e35", "badge_criminal_fg": "#ffab9b",
    "badge_unknown_bg": "#354251", "badge_unknown_fg": "#ffd697",
    "badge_hidden_bg": "#252b34", "badge_hidden_fg": "#b9b5b2",
}

READING_FONT = "Atkinson Hyperlegible"
AUTO_SOLVE_LABEL = "Auto Solve"
CHECK_BOARD_LABEL = "Check Board"
LOGS_LABEL = "Logs"


@cache
def _load_reading_fonts() -> None:
    """Make the bundled typefaces available to this Windows process only."""
    if sys.platform != "win32":
        return

    from ctypes import windll

    directory = Path(__file__).resolve().parent / "assets" / "atkinson-hyperlegible"
    private_font = 0x10  # FR_PRIVATE
    for weight in ("Regular", "Bold"):
        path = directory / f"AtkinsonHyperlegible-{weight}.ttf"
        if path.is_file():
            windll.gdi32.AddFontResourceExW(str(path), private_font, None)


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
        self._paint_outline(2, 2, self._stroke, self._stroke_width)

    def _paint_outline(self, inset: int, top: int, color: str, width: int) -> None:
        right, bottom = self.winfo_width() - inset, self.winfo_height() - inset
        if right <= inset or bottom <= top:
            return
        radius = min(14, (right - inset) // 2, (bottom - top) // 2)
        points = (
            inset + radius, top, right - radius, top, right, top, right, top + radius,
            right, bottom - radius, right, bottom, right - radius, bottom,
            inset + radius, bottom, inset, bottom, inset, bottom - radius,
            inset, top + radius, inset, top, inset + radius, top,
        )
        self._surface.delete("all")
        self._surface.create_polygon(points, smooth=True, splinesteps=24,
                                     fill=self._fill, outline=color, width=width)


class CharacterCard(RoundedCard):
    """Animate the border inside the fixed grid slot."""

    def __init__(self, master: tk.Misc, *, scale: Callable[[float], int],
                 reduced_motion: Callable[[], bool], **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._scale = scale
        self._reduced_motion = reduced_motion
        self._pointer_inside = False
        self._dimmed = False
        self._hover_amount = 0.0
        self._hover_timer: str | None = None
        self.bind("<Destroy>", self._cancel_hover)

    def bind_hover(self) -> None:
        """Treat the portrait, clue text and labels as one pointer target."""
        pending = [self]
        while pending:
            widget = pending.pop()
            widget.bind("<Enter>", self._enter_card, add="+")
            widget.bind("<Leave>", self._leave_card, add="+")
            pending.extend(widget.winfo_children())

    def set_dimmed(self, dimmed: bool) -> None:
        """Keep muted cards in the background during Hint spotlight."""
        if self._dimmed != dimmed:
            self._dimmed = dimmed
            self._animate_hover()

    def _enter_card(self, event) -> None:
        if not self._pointer_inside:
            self._pointer_inside = True
            self._animate_hover()

    def _leave_card(self, event) -> None:
        x = event.x_root - self.winfo_rootx()
        y = event.y_root - self.winfo_rooty()
        if 0 <= x < self.winfo_width() and 0 <= y < self.winfo_height():
            return
        if self._pointer_inside:
            self._pointer_inside = False
            self._animate_hover()

    def _cancel_hover(self, event=None) -> None:
        if self._hover_timer is not None:
            self.after_cancel(self._hover_timer)
            self._hover_timer = None

    def _animate_hover(self) -> None:
        self._cancel_hover()
        target = float(self._pointer_inside and not self._dimmed)
        start = self._hover_amount
        if self._dimmed or self._reduced_motion() or start == target:
            self._hover_amount = target
            self._paint()
            return

        started = time.perf_counter()

        def tick() -> None:
            self._hover_timer = None
            progress = min(1.0, (time.perf_counter() - started) / 0.15)
            self._hover_amount = start + (target - start) * (1 - (1 - progress) ** 3)
            self._paint()
            if progress < 1:
                self._hover_timer = self.after(15, tick)

        tick()

    def _paint(self, event=None) -> None:
        amount = 0.0 if self._dimmed else self._hover_amount
        motion = 0.0 if self._reduced_motion() else amount
        px = self._scale
        inset = max(2, px(3) - round(px(2) * motion))
        top = max(2, inset - round(px(1) * motion))
        base = self.winfo_rgb(self._stroke)
        light = self.winfo_rgb(THEME["text_primary"])
        color = "#" + "".join(
            f"{round((channel + (bright - channel) * amount * 0.72) / 257):02x}"
            for channel, bright in zip(base, light)
        )
        self._paint_outline(inset, top, color, self._stroke_width + round(px(1) * amount))


class GameButton(tk.Frame):
    """Animate the face inside a fixed target, using a native button for input."""

    ICONS = {
        "Hint": "✧", "Reveal": "◎", "Clear": "×", LOGS_LABEL: "≡",
        AUTO_SOLVE_LABEL: "▷", "Pause": "Ⅱ", CHECK_BOARD_LABEL: "◇",
        "Puzzles": "▤", "Restart": "↻", "Settings": "⚙",
        "Innocent": "✓", "Criminal": "!", "Cancel": "×", "Close": "×",
    }

    def __init__(self, parent, label, command, *, colors, scale, reduced_motion):
        background = parent._fill if isinstance(parent, RoundedCard) else parent.cget("bg")
        super().__init__(parent, bg=background, cursor="hand2", takefocus=True)
        self._scale = scale
        self._reduced_motion = reduced_motion
        self._base, foreground, self._hover, self._edge = colors
        self._timer = None
        self._amount = self._from = self._target = 0.0
        self._pressed = False
        self._hovered = False
        self._label = label
        self._art = tk.Canvas(self, bg=self.cget("bg"), bd=0, highlightthickness=0)
        self._art.place(relwidth=1, relheight=1)
        self._face = self._art.create_polygon(0, 0, 1, 0, 1, 1, smooth=True)
        self._button = tk.Button(
            self, text=label, command=command,
            font=("Trebuchet MS", 10, "bold"), fg=foreground, bg=self._base,
            activeforeground=foreground, activebackground=self._hover, relief=tk.FLAT,
            overrelief=tk.FLAT, bd=0, highlightthickness=0, padx=0, pady=0,
            takefocus=False, cursor="hand2",
        )
        self._icon = self._art.create_text(0, 0, font=("Segoe UI Symbol", 9), fill=foreground)
        self._button.place(x=0, y=0)
        # Reserve room for both resting and hovered frames, including the border.
        if label == "Hint":
            self._button.config(text="Reveal")
        label_width = self._button.winfo_reqwidth()
        self._button.config(text=label)
        super().config(width=label_width + scale(34),
                       height=self._button.winfo_reqheight() + scale(20))
        self.bind("<Configure>", self._paint)
        for target in (self, self._art, self._button):
            target.bind("<Enter>", self._enter)
            target.bind("<Leave>", self._leave)
        self.bind("<Destroy>", self._dispose)
        self.bind("<FocusIn>", self._paint)
        self.bind("<FocusOut>", self._paint)
        for key in ("Return", "space"):
            self.bind(f"<KeyRelease-{key}>", self._invoke_key)
        self._button.bind("<ButtonPress-1>", self._press)
        self._button.bind("<ButtonRelease-1>", self._activate_border)
        self._art.bind("<ButtonPress-1>", self._press)
        self._art.bind("<ButtonRelease-1>", self._activate_border)

    def _invoke_key(self, event):
        self._button.invoke()
        return "break"

    def config(self, cnf=None, **kwargs):
        if "text" in kwargs:
            self._label = kwargs.pop("text")
            self._button.config(text=self._label)
            self._paint()
        return super().config(cnf, **kwargs)

    configure = config

    def cget(self, key):
        return self._label if key == "text" else super().cget(key)

    def _enter(self, event):
        if self._hovered:
            return
        self._hovered = True
        self._ease_to(1.0)

    def _leave(self, event):
        # The pointer may have moved from the border to the native child.
        x, y = event.x_root, event.y_root
        if (0 <= x - self.winfo_rootx() < self.winfo_width()
                and 0 <= y - self.winfo_rooty() < self.winfo_height()):
            return
        if not self._hovered:
            return
        self._hovered = False
        self._pressed = False
        self._ease_to(0.0)

    def _press(self, event):
        self._pressed = True
        self.focus_set()
        self._paint()
        return "break"

    def _release(self, event):
        self._pressed = False
        self._paint()

    def _activate_border(self, event):
        armed = self._pressed
        self._release(event)
        x = event.x_root - self.winfo_rootx()
        y = event.y_root - self.winfo_rooty()
        if armed and 0 <= x < self.winfo_width() and 0 <= y < self.winfo_height():
            self._button.invoke()
        return "break"

    def _dispose(self, event):
        if self._timer is not None:
            self.after_cancel(self._timer)
            self._timer = None

    def _ease_to(self, target):
        if self._timer is not None:
            self.after_cancel(self._timer)
            self._timer = None
        self._target = target
        self._from = self._amount
        if self._reduced_motion():
            self._amount = target
            self._paint()
            return
        self._started = time.perf_counter()
        self._tick()

    def _tick(self):
        self._timer = None
        progress = min(1.0, (time.perf_counter() - self._started) / 0.15)
        eased = 1 - (1 - progress) ** 3
        self._amount = self._from + (self._target - self._from) * eased
        self._paint()
        if progress < 1:
            self._timer = self.after(15, self._tick)

    def _paint(self, event=None):
        width, height = self.winfo_width(), self.winfo_height()
        if width < 10 or height < 10:
            return
        px = self._scale
        amount = 0.0 if self._reduced_motion() else self._amount
        inset = px(5) - round(px(3) * amount)
        top = inset - round(px(2) * amount) + px(1 if self._pressed else 0)
        top = max(2, top)
        right, bottom = width - inset, height - inset - round(px(1) * amount)
        radius = min(px(8), (bottom - top) // 2)
        fill = self._hover if self._hovered or self._pressed else self._base
        edge = THEME["border_selected"] if self.focus_get() == self else (
            THEME["text_secondary"] if self._hovered else self._edge
        )
        points = (
            inset + radius, top, right - radius, top, right, top, right, top + radius,
            right, bottom - radius, right, bottom, right - radius, bottom,
            inset + radius, bottom, inset, bottom, inset, bottom - radius,
            inset, top + radius, inset, top, inset + radius, top,
        )
        self._art.coords(self._face, *points)
        self._art.itemconfig(self._face, fill=fill, outline=edge, width=px(2 if self._hovered else 1))
        self._art.itemconfig(self._icon, text=self.ICONS.get(self._label, ""))
        icon_width = px(12) if self._label in self.ICONS else 0
        gap = px(6) if icon_width else 0
        text_width = self._button.winfo_reqwidth()
        left = (width - text_width - icon_width - gap) // 2
        center_y = (top + bottom) // 2
        self._art.coords(self._icon, left + icon_width / 2, center_y)
        self._button.config(bg=fill)
        text_height = self._button.winfo_reqheight()
        self._button.place(x=left + icon_width + gap, y=center_y - text_height // 2,
                           width=text_width, height=text_height)


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

    # =========================================================================
    # User Actions (All routed through GameController)
    # =========================================================================

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
        self.hinted_cell = None
        self.last_hint = None
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
        self.clear_highlights()
        if self.selected_cell is None:
            self.last_rejection_reason = RejectionReason.INVALID_CELL
            self.status_message = "Select a card first."
            self.status_subtitle = "Choose a face-down card to make a call."
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
        if res.classification is not None:
            for query in res.classification.queries:
                self._log_sat_query(query)
        if res.rejection_reason == RejectionReason.INCONSISTENT:
            self._add_log("sat", "Public Clues", "UNSAT")

        if res.accepted:
            self.last_rejection_reason = None
            verdict = proposed_status.value.lower()
            self.status_message = f"{target} is {verdict}. New clue revealed."
            clue = res.revealed_clue
            self.status_subtitle = format_clue_text(clue, self.controller.public_state) if clue else ""
            detail = f"{verdict.title()}, clue {clue.clue_id}" if clue else verdict.title()
            self._add_log("action", f"Revealed {target}", detail)
            if self.controller.is_solved:
                self.status_message = "Puzzle solved."
                self._add_log("deduction", "Puzzle Solved", "Every card was revealed without guessing.")
        else:
            reason = res.rejection_reason
            self.last_rejection_reason = reason
            if reason == RejectionReason.NOT_PROVABLE:
                self.status_message = "Not enough evidence yet."
                self.status_subtitle = f"Both verdicts are still possible for {target}. Read another clue or use Hint."
            elif reason == RejectionReason.CONTRADICTED:
                self.status_message = "The clues prove the opposite verdict."
                self.status_subtitle = f"Review the clues that refer to {target}."
            elif reason == RejectionReason.INCONSISTENT:
                self.status_message = "The revealed clues conflict."
                self.status_subtitle = f"Use {CHECK_BOARD_LABEL} to inspect the public clues."
            else:
                self.status_message = "Verdict not accepted."
                self.status_subtitle = res.message or ""
            if reason is not None:
                self._add_log("info", reason.value, self.status_subtitle)

        if self.root is not None:
            self._refresh_ui()

        return res

    def _log_sat_query(self, query: SatQueryRecord) -> None:
        variables = PrimaryVarMap(self.controller.grid_size)
        assumptions = []
        for literal in query.assumptions:
            cell = variables.var_to_cell(abs(literal))
            assumptions.append(f"{cell} = {'Criminal' if literal > 0 else 'Innocent'}")
        self._add_log("sat", ", ".join(assumptions) or "Public Clues",
                      "SAT" if query.is_sat else "UNSAT")

    def check_board(self, claim: AutoSolveStatus | None = None) -> AutoSolveStatus | None:
        """Verify the player's board claim against public evidence only."""
        self.stop_auto_solve()
        self.clear_highlights()
        proof = self.controller.assess_board()
        self._log_sat_query(proof.base_query)
        for classification in proof.classifications.values():
            for query in classification.queries:
                self._log_sat_query(query)
        if not proof.base_consistent:
            status = AutoSolveStatus.INCONSISTENT
            detail = "No assignment satisfies the revealed clues and known statuses."
        elif proof.first_forced_cell is not None:
            status = None
            detail = "Select Hint to see the relevant clues."
        elif self.controller.is_solved:
            status = AutoSolveStatus.SOLVED
            detail = "All cards have been revealed and the public clues agree."
        else:
            status = AutoSolveStatus.STALLED
            detail = "The revealed clues agree, but no remaining verdict is forced."
        label = {
            AutoSolveStatus.INCONSISTENT: "The revealed clues conflict.",
            AutoSolveStatus.SOLVED: "Puzzle solved.",
            AutoSolveStatus.STALLED: "No provable move remains.",
        }.get(status, "A provable move remains.")
        prefix = "" if claim is None else ("Correct. " if claim == status else "Claim not supported. ")
        self.status_message = prefix + label
        self.status_subtitle = detail
        self._add_log("deduction", CHECK_BOARD_LABEL, f"{label} {detail}")
        if self.root is not None:
            self._refresh_ui()
        return status

    def _show_board_check(self) -> None:
        self.stop_auto_solve()
        panel = self._new_dialog(CHECK_BOARD_LABEL)
        self._dialog_text(panel, "What do the clues show?", heading=True)
        result = tk.StringVar(master=panel, value="")
        for label, claim in (("No Provable Move", AutoSolveStatus.STALLED),
                             ("Conflicting Clues", AutoSolveStatus.INCONSISTENT)):
            def verify(choice=claim):
                self.check_board(choice)
                result.set(f"{self.status_message}\n{self.status_subtitle}")

            ttk.Button(panel, text=label, command=verify).pack(fill=tk.X, pady=5)
        tk.Label(panel, textvariable=result, wraplength=390, justify=tk.CENTER,
                 font=(READING_FONT, 11),
                 bg=THEME["bg_card"], fg=THEME["text_primary"]).pack(fill=tk.X, pady=8)
        ttk.Button(panel, text="Close", command=self._dismiss_dialog).pack()
        self._present_dialog()

    def hint(self) -> Hint:
        """Start with public evidence, without selecting or flipping the target."""
        self.stop_auto_solve()
        self.clear_highlights()
        self.selected_cell = None
        hint = self.controller.hint()
        self.last_hint = hint
        if hint.classification is not None:
            for query in hint.classification.queries:
                self._log_sat_query(query)

        if not hint.base_consistent:
            self.status_message = "The revealed clues conflict."
            self._add_log("sat", "Public Clues", "UNSAT")
        elif hint.has_forced_cell:
            clues = self.controller.public_state.revealed_clues
            self.hint_clue_cells = frozenset(
                clue.owner for clue in clues if clue.clue_id in hint.relevant_clue_ids
            )
            evidence = ", ".join(str(cell) for cell in sorted(self.hint_clue_cells))
            self.status_message = (
                f"Read the evidence on {evidence}. Select Reveal for the next person."
                if evidence else "Select Reveal to see who you can identify next."
            )
            self._add_log("deduction", "Hint", f"Evidence on {evidence}" if evidence else "Next move is provable")
        else:
            self.status_message = "Puzzle solved." if self.controller.is_solved else "No provable move remains."
        self.status_subtitle = ""
        if self.root is not None:
            self._refresh_ui()
            if self.hint_clue_cells:
                self._scroll_to_hint(min(self.hint_clue_cells))
        return hint

    def _advance_hint(self) -> None:
        """Cycle from evidence to the target and then clear the spotlight."""
        if self.hinted_cell is not None:
            self.status_message = "Spotlight cleared."
            self.status_subtitle = "Continue investigating the revealed clues."
            self.selected_cell = None
            self.clear_highlights()
        elif self.last_hint and self.last_hint.has_forced_cell and self.hint_clue_cells:
            self._reveal_hint_target()
        else:
            hint = self.hint()
            if hint.has_forced_cell and not self.hint_clue_cells:
                self._reveal_hint_target()

    def _reveal_hint_target(self) -> None:
        hint = self.last_hint
        if hint is None or hint.cell is None:
            return
        self.hinted_cell = hint.cell
        person = self.controller.public_state.cards[hint.cell].character
        self.status_message = f"Next person: {person.name} ({hint.cell}). Select the card to make your call."
        self.status_subtitle = "Use the highlighted clues to decide the verdict."
        if self.root is not None:
            self._refresh_ui()
            self._scroll_to_hint(hint.cell)

    def _scroll_to_hint(self, cell: CellId) -> None:
        """Bring a highlighted card into the board viewport when needed."""
        viewport = getattr(self, "_board_viewport", None)
        card = self._cell_buttons.get(cell)
        if viewport is None or card is None:
            return
        viewport.update_idletasks()
        bounds = viewport.bbox("all")
        if bounds:
            for axis, start, length, view, span in (
                ("x", bounds[0] + card.winfo_x(), card.winfo_width(), viewport.canvasx(0), viewport.winfo_width()),
                ("y", bounds[1] + card.winfo_y(), card.winfo_height(), viewport.canvasy(0), viewport.winfo_height()),
            ):
                if start < view or start + length > view + span:
                    extent = bounds[2 if axis == "x" else 3]
                    getattr(viewport, f"{axis}view_moveto")(max(0, start - self._px(12)) / max(1, extent))

    def _is_dimmed(self, cell: CellId) -> bool:
        spotlight = self.hint_clue_cells or self.hinted_cell is not None
        return bool(spotlight and cell not in self.hint_clue_cells and cell != self.hinted_cell)

    @staticmethod
    def _dim_color(color: str) -> str:
        if len(color) == 7 and color.startswith("#"):
            backdrop = THEME["bg_root"]
            return "#" + "".join(
                f"{round(int(color[i:i+2], 16) * .38 + int(backdrop[i:i+2], 16) * .62):02x}"
                for i in (1, 3, 5)
            )
        return color

    def step(self) -> DeductionStep | None:
        """Execute a single deterministic deduction step."""
        self.stop_auto_solve()
        self.clear_highlights()
        step_res = self.controller.step()
        if step_res is not None:
            self._log_deduction_step(step_res)
            self.status_message = (
                f"Step {step_res.step_number} · {step_res.target_cell} is "
                f"{step_res.target_verdict.value.lower()}."
            )
            self.status_subtitle = format_clue_text(step_res.revealed_clue, self.controller.public_state)
            self.selected_cell = step_res.target_cell
            if self.controller.is_solved:
                self.status_message = "Puzzle solved."
                self.status_subtitle = "Every card was revealed without guessing."
                self._add_log("deduction", "Complete", "Puzzle solved successfully")
        else:
            if self.controller.is_solved:
                self.status_message = "The puzzle is already solved."
                self.status_subtitle = "All character cards have been exposed."
            else:
                terminal_report = self.controller.auto_solve()
                self.last_auto_solve_report = terminal_report
                if terminal_report.status == AutoSolveStatus.INCONSISTENT:
                    self.status_message = "The revealed clues conflict."
                    self.status_subtitle = "No assignment fits the revealed clues and known verdicts."
                else:
                    self.status_message = "No provable move remains."
                    self.status_subtitle = "The current clues leave more than one possibility."
            self._add_log("info", "Step Result", self.status_message)

        if self.root is not None:
            self._refresh_ui()

        return step_res

    def auto_solve(self, max_steps: int | None = None) -> AutoSolveReport:
        """Run the full deduction loop until solved, stalled, or inconsistent."""
        self.stop_auto_solve()
        self.clear_highlights()
        report = self.controller.auto_solve(max_steps=max_steps)
        self.last_auto_solve_report = report

        for step in report.steps:
            self._log_deduction_step(step)
        self._show_auto_solve_result(report)

        if self.root is not None:
            self._refresh_ui()

        return report

    def _log_deduction_step(self, step: DeductionStep) -> None:
        """Group the evidence used and the newly revealed clue around each step."""
        active_clues = ", ".join(step.active_clue_ids) or "None"
        self._add_log("deduction", f"Step {step.step_number}",
                      f"Active Clues: {active_clues}")
        for query in step.all_queries:
            self._log_sat_query(query)
        verdict = step.target_verdict.value.lower()
        self._add_log("deduction", f"{step.target_cell} is {verdict}",
                      f"Revealed clue {step.revealed_clue_id}.")

    def _show_auto_solve_result(self, report: AutoSolveReport) -> None:
        """Use the same player-facing result for animated and immediate runs."""
        count = report.total_steps
        steps = f"{count} {'step' if count == 1 else 'steps'}"
        result = {
            AutoSolveStatus.SOLVED: f"Solved in {steps}.",
            AutoSolveStatus.STALLED: "No provable move remains.",
            AutoSolveStatus.INCONSISTENT: "The revealed clues conflict.",
            AutoSolveStatus.ALREADY_SOLVED: "The puzzle is already solved.",
            AutoSolveStatus.STEP_LIMIT_REACHED: f"Paused after {steps}.",
        }[report.status]
        self.status_message = f"{AUTO_SOLVE_LABEL} · {result}"
        self.status_subtitle = f"Steps: {count} · SAT Queries: {report.total_sat_calls}"
        self._add_log("deduction", AUTO_SOLVE_LABEL, f"{result} {self.status_subtitle}.")

    def stop_auto_solve(self) -> None:
        """Cancel pending frames; invalidate callbacks across restart/load/pause."""
        self.auto_running = False
        self._auto_generation += 1
        if self._auto_after_id is not None and self.root is not None:
            self.root.after_cancel(self._auto_after_id)
        self._auto_after_id = None
        for button in getattr(self, "_auto_buttons", (getattr(self, "_auto_button", None),)):
            if button is None:
                continue
            button.config(text=AUTO_SOLVE_LABEL)

    def toggle_auto_solve(self) -> None:
        """Animate actual public reveals, one proven card per timer callback."""
        if self.auto_running:
            self.stop_auto_solve()
            self.status_message = f"{AUTO_SOLVE_LABEL} paused."
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
        for button in getattr(self, "_auto_buttons", (self._auto_button,)):
            button.config(text="Pause")
        generation = self._auto_generation
        self.status_message = f"{AUTO_SOLVE_LABEL} is revealing proven cards."
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
            self.status_message = f"{AUTO_SOLVE_LABEL} stopped. See {LOGS_LABEL} for details."
            self.status_subtitle = str(exc)
            self._add_log("error", AUTO_SOLVE_LABEL, str(exc))
            self._refresh_ui()
            return
        prior_steps = sum(r.total_steps for r in self._animation_reports)
        report = replace(report, steps=tuple(
            replace(step, step_number=prior_steps + index)
            for index, step in enumerate(report.steps, start=1)
        ))
        self._animation_reports.append(report)
        for step in report.steps:
            self._log_deduction_step(step)
            self.selected_cell = step.target_cell
            self.status_message = f"{AUTO_SOLVE_LABEL} · {step.target_cell} is {step.target_verdict.value.lower()}."
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
            if report.status in (AutoSolveStatus.STALLED, AutoSolveStatus.INCONSISTENT):
                self._add_log("sat", "Public Clues",
                              "UNSAT" if report.status == AutoSolveStatus.INCONSISTENT else "SAT")
            self._show_auto_solve_result(self.last_auto_solve_report)
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
        """Lay out the board and let the controls reflow with the window."""
        assert self.root is not None
        _load_reading_fonts()
        self.root.title("Griductive")
        self._ui_scale = self.root.winfo_fpixels("1i") / 96
        px = self._px
        self.root.geometry(f"{min(px(1180), self.root.winfo_screenwidth() - 40)}x"
                           f"{min(px(790), self.root.winfo_screenheight() - 84)}")
        self.root.minsize(px(360), px(390))
        self.root.config(bg=THEME["bg_root"])
        self.root.protocol("WM_DELETE_WINDOW", self._close_window)
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TButton", font=("Segoe UI Semibold", 10), padding=(px(10), px(6)),
                        background=THEME["btn_bg"], foreground=THEME["text_primary"],
                        bordercolor=THEME["btn_border"], lightcolor=THEME["btn_bg"],
                        darkcolor=THEME["btn_bg"], focuscolor=THEME["gold_accent"])
        style.map("TButton", background=[("pressed", "#47566a"), ("active", "#394759")],
                  bordercolor=[("active", THEME["text_muted"])])
        style.configure("TCheckbutton", background=THEME["bg_card"],
                        foreground=THEME["text_primary"], font=(READING_FONT, 10),
                        indicatorcolor=THEME["btn_bg"])
        style.map("TCheckbutton", background=[("active", THEME["bg_card"])],
                  indicatorcolor=[("selected", THEME["gold_accent"])])
        style.configure("Treeview", background=THEME["bg_root"],
                        fieldbackground=THEME["bg_root"], foreground=THEME["text_primary"],
                        font=(READING_FONT, 10), rowheight=px(26), borderwidth=0)
        style.map("Treeview", background=[("selected", THEME["bg_card_selected"])],
                  foreground=[("selected", THEME["border_selected"])])
        style.configure("Treeview.Heading", background=THEME["btn_bg"],
                        foreground=THEME["text_secondary"], font=(READING_FONT, 9, "bold"),
                        relief="flat", padding=(px(6), px(4)))
        style.map("Treeview.Heading", background=[("active", "#394759")])
        for direction in ("Vertical", "Horizontal"):
            style.configure(f"Warm.{direction}.TScrollbar", background=THEME["btn_bg"],
                            troughcolor=THEME["bg_root"], arrowcolor=THEME["text_muted"],
                            bordercolor=THEME["bg_root"], lightcolor=THEME["btn_bg"],
                            darkcolor=THEME["btn_bg"], arrowsize=px(10))
        self._dialog = None
        header = tk.Frame(self.root, bg=THEME["bg_root"])
        header.pack(fill=tk.X, padx=px(22), pady=(px(10), px(6)))
        tk.Label(header, text="Griductive", font=("Georgia", 22, "bold"),
                 bg=THEME["bg_root"], fg=THEME["text_primary"]).pack(side=tk.LEFT)
        self._meta_stats_lbl = tk.Label(header, font=(READING_FONT, 10),
                                       bg=THEME["bg_root"], fg=THEME["text_secondary"])
        self._meta_stats_lbl.pack(side=tk.RIGHT)

        self._board_status = tk.Label(self.root, font=(READING_FONT, 11), anchor="w",
                                      justify=tk.LEFT, bg=THEME["bg_card"],
                                      fg=THEME["text_primary"], height=2,
                                      padx=px(16), pady=px(4))
        self._board_status.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Frame(self.root, bg=THEME["border_subtle"], height=1).pack(side=tk.BOTTOM, fill=tk.X)
        self._board_status.bind("<Configure>",
                                lambda event: self._board_status.config(wraplength=event.width - px(32)))

        utility = tk.Frame(self.root, bg=THEME["bg_root"])
        utility.pack(fill=tk.X, padx=px(16), pady=(0, px(6)))
        self._flow_actions(utility, [
            ("Puzzles", self._on_load_button), ("Restart", self.restart),
            ("Settings", self._show_settings), (LOGS_LABEL, self._show_logs),
        ])

        toolbar = tk.Frame(self.root, bg=THEME["bg_root"])
        toolbar.pack(side=tk.BOTTOM, fill=tk.X, padx=px(16), pady=(px(4), px(8)))
        self._hint_button, self._auto_button, _ = self._flow_actions(toolbar, [
            ("Hint", self._advance_hint), (AUTO_SOLVE_LABEL, self.toggle_auto_solve),
            (CHECK_BOARD_LABEL, self._show_board_check),
        ], primary=True)

        workspace = tk.Frame(self.root, bg=THEME["bg_root"])
        workspace.pack(fill=tk.BOTH, expand=True, padx=px(16))
        workspace.columnconfigure(1, weight=1)
        workspace.rowconfigure(1, weight=1)
        self._puzzle_title_lbl = tk.Label(workspace, font=("Trebuchet MS", 12, "bold"),
                                         bg=THEME["bg_root"], fg=THEME["text_secondary"])
        self._puzzle_title_lbl.grid(row=0, column=1, sticky="ew", pady=(0, px(5)))
        rail = RoundedCard(workspace, bg=THEME["bg_card"],
                           highlightbackground=THEME["border_subtle"],
                           highlightthickness=1, padx=px(18), pady=px(16))
        rail.grid(row=1, column=0, sticky="nw", padx=(0, px(14)), pady=(px(22), 0))
        for text, font, color in (
            ("How to Play", ("Georgia", 17, "bold"), "text_primary"),
            ("Open a card and choose a verdict supported by the clues.", (READING_FONT, 10), "text_secondary"),
            ("A proved verdict reveals a new clue. Use Hint to see the evidence for your next move.",
             (READING_FONT, 10), "text_secondary"),
        ):
            tk.Label(rail, text=text, font=font, fg=THEME[color], bg=THEME["bg_card"],
                     justify=tk.LEFT, wraplength=px(205)).pack(anchor="w", pady=(0, px(8)))

        self._left_col = tk.Frame(workspace, bg=THEME["bg_root"])
        self._left_col.grid(row=1, column=1, sticky="nsew")

        def flow_workspace(event):
            if event.width >= px(890):
                rail.grid()
            else:
                rail.grid_remove()

        workspace.bind("<Configure>", flow_workspace)

        self._logs_window = tk.Toplevel(self.root)
        self._logs_window.withdraw()
        self._logs_window.title(f"{LOGS_LABEL} · Griductive")
        self._logs_window.geometry("500x820")
        self._logs_window.config(bg=THEME["bg_root"])
        self._logs_window.protocol("WM_DELETE_WINDOW", self._logs_window.withdraw)
        self._right_col = tk.Frame(self._logs_window, bg=THEME["bg_root"], padx=14, pady=14)
        self._right_col.pack(fill=tk.BOTH, expand=True)
        self._build_notification_banner()
        self._build_inspector_panel()
        self._auto_buttons = (self._auto_button,)
        self._build_logs_panel()
        self._rebuild_board()

    def _px(self, value: float) -> int:
        """Convert design dimensions to pixels at the Tk startup DPI."""
        return round(value * self._ui_scale)

    def _flow_actions(self, toolbar, actions, *, primary=False):
        """Fit each action group independently within its available width."""
        px = self._px
        buttons = [
            self._game_button(toolbar, label, command, primary=primary and index == 0)
            for index, (label, command) in enumerate(actions)
        ]
        button_height = max(button.winfo_reqheight() for button in buttons)
        button_gap = px(6)

        def flow_toolbar(event=None):
            available = event.width if event else px(780)
            columns = min(len(buttons), max(1, available // px(92)))
            required = [button.winfo_reqwidth() + button_gap for button in buttons]
            while columns > 1 and any(
                sum(required[start:start + columns]) > available
                for start in range(0, len(buttons), columns)
            ):
                columns -= 1
            rows = (len(buttons) + columns - 1) // columns
            toolbar.config(height=rows * (button_height + button_gap) - button_gap)
            for row in range(rows):
                start = row * columns
                widths = required[start:start + columns]
                extra = max(0, min(px(26), (available - sum(widths)) // columns))
                left = (available - sum(widths) - extra * len(widths)) // 2
                for button, width in zip(buttons[start:start + columns], widths):
                    button.place(x=left + button_gap // 2, y=row * (button_height + button_gap),
                                 width=width + extra - button_gap, height=button_height)
                    left += width + extra

        toolbar.bind("<Configure>", flow_toolbar)
        flow_toolbar()

        return buttons

    def _game_button(self, parent, label, command, *, primary=False, colors=None):
        """Create a compact control with a stable target while it animates."""
        palette = colors or (
            ("#443724", "#ffdfab", "#66502d", THEME["gold_accent"]) if primary else
            (THEME["bg_card"], THEME["text_primary"], "#404c5b", "#687280")
        )
        return GameButton(parent, label, command, colors=palette, scale=self._px,
                          reduced_motion=lambda: self.reduced_motion)

    def _show_logs(self) -> None:
        self._logs_window.deiconify()
        self._logs_window.lift()

    def _dismiss_dialog(self) -> None:
        dialog = getattr(self, "_dialog", None)
        if dialog is not None and dialog.winfo_exists():
            dialog.grab_release()
            dialog.destroy()
            previous_focus = getattr(self, "_dialog_previous_focus", None)
            if previous_focus is not None and previous_focus.winfo_exists():
                previous_focus.focus_set()
        self._dialog = None

    def _new_dialog(self, title: str) -> tk.Frame:
        self._dismiss_dialog()
        assert self.root is not None
        dialog = tk.Toplevel(self.root)
        self._dialog = dialog
        self._dialog_previous_focus = self.root.focus_get()
        dialog.withdraw()
        dialog.transient(self.root)
        dialog.title(title)
        dialog.config(bg=THEME["bg_root"])
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", self._dismiss_dialog)
        dialog.bind("<Escape>", lambda e: self._dismiss_dialog())
        panel = RoundedCard(dialog, bg=THEME["bg_card"], padx=self._px(18), pady=self._px(14))
        panel.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        return panel

    def _present_dialog(self) -> None:
        assert self.root is not None and self._dialog is not None
        self._dialog.update_idletasks()
        width = min(self._px(430), self.root.winfo_screenwidth() - 36)
        height = self._dialog.winfo_reqheight()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
        self._dialog.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        self._dialog.deiconify()
        self._dialog.grab_set()
        self._dialog.focus_set()

    def _dialog_text(self, panel: tk.Frame, text: str, heading: bool = False) -> None:
        tk.Label(panel, text=text, wraplength=self._px(366), justify=tk.CENTER,
                 font=("Georgia", 17, "bold") if heading else (READING_FONT, 11),
                 bg=THEME["bg_card"], fg=THEME["text_primary"] if heading else THEME["text_secondary"],
                 pady=self._px(4)).pack(fill=tk.X)

    def _on_card_click(self, cell: CellId) -> None:
        """Inspect a public clue or ask for a verdict without revealing anything."""
        self.stop_auto_solve()
        card = self.controller.public_state.cards[cell]
        if self.hint_clue_cells or self.hinted_cell is not None:
            # Inspecting a clue or cancelling a verdict keeps the current hint.
            if not card.is_revealed:
                self.selected_cell = cell
        else:
            self.select_cell(cell)
        panel = self._new_dialog(card.character.name)
        portrait = tk.Canvas(panel, width=self._px(60), height=self._px(60), bg=THEME["bg_card"], highlightthickness=0)
        portrait.pack()
        portrait.update_idletasks()
        self._draw_avatar(portrait, card.is_revealed, card.status == Status.CRIMINAL,
                          False, card.character.name, card.character.profession)
        self._dialog_text(panel, card.character.name, heading=True)
        self._dialog_text(panel, f"{cell}  ·  {card.character.profession}")
        if card.is_revealed:
            is_criminal = card.status == Status.CRIMINAL
            tk.Label(panel, text=card.status.value.title(), font=(READING_FONT, 10, "bold"),
                     bg=THEME["badge_criminal_bg" if is_criminal else "badge_innocent_bg"],
                     fg=THEME["badge_criminal_fg" if is_criminal else "badge_innocent_fg"],
                     padx=self._px(10), pady=self._px(2)).pack(pady=(self._px(4), self._px(8)))
            tk.Label(panel, text=format_clue_text(card.clue, self.controller.public_state),
                     font=(READING_FONT, 12), wraplength=self._px(360), justify=tk.CENTER,
                     bg=THEME["bg_card"], fg=THEME["text_primary"]).pack(fill=tk.X, pady=(0, 12))
        else:
            self._dialog_text(panel, "Which verdict can you prove?")
            choices = tk.Frame(panel, bg=THEME["bg_card"])
            choices.pack(fill=tk.X, pady=12)
            for label, status, bg, fg in [
                ("Innocent", Status.INNOCENT, THEME["inn_btn_bg"], THEME["border_innocent"]),
                ("Criminal", Status.CRIMINAL, THEME["crim_btn_bg"], THEME["border_criminal"]),
            ]:
                button = self._game_button(
                    choices, label, lambda verdict=status: self._dialog_verdict(verdict),
                    colors=(bg, fg, THEME["inn_btn_hover"] if status == Status.INNOCENT
                            else THEME["crim_btn_hover"], fg),
                )
                column = 0 if status == Status.INNOCENT else 1
                choices.columnconfigure(column, weight=1, uniform="verdict")
                button.grid(row=0, column=column, sticky="ew", padx=4)
        self._game_button(panel, "Close" if card.is_revealed else "Cancel",
                          self._dismiss_dialog).pack(pady=(4, 0))
        self._present_dialog()

    def _dialog_verdict(self, status: Status) -> None:
        self._dismiss_dialog()
        result = self._make_call(status)
        if result.accepted:
            return
        panel = self._new_dialog("Verdict Not Accepted")
        reason = result.rejection_reason
        self._dialog_text(panel, self.status_message, heading=True)
        self._dialog_text(panel, self.status_subtitle)
        self._game_button(panel, "Keep Looking", self._dismiss_dialog).pack(pady=12)
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
            font=(READING_FONT, 16, "bold"),
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
            font=(READING_FONT, 11, "bold"),
            bg=THEME["purple_bg"],
            fg=THEME["text_primary"],
            anchor="w",
            justify=tk.LEFT,
        )
        self._status_label.pack(fill=tk.X)

        self._status_sub_label = tk.Label(
            text_box,
            text=self.status_subtitle,
            font=(READING_FONT, 10),
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
            font=(READING_FONT, 8, "bold"),
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
            bg=THEME["bg_card"],
            highlightthickness=0,
        )
        self._char_avatar_canvas.pack(side=tk.LEFT, padx=(0, 8), pady=2)

        char_text = tk.Frame(char_body, bg=THEME["bg_card"])
        char_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._insp_char_title = tk.Label(
            char_text,
            text="No Card Selected",
            font=(READING_FONT, 9, "bold"),
            bg=THEME["bg_card"],
            fg=THEME["text_primary"],
            anchor="w",
        )
        self._insp_char_title.pack(fill=tk.X)

        self._insp_char_prof = tk.Label(
            char_text,
            text="Click a card to inspect",
            font=(READING_FONT, 8),
            bg=THEME["bg_card"],
            fg=THEME["text_muted"],
            anchor="w",
        )
        self._insp_char_prof.pack(fill=tk.X)

        self._insp_char_badge = tk.Label(
            char_text,
            text="Unknown",
            font=(READING_FONT, 7, "bold"),
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
            font=(READING_FONT, 8, "bold"),
            bg=THEME["bg_card"],
            fg=THEME["text_muted"],
        ).pack(side=tk.LEFT)

        nav_box = tk.Frame(clue_header, bg=THEME["bg_card"])
        nav_box.pack(side=tk.RIGHT)

        tk.Button(
            nav_box,
            text="‹",
            font=(READING_FONT, 9, "bold"),
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
            font=(READING_FONT, 7),
            bg=THEME["bg_card"],
            fg=THEME["text_muted"],
            padx=3,
        )
        self._clue_page_lbl.pack(side=tk.LEFT)

        tk.Button(
            nav_box,
            text="›",
            font=(READING_FONT, 9, "bold"),
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

        clue_prose_frame = tk.Frame(clue_card, bg=THEME["bg_card"])
        clue_prose_frame.pack(fill=tk.X, pady=(2, 0))

        clue_scroll = ttk.Scrollbar(
            clue_prose_frame,
            orient=tk.VERTICAL,
            style="Warm.Vertical.TScrollbar",
        )
        self._clue_prose_lbl = tk.Text(
            clue_prose_frame,
            font=(READING_FONT, 8, "italic"),
            bg=THEME["bg_card"],
            fg=THEME["text_primary"],
            width=1, height=3, wrap=tk.WORD, state=tk.DISABLED,
            relief=tk.FLAT, borderwidth=0, highlightthickness=0,
            yscrollcommand=clue_scroll.set,
        )
        clue_scroll.config(command=self._clue_prose_lbl.yview)
        clue_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._clue_prose_lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._clue_refs_lbl = tk.Label(
            clue_card,
            text="👁  Referenced cells: None",
            font=(READING_FONT, 7, "bold"),
            bg=THEME["bg_card"],
            fg=THEME["gold_accent"],
            anchor="w",
        )
        self._clue_refs_lbl.pack(fill=tk.X, pady=(2, 0))

    def _build_logs_panel(self) -> None:
        """Build the Logs panel and its filters."""
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
            text=LOGS_LABEL,
            font=(READING_FONT, 8, "bold"),
            bg=THEME["bg_card"],
            fg=THEME["text_muted"],
        ).pack(side=tk.LEFT)

        # Filter Pills
        tabs_box = tk.Frame(header, bg=THEME["bg_card"])
        tabs_box.pack(side=tk.RIGHT)

        self._log_tabs = {}
        for tab_name in ["All", "SAT", "Deductions", "Actions"]:
            lbl = tk.Button(
                tabs_box,
                command=lambda name=tab_name: self._set_log_filter(name),
                relief=tk.FLAT,
                text=tab_name,
                font=(READING_FONT, 9, "bold"),
                bg=THEME["purple_accent"] if tab_name == "All" else THEME["btn_bg"],
                fg="white" if tab_name == "All" else THEME["text_secondary"],
                padx=6,
                pady=1,
                cursor="hand2",
            )
            lbl.pack(side=tk.LEFT, padx=1)
            self._log_tabs[tab_name] = lbl

        # Hidden clue listbox maintained for 100% test contract compatibility
        self._clues_listbox = tk.Listbox(panel, height=1)
        # Text log widget styled dark glass
        log_frame = tk.Frame(panel, bg=THEME["bg_card"])
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        log_scroll = ttk.Scrollbar(
            log_frame,
            orient=tk.VERTICAL,
            style="Warm.Vertical.TScrollbar",
        )
        self._log_text = tk.Text(
            log_frame,
            bg=THEME["bg_card"],
            fg=THEME["text_secondary"],
            insertbackground="white",
            relief=tk.FLAT,
            bd=0,
            font=(READING_FONT, 10),
            wrap=tk.WORD,
            highlightthickness=0,
            spacing1=3,
            spacing3=3,
            yscrollcommand=log_scroll.set,
        )
        log_scroll.config(command=self._log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

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

        # Show scrollbars only when cards cannot fit at a readable size.
        px = self._px
        viewport = tk.Canvas(self._left_col, bg=THEME["bg_root"], highlightthickness=0)
        self._board_viewport = viewport
        viewport.pack(fill=tk.BOTH, expand=True)
        vertical = ttk.Scrollbar(self._left_col, orient=tk.VERTICAL, command=viewport.yview,
                                 style="Warm.Vertical.TScrollbar")
        horizontal = ttk.Scrollbar(self._left_col, orient=tk.HORIZONTAL, command=viewport.xview,
                                   style="Warm.Horizontal.TScrollbar")

        def sync_scrollbar(bar, first, last, **placement):
            bar.set(first, last)
            if float(last) - float(first) < 0.999:
                bar.place(**placement)
            else:
                bar.place_forget()

        viewport.config(
            yscrollcommand=lambda first, last: sync_scrollbar(
                vertical, first, last, relx=1, anchor="ne", relheight=1),
            xscrollcommand=lambda first, last: sync_scrollbar(
                horizontal, first, last, rely=1, anchor="sw", relwidth=1),
        )
        board_grid_frame = tk.Frame(viewport, bg=THEME["bg_root"])
        board_window = viewport.create_window((0, 0), window=board_grid_frame, anchor="nw")
        def fit_scrollregion(event=None):
            bounds = viewport.bbox(board_window)
            if bounds is not None:
                viewport.config(scrollregion=(
                    0, 0, max(viewport.winfo_width(), bounds[2]),
                    max(viewport.winfo_height(), bounds[3]),
                ))

        board_grid_frame.bind("<Configure>", fit_scrollregion)

        def fit_board(event):
            horizontal_space = (event.width - px(42)) // n - px(8)
            vertical_space = (event.height - px(35)) // n - px(8)
            width = max(px(80), min(px(200), horizontal_space, round(vertical_space / 0.92)))
            height = max(px(106), round(width * 0.92))
            board_width = n * (width + px(8)) + px(24)
            for card in self._cell_buttons.values():
                card.config(width=width, height=height)
                card._widgets["canvas"].config(height=max(px(29), round(height * 0.34)))
            viewport.itemconfigure(board_window, width=board_width)
            viewport.coords(board_window, max(0, (event.width - board_width) // 2), 0)
            fit_scrollregion()

        viewport.bind("<Configure>", fit_board)

        # Coordinate column headers (A, B, C...)
        for c in range(1, n + 1):
            col_letter = chr(ord("A") + c - 1)
            lbl = tk.Label(
                board_grid_frame,
                text=col_letter,
                font=(READING_FONT, 10, "bold"),
                bg=THEME["bg_root"],
                fg=THEME["text_muted"],
            )
            lbl.grid(row=0, column=c, padx=6, pady=(0, 6))

        # Coordinate row headers (1, 2, 3...)
        for r in range(1, n + 1):
            lbl = tk.Label(
                board_grid_frame,
                text=str(r),
                font=(READING_FONT, 10, "bold"),
                bg=THEME["bg_root"],
                fg=THEME["text_muted"],
            )
            lbl.grid(row=r, column=0, padx=(0, 8), pady=6)

        # Create character card widget for each cell
        for r in range(1, n + 1):
            for c in range(1, n + 1):
                cell = CellId.from_coords(r, c)

                card_frame = CharacterCard(
                    board_grid_frame,
                    scale=px,
                    reduced_motion=lambda: self.reduced_motion,
                    bg=THEME["bg_card"],
                    highlightbackground=THEME["border_card"],
                    highlightthickness=2,
                    padx=px(5),
                    pady=px(4),
                    cursor="hand2",
                    width=168,
                    height=190,
                )
                card_frame.grid(row=r, column=c, padx=px(4), pady=px(4), sticky="nsew")
                card_frame.config(takefocus=True)
                def open_focused(event, target=cell):
                    self._on_card_click(target)
                    return "break"

                card_frame.bind("<Return>", open_focused)
                card_frame.bind("<space>", open_focused)
                card_frame.bind("<FocusIn>", lambda event, card=card_frame: card.config(
                    highlightbackground=THEME["gold_accent"], highlightthickness=3))
                card_frame.bind("<FocusOut>", lambda event: self._refresh_ui())
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
                    font=(READING_FONT, 8, "bold"),
                    bg=THEME["btn_bg"],
                    fg=THEME["text_secondary"],
                    padx=5,
                    pady=1,
                )
                coord_lbl.pack(side=tk.LEFT)
                coord_lbl.bind("<Button-1>", lambda e, cell=cell: self._on_card_click(cell))

                # Revealed cards: the verdict sits opposite the coordinate, and
                # the name/profession share one line so the clue keeps its room.
                status_badge = tk.Label(
                    top_row,
                    text="",
                    font=(READING_FONT, 8, "bold"),
                    bg=THEME["badge_hidden_bg"],
                    fg=THEME["badge_hidden_fg"],
                    padx=6,
                    pady=0,
                )
                status_badge.bind("<Button-1>", lambda e, cell=cell: self._on_card_click(cell))

                identity = tk.Frame(card_frame, bg=THEME["bg_card"])
                identity.bind("<Button-1>", lambda e, cell=cell: self._on_card_click(cell))
                compact_name = tk.Label(identity, font=(READING_FONT, 10, "bold"),
                                        bg=THEME["bg_card"], fg=THEME["text_primary"],
                                        padx=0, pady=0)
                compact_name.pack(side=tk.LEFT)
                compact_prof = tk.Label(identity, font=(READING_FONT, 9),
                                        bg=THEME["bg_card"], fg=THEME["text_muted"],
                                        padx=px(4), pady=0)
                compact_prof.pack(side=tk.LEFT)
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
                    font=(READING_FONT, 12, "bold"),
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
                    font=(READING_FONT, 9),
                    bg=THEME["bg_card"],
                    fg=THEME["text_muted"],
                    anchor="center",
                )
                prof_lbl.pack(fill=tk.X)
                prof_lbl.bind("<Button-1>", lambda e, cell=cell: self._on_card_click(cell))

                # Only public clues are placed on the face of revealed cards.
                clue_snippet = tk.Text(
                    card_frame, font=(READING_FONT, 9),
                    bg=THEME["bg_card"], fg=THEME["text_primary"],
                    width=1, height=4, wrap=tk.WORD, relief=tk.FLAT,
                    borderwidth=0, highlightthickness=0, state=tk.DISABLED,
                    cursor="hand2", takefocus=False, padx=px(2), pady=0,
                    spacing1=0, spacing2=0, spacing3=0,
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
                card_frame.bind_hover()
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

        if self._is_dimmed(cell):
            canvas = w["canvas"]
            for item in canvas.find_all():
                for option in ("fill", "outline"):
                    if option in canvas.itemconfig(item):
                        canvas.itemconfig(item, **{option: self._dim_color(canvas.itemcget(item, option))})

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

        if hasattr(self, "_hint_button"):
            self._hint_button.config(text="Clear" if self.hinted_cell is not None else
                                     "Reveal" if self.hint_clue_cells else "Hint")
        if hasattr(self, "_board_status"):
            self._board_status.config(text=self.status_message + (
                f"\n{self.status_subtitle}" if self.status_subtitle else ""))
            n = self.controller.grid_size
            self._meta_stats_lbl.config(text=f"{n} × {n}  ·  {len(self.controller.public_state.revealed_cells)}/{n*n} revealed")
            title = Path(self.puzzle_source_path).stem.replace("_", " ").title() if self.puzzle_source_path else "A little mystery"
            title = re.sub(r"(\d)[xX](\d)", r"\1×\2", title)
            self._puzzle_title_lbl.config(text=title)

        # 1. Update Notification Banner
        if self._status_label is not None and self._status_icon_label is not None:
            self._status_label.config(text=self.status_message)
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
                            text="Criminal",
                            bg=THEME["badge_criminal_bg"],
                            fg=THEME["badge_criminal_fg"],
                        )
                    else:
                        self._insp_char_badge.config(
                            text="Innocent",
                            bg=THEME["badge_innocent_bg"],
                            fg=THEME["badge_innocent_fg"],
                        )
                else:
                    self._insp_char_badge.config(
                        text="Unknown",
                        bg=THEME["badge_unknown_bg"],
                        fg=THEME["badge_unknown_fg"],
                    )
        else:
            self._insp_char_title.config(text="No Card Selected")
            self._insp_char_prof.config(text="Click a card on the grid")
            self._insp_char_badge.config(
                text="No Card",
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
        px_ = self._px
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
                    badge_text = "Criminal"
                else:
                    card_bg = THEME["bg_card_innocent"]
                    border_color = THEME["border_innocent"]
                    badge_bg = THEME["badge_innocent_bg"]
                    badge_fg = THEME["badge_innocent_fg"]
                    badge_text = "Innocent"

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
                badge_text = "Unknown"

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
                badge_text = "Hidden"

                name_text = view_data.character.name
                prof_text = view_data.character.profession
                prof_fg = THEME["text_muted"]
                show_badge = False

            evidence = cell in self.hint_clue_cells
            target = cell == self.hinted_cell
            if evidence:
                card_bg, border_color = "#273b39", "#85e6bc"
            elif target:
                card_bg, border_color = "#3d3049", "#e0a7ff"
            elif view_data.is_selected:
                if not is_revealed:
                    card_bg = THEME["bg_card_selected"]
                border_color = THEME["border_selected"]
            elif view_data.is_highlighted:
                if not is_revealed:
                    card_bg = THEME["bg_card_highlight"]
                border_color = THEME["border_highlight"]

            dimmed = self._is_dimmed(cell)
            card_frame.set_dimmed(dimmed)
            dim = self._dim_color if dimmed else lambda color: color
            border_width = 4 if (evidence or target) else (
                3 if (view_data.is_selected or view_data.is_highlighted) else 2
            )
            card_frame.config(bg=dim(card_bg), highlightbackground=dim(border_color),
                              highlightthickness=border_width)
            for key in ("top_row", "canvas", "identity"):
                w[key].config(bg=dim(card_bg))
            accent = border_color if evidence or target else THEME["text_primary"]
            w["coord"].config(bg=dim(card_bg), fg=dim(THEME["text_secondary"]))
            w["name"].config(text=name_text, bg=dim(card_bg), fg=dim(accent))
            w["prof"].config(text=prof_text, bg=dim(card_bg), fg=dim(prof_fg))
            w["badge"].config(text=badge_text, bg=dim(badge_bg), fg=dim(badge_fg))
            w["clue"].config(bg=dim(card_bg), fg=dim(THEME["text_primary"]))
            w["compact_name"].config(text=name_text, bg=dim(card_bg), fg=dim(accent))
            w["compact_prof"].config(text=view_data.character.profession,
                                     bg=dim(card_bg), fg=dim(prof_fg))
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
                w["badge"].pack(side=tk.RIGHT)
                w["identity"].pack(fill=tk.X, pady=(px_(1), 0), after=w["top_row"])
                w["clue"].pack(fill=tk.BOTH, expand=True, pady=(px_(2), px_(1)),
                               after=w["identity"])
            else:
                w["identity"].pack_forget()
                w["badge"].pack_forget()
                w["canvas"].config(height=max(self._px(29), round(int(card_frame.cget("height")) * 0.34)))
                w["clue"].pack_forget()
                w["canvas"].pack(fill=tk.X, pady=(2, 2), after=w["top_row"])
                w["name"].pack(fill=tk.X, after=w["canvas"])
                w["prof"].pack(fill=tk.X, after=w["name"])

            self._redraw_cell_avatar(cell)

        # 5. Update Deduction Log Text
        if self._log_text is not None:
            self._log_text.config(state=tk.NORMAL)
            self._log_text.delete("1.0", tk.END)

            self._log_text.tag_configure("icon_action", foreground="#60a5fa", font=(READING_FONT, 10, "bold"))
            self._log_text.tag_configure("icon_deduction", foreground="#34d399", font=(READING_FONT, 10, "bold"))
            self._log_text.tag_configure("icon_sat", foreground="#c084fc", font=(READING_FONT, 10, "bold"))
            self._log_text.tag_configure("icon_info", foreground="#38bdf8", font=(READING_FONT, 10, "bold"))
            self._log_text.tag_configure("icon_error", foreground="#f87171", font=(READING_FONT, 10, "bold"))
            self._log_text.tag_configure("title", foreground="#f8fafc", font=(READING_FONT, 10, "bold"))
            self._log_text.tag_configure("detail", foreground=THEME["text_secondary"], font=(READING_FONT, 10))
            self._log_text.tag_configure("ts", foreground=THEME["text_muted"], font=("Consolas", 9))

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
                self._log_text.insert(tk.END, f"{detail} ", "detail")
                self._log_text.insert(tk.END, f" {ts}\n", "ts")

            if not self._log_text.get("1.0", "end-1c"):
                empty = {
                    "All": "Game events will appear here.",
                    "SAT": "No SAT queries yet.",
                    "Deductions": "No deductions recorded yet.",
                    "Actions": "No actions recorded yet.",
                }
                self._log_text.insert(tk.END, empty[self.log_filter])
            for name, tab in self._log_tabs.items():
                active = name == self.log_filter
                tab.config(bg=THEME["purple_accent"] if active else THEME["btn_bg"],
                           fg=THEME["bg_root"] if active else THEME["text_secondary"])
            self._log_text.see(tk.END)
            self._log_text.config(state=tk.DISABLED)

    def _show_settings(self) -> None:
        panel = self._new_dialog("Settings")
        self._dialog_text(panel, "Settings", heading=True)
        delay = tk.IntVar(master=panel, value=self.animation_delay_ms)
        reduced = tk.BooleanVar(master=panel, value=self.reduced_motion)
        self._dialog_text(panel, f"{AUTO_SOLVE_LABEL} delay between cards (ms)")
        tk.Scale(panel, from_=150, to=1500, resolution=50, orient=tk.HORIZONTAL,
                 variable=delay, bg=THEME["bg_card"], fg=THEME["text_primary"],
                 troughcolor=THEME["bg_root"], activebackground=THEME["gold_accent"],
                 bd=0, sliderrelief=tk.FLAT, font=(READING_FONT, 9),
                 highlightthickness=0).pack(fill=tk.X)

        ttk.Checkbutton(panel, text="Reduce Hover Motion", variable=reduced).pack(pady=(10, 0))

        def save():
            self.animation_delay_ms = delay.get()
            self.reduced_motion = reduced.get()
            self._dismiss_dialog()

        ttk.Button(panel, text="Save Settings", command=save).pack(pady=10)
        self._present_dialog()

    def _on_load_button(self) -> None:
        """List loadable puzzle files in the current folder."""
        self.stop_auto_solve()
        panel = self._new_dialog("Choose Puzzle")
        self._dialog_text(panel, "Choose a Puzzle", heading=True)
        folder = tk.StringVar(master=panel)
        tk.Label(panel, textvariable=folder, wraplength=390, font=(READING_FONT, 9),
                 bg=THEME["bg_card"], fg=THEME["text_secondary"]).pack(fill=tk.X)
        list_area = tk.Frame(panel, bg=THEME["bg_card"])
        list_area.pack(fill=tk.BOTH, expand=True, pady=8)
        table = ttk.Treeview(list_area, columns=("size",), show="tree headings", height=8,
                             selectmode="browse")
        table.heading("#0", text="Puzzle")
        table.heading("size", text="Size")
        table.column("#0", width=270)
        table.column("size", width=60, anchor=tk.CENTER)
        scrollbar = ttk.Scrollbar(list_area, orient=tk.VERTICAL, command=table.yview,
                                  style="Warm.Vertical.TScrollbar")
        table.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        paths: dict[str, Path] = {}
        feedback = tk.StringVar(master=panel)
        tk.Label(panel, textvariable=feedback, font=(READING_FONT, 9),
                 bg=THEME["bg_card"], fg=THEME["text_secondary"]).pack(fill=tk.X)

        def refresh():
            folder.set(str(self.puzzles_dir))
            table.delete(*table.get_children())
            paths.clear()
            skipped = 0
            for path in sorted(self.puzzles_dir.glob("*.json"), key=lambda p: p.name.casefold()):
                if path.name.casefold() == "manifest.json":
                    continue
                try:
                    puzzle = load_puzzle_from_json(path, allow_public_conflict=True)
                except (OSError, ValueError, TypeError, KeyError):
                    skipped += 1
                    continue
                n = puzzle.grid_size
                row = table.insert("", tk.END, text=path.stem.replace("_", " "), values=(f"{n} × {n}",))
                paths[row] = path
            skipped_label = "file" if skipped == 1 else "files"
            feedback.set(f"{len(paths)} puzzles · {skipped} invalid {skipped_label} skipped")
            if paths:
                table.selection_set(next(iter(paths)))

        def browse():
            directory = filedialog.askdirectory(parent=self._dialog, initialdir=self.puzzles_dir)
            if directory:
                self.puzzles_dir = Path(directory)
                refresh()

        def open_selected(event=None):
            selection = table.selection()
            if selection:
                self.load_puzzle(paths[selection[0]])

        buttons = tk.Frame(panel, bg=THEME["bg_card"])
        buttons.pack(fill=tk.X, pady=8)
        ttk.Button(buttons, text="Change Folder", command=browse).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Play Selected", command=open_selected).pack(side=tk.RIGHT)
        table.bind("<Double-1>", open_selected)
        table.bind("<Return>", open_selected)
        refresh()
        self._present_dialog()


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
