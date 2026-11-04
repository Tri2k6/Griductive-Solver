"""UI module for Griductive.

Contains the interactive Tkinter desktop GUI application.
"""

from griductive.ui.gui import (
    GriductiveApp,
    format_clue_text,
    format_region_text,
    launch_gui,
)

__all__ = [
    "GriductiveApp",
    "launch_gui",
    "format_region_text",
    "format_clue_text",
]

