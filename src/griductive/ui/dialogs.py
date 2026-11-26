"""Tkinter dialogs for verdicts, board checks, settings, and puzzle selection."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from griductive.domain.model import CellId, Status
from griductive.game.controller import AutoSolveStatus
from griductive.game.io import load_puzzle_from_json
from griductive.ui import formatting
from griductive.ui.portraits import draw_avatar
from griductive.ui.theme import AUTO_SOLVE_LABEL, CHECK_BOARD_LABEL, READING_FONT, THEME
from griductive.ui.widgets import RoundedCard


class _GameDialogs:
    """Modal dialogs used by GriductiveApp."""

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
        draw_avatar(portrait, card.is_revealed, card.status == Status.CRIMINAL,
                          False, card.character.name, card.character.profession)
        self._dialog_text(panel, card.character.name, heading=True)
        self._dialog_text(panel, f"{cell}  ·  {card.character.profession}")
        if card.is_revealed:
            is_criminal = card.status == Status.CRIMINAL
            tk.Label(panel, text=card.status.value.title(), font=(READING_FONT, 10, "bold"),
                     bg=THEME["badge_criminal_bg" if is_criminal else "badge_innocent_bg"],
                     fg=THEME["badge_criminal_fg" if is_criminal else "badge_innocent_fg"],
                     padx=self._px(10), pady=self._px(2)).pack(pady=(self._px(4), self._px(8)))
            tk.Label(panel, text=formatting.format_clue_text(card.clue, self.controller.public_state),
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
        self._dialog_text(panel, self.status_message, heading=True)
        self._dialog_text(panel, self.status_subtitle)
        self._game_button(panel, "Keep Looking", self._dismiss_dialog).pack(pady=12)
        self._present_dialog()

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
