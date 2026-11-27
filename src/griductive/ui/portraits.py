"""Canvas illustration of character portraits and silhouettes."""

from __future__ import annotations

import tkinter as tk

from griductive.ui.theme import THEME


def draw_avatar(
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
