"""Unit tests for domain models and immutable types."""

import pytest
from griductive.domain.model import (
    AtLeastClue,
    AtMostClue,
    CellId,
    Character,
    ColRegion,
    CommonNeighborsRegion,
    DifferentClue,
    ExactlyClue,
    ExplicitRegion,
    FactClue,
    NeighborsRegion,
    Parity,
    ParityClue,
    PublicCard,
    PublicState,
    Puzzle,
    RejectionReason,
    RowRegion,
    SameClue,
    Status,
    Verdict,
    create_initial_public_state,
)


class TestCellId:
    def test_parse_and_properties(self) -> None:
        cell = CellId("C2")
        assert cell.name == "C2"
        assert cell.col == "C"
        assert cell.row == 2
        assert cell.col_idx == 3
        assert cell.to_coords() == (2, 3)

    def test_case_insensitivity(self) -> None:
        cell = CellId("b4")
        assert cell.name == "B4"
        assert cell.col == "B"
        assert cell.row == 4
        assert cell.col_idx == 2

    def test_from_coords(self) -> None:
        cell = CellId.from_coords(row=3, col_idx=1)
        assert cell.name == "A3"
        assert cell.row == 3
        assert cell.col == "A"
        assert cell.col_idx == 1

    def test_index_round_trip(self) -> None:
        for grid_size in (3, 4, 5):
            total_cells = grid_size * grid_size
            for idx in range(total_cells):
                cell = CellId.from_index(idx, grid_size)
                assert cell.to_index(grid_size) == idx

    def test_row_major_ordering(self) -> None:
        cells_3x3 = [
            CellId("A1"),
            CellId("B1"),
            CellId("C1"),
            CellId("A2"),
            CellId("B2"),
            CellId("C2"),
            CellId("A3"),
            CellId("B3"),
            CellId("C3"),
        ]
        # Unsorted list
        scrambled = [
            CellId("C3"),
            CellId("A2"),
            CellId("B1"),
            CellId("A1"),
            CellId("C1"),
            CellId("B3"),
            CellId("C2"),
            CellId("A3"),
            CellId("B2"),
        ]
        assert sorted(scrambled) == cells_3x3

    def test_equality_and_hash(self) -> None:
        c1 = CellId("B2")
        c2 = CellId.from_coords(2, 2)
        assert c1 == c2
        assert hash(c1) == hash(c2)
        s = {c1}
        assert c2 in s

    def test_invalid_formats(self) -> None:
        with pytest.raises(ValueError, match="Invalid cell coordinate format"):
            CellId("12")
        with pytest.raises(ValueError, match="Column must be a single letter"):
            CellId("AB1")
        with pytest.raises(ValueError, match="Row number must be >= 1"):
            CellId("A0")
        with pytest.raises(ValueError, match="grid_size must be >= 1"):
            CellId.from_index(0, 0)
        with pytest.raises(ValueError, match="out of bounds"):
            CellId.from_index(9, 3)

    def test_immutability(self) -> None:
        cell = CellId("A1")
        with pytest.raises(Exception):
            cell.row = 5  # type: ignore[misc]


class TestEnums:
    def test_status_methods(self) -> None:
        assert Status.CRIMINAL.opposite() == Status.INNOCENT
        assert Status.INNOCENT.opposite() == Status.CRIMINAL
        assert Status.from_bool(True) == Status.CRIMINAL
        assert Status.from_bool(False) == Status.INNOCENT
        assert Status.CRIMINAL.to_bool() is True
        assert Status.INNOCENT.to_bool() is False

    def test_verdict_and_rejection_reasons(self) -> None:
        assert Verdict.CRIMINAL == "CRIMINAL"
        assert Verdict.UNKNOWN == "UNKNOWN"
        assert Verdict.INCONSISTENT == "INCONSISTENT"
        assert RejectionReason.NOT_PROVABLE == "NOT_PROVABLE"
        assert RejectionReason.CONTRADICTED == "CONTRADICTED"
        assert Parity.EVEN == "EVEN"
        assert Parity.ODD == "ODD"


class TestCluesAndRegions:
    def test_region_instantiation(self) -> None:
        r1 = RowRegion(1)
        r2 = ColRegion("B")
        r3 = NeighborsRegion(CellId("B2"))
        r4 = ExplicitRegion((CellId("A1"), CellId("C3")))
        r5 = CommonNeighborsRegion(CellId("A1"), CellId("C1"))
        assert r1.row == 1
        assert r2.col == "B"
        assert r3.center == CellId("B2")
        assert len(r4.cells) == 2
        assert r5.cell_a == CellId("A1")

    def test_typed_clues(self) -> None:
        c1 = FactClue("clue_1", CellId("A1"), CellId("B2"), Status.CRIMINAL, "Alice")
        c2 = SameClue("clue_2", CellId("A2"), CellId("A1"), CellId("B1"))
        c3 = DifferentClue("clue_3", CellId("A3"), CellId("B2"), CellId("C3"))
        c4 = ExactlyClue("clue_4", CellId("B1"), 2, RowRegion(1))
        c5 = AtLeastClue("clue_5", CellId("B2"), 1, ColRegion("C"))
        c6 = AtMostClue("clue_6", CellId("B3"), 3, NeighborsRegion(CellId("B2")))
        c7 = ParityClue("clue_7", CellId("C1"), Parity.EVEN, ExplicitRegion((CellId("A1"), CellId("C3"))))

        assert c1.status == Status.CRIMINAL
        assert c2.person_a == CellId("A1")
        assert c3.person_b == CellId("C3")
        assert c4.k == 2
        assert c5.k == 1
        assert c6.k == 3
        assert c7.parity == Parity.EVEN


class TestPuzzleAndPublicState:
    def _create_sample_3x3_puzzle(self) -> Puzzle:
        characters = []
        solution = {}
        clues = {}
        # 3x3 cells: A1, B1, C1, A2, B2, C2, A3, B3, C3
        names = ["Zara", "Bob", "Charlie", "David", "Eve", "Frank", "Grace", "Heidi", "Alice"]
        for idx in range(9):
            cell = CellId.from_index(idx, 3)
            char = Character(cell=cell, name=names[idx], profession="Citizen")
            characters.append(char)
            # Even index: Criminal, Odd: Innocent
            solution[cell] = Status.CRIMINAL if idx % 2 == 0 else Status.INNOCENT
            clues[cell] = FactClue(f"clue_{cell}", cell, cell, solution[cell])

        return Puzzle(
            grid_size=3,
            characters=tuple(characters),
            solution=solution,
            clues=clues,
            initial_face_up=frozenset([CellId("A1"), CellId("C3")]),
        )

    def test_public_card_invariants(self) -> None:
        char = Character(CellId("A1"), "Alice", "Baker")
        # Face-down card cannot expose status or clue
        with pytest.raises(ValueError, match="Face-down card.*must not expose"):
            PublicCard(CellId("A1"), char, is_revealed=False, status=Status.CRIMINAL)

        with pytest.raises(ValueError, match="Face-down card.*must not expose"):
            clue = FactClue("c1", CellId("A1"), CellId("A1"), Status.INNOCENT)
            PublicCard(CellId("A1"), char, is_revealed=False, clue=clue)

        # Revealed card must have both status and clue
        with pytest.raises(ValueError, match="Revealed card.*must have both status and clue"):
            PublicCard(CellId("A1"), char, is_revealed=True, status=None, clue=None)

    def test_initial_public_state_creation(self) -> None:
        puzzle = self._create_sample_3x3_puzzle()
        state = create_initial_public_state(puzzle)

        assert state.grid_size == 3
        assert state.revealed_cells == frozenset([CellId("A1"), CellId("C3")])
        assert len(state.known_statuses) == 2
        assert len(state.revealed_clues) == 2

        # Check alphabetical sorting of public characters
        char_names = [c.name for c in state.characters]
        assert char_names == sorted(char_names)
        assert char_names[0] == "Alice"
        assert char_names[-1] == "Zara"

        # Check face-down card exposure is prevented
        for cell, card in state.cards.items():
            if cell in state.revealed_cells:
                assert card.is_revealed is True
                assert card.status is not None
                assert card.clue is not None
            else:
                assert card.is_revealed is False
                assert card.status is None
                assert card.clue is None

    def test_puzzle_duplicate_names_rejected(self) -> None:
        chars = [
            Character(CellId("A1"), "Alice", "Cook"),
            Character(CellId("B1"), "Alice", "Doctor"),
            Character(CellId("A2"), "Charlie", "Engineer"),
            Character(CellId("B2"), "David", "Lawyer"),
        ]
        sol = {c.cell: Status.INNOCENT for c in chars}
        clues = {c.cell: FactClue(f"c_{c.cell}", c.cell, c.cell, Status.INNOCENT) for c in chars}

        with pytest.raises(ValueError, match="Duplicate character name"):
            Puzzle(
                grid_size=2,
                characters=tuple(chars),
                solution=sol,
                clues=clues,
                initial_face_up=frozenset([CellId("A1")]),
            )

    def test_explicit_region_coercion_and_immutability(self) -> None:
        cells_list = [CellId("A1"), CellId("B2")]
        region = ExplicitRegion(cells_list)  # type: ignore[arg-type]
        assert isinstance(region.cells, tuple)
        cells_list.append(CellId("C3"))
        assert region.cells == (CellId("A1"), CellId("B2"))

    def test_puzzle_source_alias_mutation_prevention(self) -> None:
        chars = [
            Character(CellId("A1"), "Alice", "Cook"),
            Character(CellId("B1"), "Bob", "Doctor"),
            Character(CellId("A2"), "Charlie", "Engineer"),
            Character(CellId("B2"), "David", "Lawyer"),
        ]
        sol = {c.cell: Status.INNOCENT for c in chars}
        clues = {c.cell: FactClue(f"c_{c.cell}", c.cell, c.cell, Status.INNOCENT) for c in chars}
        init_up = {CellId("A1")}

        puzzle = Puzzle(
            grid_size=2,
            characters=tuple(chars),
            solution=sol,
            clues=clues,
            initial_face_up=init_up,  # type: ignore[arg-type]
        )

        # Mutate source dicts and set
        sol[CellId("A1")] = Status.CRIMINAL
        clues[CellId("A1")] = FactClue("mutated", CellId("A1"), CellId("A1"), Status.CRIMINAL)
        init_up.add(CellId("B1"))

        assert puzzle.solution[CellId("A1")] == Status.INNOCENT
        assert puzzle.clues[CellId("A1")].clue_id == "c_A1"
        assert puzzle.initial_face_up == frozenset([CellId("A1")])

    def test_puzzle_mapping_proxy_raises_type_error(self) -> None:
        puzzle = self._create_sample_3x3_puzzle()
        with pytest.raises(TypeError):
            puzzle.solution[CellId("A1")] = Status.INNOCENT  # type: ignore[index]
        with pytest.raises(TypeError):
            puzzle.clues[CellId("A1")] = FactClue("c", CellId("A1"), CellId("A1"), Status.INNOCENT)  # type: ignore[index]

    def test_puzzle_invariants(self) -> None:
        chars = [
            Character(CellId("A1"), "Alice", "Cook"),
            Character(CellId("B1"), "Bob", "Doctor"),
            Character(CellId("A2"), "Charlie", "Engineer"),
            Character(CellId("B2"), "David", "Lawyer"),
        ]
        sol = {c.cell: Status.INNOCENT for c in chars}
        clues = {c.cell: FactClue(f"c_{c.cell}", c.cell, c.cell, Status.INNOCENT) for c in chars}

        # Clue owner mismatch
        bad_clues = dict(clues)
        bad_clues[CellId("A1")] = FactClue("bad", CellId("B1"), CellId("B1"), Status.INNOCENT)
        with pytest.raises(ValueError, match="mismatched owner"):
            Puzzle(2, tuple(chars), sol, bad_clues, frozenset([CellId("A1")]))

        # Missing cell in solution
        bad_sol = {CellId("A1"): Status.INNOCENT}
        with pytest.raises(ValueError, match="Expected 4 solution entries"):
            Puzzle(2, tuple(chars), bad_sol, clues, frozenset([CellId("A1")]))

        # Initial face up outside grid
        with pytest.raises(ValueError, match="outside the puzzle grid"):
            Puzzle(2, tuple(chars), sol, clues, frozenset([CellId("C3")]))

    def test_public_card_mismatched_cell_and_character(self) -> None:
        char = Character(CellId("A1"), "Alice", "Cook")
        with pytest.raises(ValueError, match="does not match character cell"):
            PublicCard(CellId("B1"), char, is_revealed=False)

    def test_public_card_revealed_clue_owner_mismatch(self) -> None:
        char = Character(CellId("A1"), "Alice", "Cook")
        clue = FactClue("c", CellId("B1"), CellId("B1"), Status.INNOCENT)
        with pytest.raises(ValueError, match="has clue belonging to owner"):
            PublicCard(CellId("A1"), char, is_revealed=True, status=Status.INNOCENT, clue=clue)

    def test_public_state_immutability_and_source_aliasing(self) -> None:
        puzzle = self._create_sample_3x3_puzzle()
        state = create_initial_public_state(puzzle)

        # Mutating MappingProxyType directly raises TypeError
        with pytest.raises(TypeError):
            state.cards[CellId("A1")] = PublicCard(  # type: ignore[index]
                CellId("A1"), Character(CellId("A1"), "A", "P"), is_revealed=False
            )
        with pytest.raises(TypeError):
            state.known_statuses[CellId("A1")] = Status.INNOCENT  # type: ignore[index]

    def test_public_state_invariants(self) -> None:
        puzzle = self._create_sample_3x3_puzzle()
        state = create_initial_public_state(puzzle)

        # 1. Unsorted character names
        reversed_chars = tuple(reversed(state.characters))
        with pytest.raises(ValueError, match="Characters must be sorted alphabetically"):
            PublicState(
                grid_size=3,
                characters=reversed_chars,
                cards=state.cards,
                known_statuses=state.known_statuses,
                revealed_clues=state.revealed_clues,
                revealed_cells=state.revealed_cells,
            )

        # 2. Key mismatch in cards
        bad_cards = dict(state.cards)
        bad_cards[CellId("A1")] = state.cards[CellId("B1")]
        with pytest.raises(ValueError, match="does not match card.cell"):
            PublicState(
                grid_size=3,
                characters=state.characters,
                cards=bad_cards,
                known_statuses=state.known_statuses,
                revealed_clues=state.revealed_clues,
                revealed_cells=state.revealed_cells,
            )

        # 3. Known statuses mismatch with revealed_cells
        bad_known = dict(state.known_statuses)
        del bad_known[CellId("A1")]
        with pytest.raises(ValueError, match="Revealed card at A1 is not in known_statuses"):
            PublicState(
                grid_size=3,
                characters=state.characters,
                cards=state.cards,
                known_statuses=bad_known,
                revealed_clues=state.revealed_clues,
                revealed_cells=state.revealed_cells,
            )

        # 4. Revealed clue count or owner mismatch
        bad_clues = state.revealed_clues[:1]
        with pytest.raises(ValueError, match="revealed_clues count"):
            PublicState(
                grid_size=3,
                characters=state.characters,
                cards=state.cards,
                known_statuses=state.known_statuses,
                revealed_clues=bad_clues,
                revealed_cells=state.revealed_cells,
            )

        # 5. Revealed clues not sorted by owner cell
        reversed_clues = tuple(reversed(state.revealed_clues))
        with pytest.raises(ValueError, match="revealed_clues must be ordered deterministically"):
            PublicState(
                grid_size=3,
                characters=state.characters,
                cards=state.cards,
                known_statuses=state.known_statuses,
                revealed_clues=reversed_clues,
                revealed_cells=state.revealed_cells,
            )


