"""Immutable domain models and types for Griductive Solver."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class CellId:
    """Stable cell coordinate identifier (e.g., 'A1', 'C2').

    Columns are lettered left-to-right starting at 'A' (1-indexed col_idx=1).
    Rows are numbered top-to-bottom starting at 1 (1-indexed row=1).
    Comparison (<, <=, >, >=) uses row-major order: row first, then col_idx.
    """

    name: str
    row: int
    col: str
    col_idx: int

    def __init__(self, name_or_col: str, row: int | None = None) -> None:
        """Initialize from coordinate string 'C2' or (col, row)."""
        if row is not None:
            col_str = name_or_col.upper()
            row_num = int(row)
            if not col_str.isalpha() or len(col_str) != 1:
                raise ValueError(f"Invalid column letter: {name_or_col!r}")
            if row_num < 1:
                raise ValueError(f"Invalid row number (must be >= 1): {row_num}")
            c_idx = ord(col_str) - ord("A") + 1
            formatted_name = f"{col_str}{row_num}"
        else:
            match = re.fullmatch(r"([A-Za-z]+)(\d+)", name_or_col.strip())
            if not match:
                raise ValueError(f"Invalid cell coordinate format: {name_or_col!r}")
            col_str = match.group(1).upper()
            if len(col_str) != 1:
                raise ValueError(f"Column must be a single letter: {name_or_col!r}")
            row_num = int(match.group(2))
            if row_num < 1:
                raise ValueError(f"Row number must be >= 1: {row_num}")
            c_idx = ord(col_str) - ord("A") + 1
            formatted_name = f"{col_str}{row_num}"

        object.__setattr__(self, "name", formatted_name)
        object.__setattr__(self, "row", row_num)
        object.__setattr__(self, "col", col_str)
        object.__setattr__(self, "col_idx", c_idx)

    @classmethod
    def from_coords(cls, row: int, col_idx: int) -> CellId:
        """Create CellId from 1-indexed row and column numbers."""
        if col_idx < 1 or col_idx > 26:
            raise ValueError(f"Column index must be between 1 and 26: {col_idx}")
        col_letter = chr(ord("A") + col_idx - 1)
        return cls(f"{col_letter}{row}")

    @classmethod
    def from_index(cls, index: int, grid_size: int) -> CellId:
        """Create CellId from 0-indexed row-major flat index."""
        if grid_size < 1:
            raise ValueError(f"grid_size must be >= 1: {grid_size}")
        if index < 0 or index >= grid_size * grid_size:
            raise ValueError(
                f"Index {index} out of bounds for grid_size {grid_size} (0..{grid_size * grid_size - 1})"
            )
        row = index // grid_size + 1
        col_idx = index % grid_size + 1
        return cls.from_coords(row, col_idx)

    def to_coords(self) -> tuple[int, int]:
        """Return 1-indexed (row, col_idx)."""
        return self.row, self.col_idx

    def to_index(self, grid_size: int) -> int:
        """Return 0-indexed row-major flat index."""
        if not self.is_valid_for(grid_size):
            raise ValueError(f"Cell {self.name} is not valid for grid_size {grid_size}")
        return (self.row - 1) * grid_size + (self.col_idx - 1)

    def is_valid_for(self, grid_size: int) -> bool:
        """Check if cell is within 1..grid_size bounds."""
        return 1 <= self.row <= grid_size and 1 <= self.col_idx <= grid_size

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        name = getattr(self, "name", "<uninitialized>")
        return f"CellId('{name}')"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CellId):
            return False
        return self.row == other.row and self.col_idx == other.col_idx

    def __hash__(self) -> int:
        return hash((self.row, self.col_idx))

    def __lt__(self, other: CellId) -> bool:
        if not isinstance(other, CellId):
            return NotImplemented
        return (self.row, self.col_idx) < (other.row, other.col_idx)

    def __le__(self, other: CellId) -> bool:
        if not isinstance(other, CellId):
            return NotImplemented
        return (self.row, self.col_idx) <= (other.row, other.col_idx)

    def __gt__(self, other: CellId) -> bool:
        if not isinstance(other, CellId):
            return NotImplemented
        return (self.row, self.col_idx) > (other.row, other.col_idx)

    def __ge__(self, other: CellId) -> bool:
        if not isinstance(other, CellId):
            return NotImplemented
        return (self.row, self.col_idx) >= (other.row, other.col_idx)


class Status(str, Enum):
    """Hidden ground truth or revealed status of a character."""

    CRIMINAL = "CRIMINAL"
    INNOCENT = "INNOCENT"

    def opposite(self) -> Status:
        """Return the opposite status."""
        return Status.INNOCENT if self == Status.CRIMINAL else Status.CRIMINAL

    @classmethod
    def from_bool(cls, val: bool) -> Status:
        """True maps to CRIMINAL, False maps to INNOCENT."""
        return cls.CRIMINAL if val else cls.INNOCENT

    def to_bool(self) -> bool:
        """Return True for CRIMINAL, False for INNOCENT."""
        return self == Status.CRIMINAL


class Parity(str, Enum):
    """Parity constraint value for the parity extension."""

    EVEN = "EVEN"
    ODD = "ODD"


class Verdict(str, Enum):
    """Classification outcome for a character status query."""

    CRIMINAL = "CRIMINAL"
    INNOCENT = "INNOCENT"
    UNKNOWN = "UNKNOWN"
    INCONSISTENT = "INCONSISTENT"


class RejectionReason(str, Enum):
    """Reason for rejecting an unprovable or contradicted manual call."""

    NOT_PROVABLE = "NOT_PROVABLE"
    CONTRADICTED = "CONTRADICTED"


# ============================================================================
# Region expressions
# ============================================================================


@dataclass(frozen=True)
class RegionExpr:
    """Base class for region expressions."""


@dataclass(frozen=True)
class RowRegion(RegionExpr):
    """All cells in a given row (1..N)."""

    row: int


@dataclass(frozen=True)
class ColRegion(RegionExpr):
    """All cells in a given column letter ('A'..'Z')."""

    col: str


@dataclass(frozen=True)
class NeighborsRegion(RegionExpr):
    """Eight-direction neighbors of a cell, excluding the center itself."""

    center: CellId


@dataclass(frozen=True)
class ExplicitRegion(RegionExpr):
    """Explicitly specified distinct list of cells."""

    cells: tuple[CellId, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "cells", tuple(self.cells))


@dataclass(frozen=True)
class CommonNeighborsRegion(RegionExpr):
    """Intersection of eight-neighbors of cell_a and eight-neighbors of cell_b."""

    cell_a: CellId
    cell_b: CellId


# ============================================================================
# Clue variants
# ============================================================================


@dataclass(frozen=True)
class Clue:
    """Base class for structured clues."""

    clue_id: str
    owner: CellId


@dataclass(frozen=True)
class FactClue(Clue):
    """FACT(person, status): A named person has the given status."""

    target: CellId
    status: Status
    target_name: str | None = None


@dataclass(frozen=True)
class SameClue(Clue):
    """SAME(person_a, person_b): Two people have the same status."""

    person_a: CellId
    person_b: CellId
    name_a: str | None = None
    name_b: str | None = None


@dataclass(frozen=True)
class DifferentClue(Clue):
    """DIFFERENT(person_a, person_b): Two people have different statuses."""

    person_a: CellId
    person_b: CellId
    name_a: str | None = None
    name_b: str | None = None


@dataclass(frozen=True)
class ExactlyClue(Clue):
    """EXACTLY(k, region): Exactly k criminals in the region."""

    k: int
    region: RegionExpr


@dataclass(frozen=True)
class AtLeastClue(Clue):
    """AT_LEAST(k, region): At least k criminals in the region."""

    k: int
    region: RegionExpr


@dataclass(frozen=True)
class AtMostClue(Clue):
    """AT_MOST(k, region): At most k criminals in the region."""

    k: int
    region: RegionExpr


@dataclass(frozen=True)
class ParityClue(Clue):
    """PARITY(region, parity): Criminals count in region has given parity."""

    parity: Parity
    region: RegionExpr


# ============================================================================
# Character and Card representations
# ============================================================================


@dataclass(frozen=True)
class Character:
    """Public character metadata (cell, unique display name, profession)."""

    cell: CellId
    name: str
    profession: str


@dataclass(frozen=True)
class PublicCard:
    """Public view of a card at a cell.

    If is_revealed is False, status and clue MUST be None.
    If is_revealed is True, status and clue MUST be present.
    """

    cell: CellId
    character: Character
    is_revealed: bool
    status: Status | None = None
    clue: Clue | None = None

    def __post_init__(self) -> None:
        if self.cell != self.character.cell:
            raise ValueError(
                f"PublicCard cell {self.cell} does not match character cell {self.character.cell}."
            )
        if not self.is_revealed:
            if self.status is not None or self.clue is not None:
                raise ValueError(
                    f"Face-down card at {self.cell} must not expose status or clue."
                )
        else:
            if self.status is None or self.clue is None:
                raise ValueError(
                    f"Revealed card at {self.cell} must have both status and clue exposed."
                )
            if self.clue.owner != self.cell:
                raise ValueError(
                    f"Revealed card at {self.cell} has clue belonging to owner {self.clue.owner}."
                )


# ============================================================================
# Private Puzzle and Public State
# ============================================================================


@dataclass(frozen=True)
class Puzzle:
    """Complete private puzzle model owned by GameEngine.

    Contains the ground truth solution and all clues (face-up and face-down).
    Must NEVER be leaked or passed to LogicAgent.
    """

    grid_size: int
    characters: tuple[Character, ...]
    solution: Mapping[CellId, Status]
    clues: Mapping[CellId, Clue]
    initial_face_up: frozenset[CellId]

    def __post_init__(self) -> None:
        if self.grid_size < 2:
            raise ValueError(f"grid_size must be >= 2: {self.grid_size}")

        object.__setattr__(self, "characters", tuple(self.characters))
        object.__setattr__(self, "solution", MappingProxyType(dict(self.solution)))
        object.__setattr__(self, "clues", MappingProxyType(dict(self.clues)))
        object.__setattr__(self, "initial_face_up", frozenset(self.initial_face_up))

        expected_cells = self.grid_size * self.grid_size
        if len(self.characters) != expected_cells:
            raise ValueError(
                f"Expected {expected_cells} characters for grid_size {self.grid_size}, got {len(self.characters)}"
            )
        if len(self.solution) != expected_cells:
            raise ValueError(
                f"Expected {expected_cells} solution entries for grid_size {self.grid_size}, got {len(self.solution)}"
            )
        if len(self.clues) != expected_cells:
            raise ValueError(
                f"Expected {expected_cells} clues for grid_size {self.grid_size}, got {len(self.clues)}"
            )

        char_cells = set()
        names = set()
        for char in self.characters:
            if not char.cell.is_valid_for(self.grid_size):
                raise ValueError(
                    f"Character cell {char.cell} is not valid for grid_size {self.grid_size}"
                )
            if char.cell in char_cells:
                raise ValueError(f"Duplicate character cell: {char.cell}")
            char_cells.add(char.cell)

            if char.name in names:
                raise ValueError(f"Duplicate character name: {char.name!r}")
            names.add(char.name)

            if char.cell not in self.solution:
                raise ValueError(f"Missing solution for cell {char.cell}")
            if char.cell not in self.clues:
                raise ValueError(f"Missing clue for cell {char.cell}")

        if set(self.solution.keys()) != char_cells:
            raise ValueError("Solution keys do not match character cells")
        if set(self.clues.keys()) != char_cells:
            raise ValueError("Clue keys do not match character cells")

        for cell, clue in self.clues.items():
            if clue.owner != cell:
                raise ValueError(f"Clue for cell {cell} has mismatched owner {clue.owner}")

        if not self.initial_face_up.issubset(char_cells):
            raise ValueError("initial_face_up contains cells outside the puzzle grid")


@dataclass(frozen=True)
class PublicState:
    """Immutable public game state visible to players, LogicAgent, and GUI.

    Contains only publicly revealed knowledge:
    - Visible character labels and professions
    - Known statuses of revealed cards
    - Clues of revealed cards
    - No hidden statuses or face-down clues are accessible.
    """

    grid_size: int
    characters: tuple[Character, ...]
    cards: Mapping[CellId, PublicCard]
    known_statuses: Mapping[CellId, Status]
    revealed_clues: tuple[Clue, ...]
    revealed_cells: frozenset[CellId]
    revision: int = 0

    def __post_init__(self) -> None:
        if self.grid_size < 1:
            raise ValueError(f"grid_size must be >= 1: {self.grid_size}")

        object.__setattr__(self, "characters", tuple(self.characters))
        object.__setattr__(self, "cards", MappingProxyType(dict(self.cards)))
        object.__setattr__(self, "known_statuses", MappingProxyType(dict(self.known_statuses)))
        object.__setattr__(self, "revealed_clues", tuple(self.revealed_clues))
        object.__setattr__(self, "revealed_cells", frozenset(self.revealed_cells))

        expected_cells = self.grid_size * self.grid_size
        if len(self.characters) != expected_cells:
            raise ValueError(
                f"Expected {expected_cells} characters for grid_size {self.grid_size}, got {len(self.characters)}"
            )
        if len(self.cards) != expected_cells:
            raise ValueError(
                f"Expected {expected_cells} cards for grid_size {self.grid_size}, got {len(self.cards)}"
            )

        names = [c.name for c in self.characters]
        if names != sorted(names):
            raise ValueError("Characters must be sorted alphabetically by display name.")

        for cell, card in self.cards.items():
            if not cell.is_valid_for(self.grid_size):
                raise ValueError(f"Card cell {cell} is not valid for grid_size {self.grid_size}.")
            if card.cell != cell:
                raise ValueError(f"Card mapping key {cell} does not match card.cell {card.cell}.")

            if card.is_revealed:
                if cell not in self.revealed_cells:
                    raise ValueError(f"Revealed card at {cell} is not in revealed_cells.")
                if cell not in self.known_statuses:
                    raise ValueError(f"Revealed card at {cell} is not in known_statuses.")
                if card.status != self.known_statuses[cell]:
                    raise ValueError(
                        f"Card status {card.status} at {cell} does not match known_statuses[{cell}] {self.known_statuses[cell]}."
                    )
            else:
                if cell in self.revealed_cells:
                    raise ValueError(f"Face-down card at {cell} is present in revealed_cells.")
                if cell in self.known_statuses:
                    raise ValueError(f"Unrevealed cell {cell} present in known_statuses!")
                if card.status is not None or card.clue is not None:
                    raise ValueError(f"Face-down card at {cell} exposes status or clue!")

        if frozenset(self.known_statuses.keys()) != self.revealed_cells:
            raise ValueError(
                "known_statuses keys must match revealed_cells exactly."
            )

        if len(self.revealed_clues) != len(self.revealed_cells):
            raise ValueError(
                f"revealed_clues count ({len(self.revealed_clues)}) does not match revealed_cells count ({len(self.revealed_cells)})."
            )
        revealed_owners = {clue.owner for clue in self.revealed_clues}
        if revealed_owners != self.revealed_cells:
            raise ValueError(
                "revealed_clues owners must match revealed_cells exactly."
            )

        for clue in self.revealed_clues:
            card = self.cards.get(clue.owner)
            if card is None or card.clue != clue:
                raise ValueError(
                    f"revealed_clue for {clue.owner} does not match card.clue {getattr(card, 'clue', None)}."
                )
        expected_clue_order = tuple(sorted(self.revealed_clues, key=lambda c: c.owner))
        if self.revealed_clues != expected_clue_order:
            raise ValueError("revealed_clues must be ordered deterministically by clue owner cell.")



def create_initial_public_state(puzzle: Puzzle) -> PublicState:
    """Create the initial public state from a private puzzle.

    Only cards in puzzle.initial_face_up are revealed.
    Characters are sorted alphabetically by display name.
    """
    sorted_characters = tuple(sorted(puzzle.characters, key=lambda c: c.name))
    revealed_cells = puzzle.initial_face_up

    cards: dict[CellId, PublicCard] = {}
    known_statuses: dict[CellId, Status] = {}
    revealed_clues_list: list[Clue] = []

    for char in puzzle.characters:
        cell = char.cell
        if cell in revealed_cells:
            status = puzzle.solution[cell]
            clue = puzzle.clues[cell]
            cards[cell] = PublicCard(
                cell=cell,
                character=char,
                is_revealed=True,
                status=status,
                clue=clue,
            )
            known_statuses[cell] = status
            revealed_clues_list.append(clue)
        else:
            cards[cell] = PublicCard(
                cell=cell,
                character=char,
                is_revealed=False,
                status=None,
                clue=None,
            )

    # Sort revealed clues deterministically in row-major order of owner
    revealed_clues_list.sort(key=lambda clue: clue.owner)

    return PublicState(
        grid_size=puzzle.grid_size,
        characters=sorted_characters,
        cards=cards,
        known_statuses=known_statuses,
        revealed_clues=tuple(revealed_clues_list),
        revealed_cells=revealed_cells,
        revision=0,
    )
