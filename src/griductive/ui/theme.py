"""Shared colors, labels, and bundled font registration."""

from __future__ import annotations

from functools import cache
from pathlib import Path
import sys


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
def load_reading_fonts() -> None:
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
