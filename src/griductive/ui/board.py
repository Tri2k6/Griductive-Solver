"""Scrollable card grid and card rendering for the public board."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from griductive.domain.model import CellId, Status
from griductive.ui.portraits import draw_avatar
from griductive.ui.theme import READING_FONT, THEME
from griductive.ui.widgets import CharacterCard


class _BoardView:
    """Board widgets and scrolling used by GriductiveApp."""

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

                self._cell_buttons[cell] = self._build_card(board_grid_frame, cell, r, c)


        # Configure responsive grid expansion
        for i in range(1, n + 1):
            board_grid_frame.grid_columnconfigure(i, weight=1, uniform="cards")
            board_grid_frame.grid_rowconfigure(i, weight=1, uniform="cards")

    def _build_card(
        self, parent: tk.Frame, cell: CellId, row: int, column: int
    ) -> CharacterCard:
        """Create the widgets and bindings for one card."""
        px = self._px
        card_frame = CharacterCard(
            parent,
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
        card_frame.grid(row=row, column=column, padx=px(4), pady=px(4), sticky="nsew")
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
        return card_frame

    def _redraw_cell_avatar(self, cell: CellId) -> None:
        """Redraw avatar for a specific cell after layout configure."""
        if cell not in self._cell_buttons:
            return
        card_frame = self._cell_buttons[cell]
        w = card_frame._widgets  # type: ignore[attr-defined]
        view_data = self.get_cell_view_data(cell)
        is_crim = (view_data.status == Status.CRIMINAL)
        draw_avatar(
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

    def _refresh_cards(self) -> None:
        """Update card content and highlights from the public view."""
        px_ = self._px
        for cell, card_frame in self._cell_buttons.items():
            view_data = self.get_cell_view_data(cell)
            w = card_frame._widgets  # type: ignore[attr-defined]

            # Coordinate
            w["coord"].config(text=str(cell))

            is_crim = (view_data.status == Status.CRIMINAL)
            is_revealed = view_data.is_revealed
            is_selected = view_data.is_selected

            name_text = view_data.character.name
            prof_text = view_data.character.profession
            prof_fg = THEME["text_muted"]

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
            elif is_selected:
                card_bg = THEME["bg_card_selected"]
                border_color = THEME["border_selected"]
                badge_bg = THEME["badge_unknown_bg"]
                badge_fg = THEME["badge_unknown_fg"]
                badge_text = "Unknown"
            else:
                card_bg = THEME["bg_card"]
                border_color = THEME["border_card"]
                badge_bg = THEME["badge_hidden_bg"]
                badge_fg = THEME["badge_hidden_fg"]
                badge_text = "Hidden"

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
