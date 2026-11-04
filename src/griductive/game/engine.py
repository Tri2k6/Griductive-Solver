"""Game engine managing private puzzle state and publishing immutable public snapshots."""

from __future__ import annotations

from griductive.domain.model import (
    CellId,
    Clue,
    PublicCard,
    PublicState,
    Puzzle,
    Status,
)


class GameEngine:
    """Manages the private state of a Griductive puzzle and emits immutable public views.

    The GameEngine owns the ground truth solution and all unrevealed clues.
    It guarantees that:
    1. Only revealed cards expose their status and clue.
    2. Face-down cards expose only character metadata with status=None and clue=None.
    3. Invalid or rejected internal transition requests do not mutate the engine's
       internal state or increment its revision.
    4. Successful internal transitions update the revealed card set, increment
       revision, and return (status, clue).
    5. Restart resets the engine to its initial face-up configuration.
    """

    def __init__(self, puzzle: Puzzle) -> None:
        """Initialize the game engine with a private Puzzle instance."""
        if not isinstance(puzzle, Puzzle):
            raise TypeError(f"puzzle must be a Puzzle instance, got {type(puzzle).__name__}")

        self._puzzle: Puzzle = puzzle
        self._revealed_cells: set[CellId] = set(puzzle.initial_face_up)
        self._revision: int = 0

    @property
    def grid_size(self) -> int:
        """Return the grid size N of the puzzle."""
        return self._puzzle.grid_size

    @property
    def revision(self) -> int:
        """Return the monotonic state revision counter."""
        return self._revision

    @property
    def is_solved(self) -> bool:
        """Return True if all characters in the puzzle have been revealed."""
        return len(self._revealed_cells) == len(self._puzzle.characters)

    @property
    def public_state(self) -> PublicState:
        """Construct and return a fresh, immutable snapshot of the public game state."""
        # Characters must be sorted alphabetically by display name
        sorted_characters = tuple(sorted(self._puzzle.characters, key=lambda c: c.name))

        cards: dict[CellId, PublicCard] = {}
        known_statuses: dict[CellId, Status] = {}
        revealed_clues_list: list[Clue] = []

        for char in self._puzzle.characters:
            cell = char.cell
            if cell in self._revealed_cells:
                status = self._puzzle.solution[cell]
                clue = self._puzzle.clues[cell]
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

        # Clues ordered deterministically by owner cell in row-major order
        revealed_clues = tuple(sorted(revealed_clues_list, key=lambda c: c.owner))
        revealed_cells = frozenset(self._revealed_cells)

        return PublicState(
            grid_size=self._puzzle.grid_size,
            characters=sorted_characters,
            cards=cards,
            known_statuses=known_statuses,
            revealed_clues=revealed_clues,
            revealed_cells=revealed_cells,
            revision=self._revision,
        )

    def get_public_state(self) -> PublicState:
        """Convenience method returning public_state."""
        return self.public_state

    def public_view(self) -> PublicState:
        """Alias for public_state matching architecture specification."""
        return self.public_state

    def _reveal_proven(
        self, cell: CellId | str, verdict: Status | str
    ) -> tuple[Status, Clue]:
        """Commit a verdict that the controller has already proven publicly.

        This is an internal transition, not a supported player-facing operation.
        ``GameController`` performs SAT entailment before invoking it; this method
        only defends private state integrity by checking the supplied verdict against
        the hidden solution. Errors intentionally never disclose that solution.

        Python leading underscores are a convention, not a security sandbox. Public
        callers must use ``GameController.make_call()``, ``step()``, or
        ``auto_solve()``; application code must not retain or expose this engine.
        """
        # Normalize and validate cell
        if isinstance(cell, str):
            try:
                target_cell = CellId(cell)
            except ValueError as exc:
                raise ValueError(f"Invalid cell coordinate format: {cell!r}") from exc
        elif isinstance(cell, CellId):
            target_cell = cell
        else:
            raise TypeError(f"cell must be CellId or str, got {type(cell).__name__}")

        if target_cell not in self._puzzle.solution:
            raise ValueError(f"Cell {target_cell} is out of bounds or not in puzzle.")

        # Check if already revealed
        if target_cell in self._revealed_cells:
            raise ValueError(f"Cell {target_cell} has already been revealed.")

        # Normalize and validate verdict
        if isinstance(verdict, str):
            try:
                expected_verdict = Status(verdict.strip().upper())
            except ValueError as exc:
                raise ValueError(f"Invalid status verdict: {verdict!r}. Must be CRIMINAL or INNOCENT.") from exc
        elif isinstance(verdict, Status):
            expected_verdict = verdict
        else:
            raise TypeError(f"verdict must be Status or str, got {type(verdict).__name__}")

        # Check verdict against ground truth solution
        actual_status = self._puzzle.solution[target_cell]
        if expected_verdict != actual_status:
            # Rejection: CRITICALLY leave state and revision untouched!
            raise ValueError(f"Verdict for cell {target_cell} cannot be committed.")

        # Successful reveal: advance state
        self._revealed_cells.add(target_cell)
        self._revision += 1
        return actual_status, self._puzzle.clues[target_cell]

    def restart(self) -> PublicState:
        """Reset the engine back to its initial face-up state."""
        self._revealed_cells = set(self._puzzle.initial_face_up)
        self._revision = 0
        return self.public_state
