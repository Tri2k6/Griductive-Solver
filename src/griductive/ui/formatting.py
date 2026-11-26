"""Text formatting and immutable view data for the public board."""

from __future__ import annotations

from dataclasses import dataclass

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
    PublicState,
    RegionExpr,
    RowRegion,
    SameClue,
    Status,
)


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
