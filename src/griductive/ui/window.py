"""Main window layout, toolbar reflow, and status display."""

from __future__ import annotations

from pathlib import Path
import re
import tkinter as tk
from tkinter import ttk

from griductive.ui.theme import (
    AUTO_SOLVE_LABEL,
    CHECK_BOARD_LABEL,
    LOGS_LABEL,
    READING_FONT,
    THEME,
    load_reading_fonts,
)
from griductive.ui.widgets import GameButton, RoundedCard


class _WindowLayout:
    """Window layout used by GriductiveApp."""

    def _build_ui(self) -> None:
        """Lay out the board and let the controls reflow with the window."""
        assert self.root is not None
        load_reading_fonts()
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

    def _close_window(self) -> None:
        """Stop queued animation before disposing Tk widgets."""
        self.stop_auto_solve()
        assert self.root is not None
        self.root.destroy()

    def _refresh_window_status(self) -> None:
        """Update the puzzle title, reveal count, and controls."""
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
