"""CNF formula representation, variable mappings, and clue encoders.

Allocates deterministic primary variables in row-major order (1..N^2),
allocates fresh auxiliary variables strictly above the primary range,
and compiles revealed public knowledge, binary clues, cardinality clues
(AT_MOST, AT_LEAST, EXACTLY), and parity clues (PARITY with Tseitin XOR chain)
into CNF clauses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from griductive.domain.model import (
    AtLeastClue,
    AtMostClue,
    CellId,
    DifferentClue,
    ExactlyClue,
    FactClue,
    Parity,
    ParityClue,
    PublicState,
    SameClue,
    Status,
)
from griductive.domain.regions import resolve_region


class PrimaryVarMap:
    """Deterministic bijection between CellId coordinates and 1-indexed primary variable integers.

    Primary variables are numbered in row-major order (1..N^2):
    Row 1: A1 -> 1, B1 -> 2, ..., [Col_N]1 -> N
    Row 2: A2 -> N+1, B2 -> N+2, ...
    Row N: AN -> N*(N-1)+1, ..., [Col_N]N -> N^2
    """

    def __init__(self, grid_size: int) -> None:
        """Initialize PrimaryVarMap for an N x N grid."""
        if grid_size < 1:
            raise ValueError(f"grid_size must be >= 1, got {grid_size}")
        self._grid_size: int = grid_size
        self._num_primary: int = grid_size * grid_size

    @property
    def grid_size(self) -> int:
        """Size of the N x N grid."""
        return self._grid_size

    @property
    def num_primary(self) -> int:
        """Total number of primary variables (N^2)."""
        return self._num_primary

    def cell_to_var(self, cell: CellId) -> int:
        """Convert a CellId to its deterministic 1-indexed primary variable integer."""
        if not cell.is_valid_for(self._grid_size):
            raise ValueError(
                f"Cell {cell.name} is not valid for grid_size {self._grid_size}"
            )
        return cell.to_index(self._grid_size) + 1

    def var_to_cell(self, var: int) -> CellId:
        """Convert a 1-indexed primary variable integer back to its CellId."""
        if var < 1 or var > self._num_primary:
            raise ValueError(
                f"Primary variable {var} out of range (1..{self._num_primary})"
            )
        return CellId.from_index(var - 1, self._grid_size)

    def __repr__(self) -> str:
        return f"PrimaryVarMap(grid_size={self._grid_size}, num_primary={self._num_primary})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PrimaryVarMap):
            return False
        return self._grid_size == other._grid_size


class AuxAllocator:
    """Allocator for fresh auxiliary SAT variables starting strictly above the primary range.

    Guarantees auxiliary variable integers never overlap with primary variable integers.
    """

    def __init__(self, start_after: int | PrimaryVarMap) -> None:
        """Initialize allocator starting after the given primary variable count or map."""
        if isinstance(start_after, PrimaryVarMap):
            base = start_after.num_primary
        elif isinstance(start_after, int):
            if start_after < 0:
                raise ValueError(f"start_after must be non-negative, got {start_after}")
            base = start_after
        else:
            raise TypeError(
                f"start_after must be int or PrimaryVarMap, got {type(start_after).__name__}"
            )
        self._base: int = base
        self._current: int = base

    @property
    def num_aux(self) -> int:
        """Number of auxiliary variables allocated so far."""
        return self._current - self._base

    def fresh(self) -> int:
        """Allocate and return the next unused fresh auxiliary variable integer."""
        self._current += 1
        return self._current

    def __repr__(self) -> str:
        return f"AuxAllocator(base={self._base}, num_aux={self.num_aux})"


@dataclass(frozen=True)
class CNFFormula:
    """Immutable container for a CNF formula in DIMACS-like form.

    Each clause is a tuple of nonzero signed integers.
    Positive integers denote positive literals; negative integers denote negated literals.
    An empty clause () is a valid contradiction clause (always false).
    """

    clauses: tuple[tuple[int, ...], ...]
    primary_map: PrimaryVarMap
    num_aux: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.num_aux, bool) or not isinstance(self.num_aux, int):
            raise TypeError(f"num_aux must be an integer, got {type(self.num_aux).__name__}: {self.num_aux!r}")
        if self.num_aux < 0:
            raise ValueError(f"num_aux cannot be negative, got {self.num_aux}")

        max_var = self.num_vars
        normalized_clauses = []
        for clause in self.clauses:
            clause_lits = []
            for lit in clause:
                if isinstance(lit, bool) or not isinstance(lit, int):
                    raise TypeError(
                        f"Literal must be an integer (and not bool), got {type(lit).__name__}: {lit!r}"
                    )
                if lit == 0:
                    raise ValueError("Clause cannot contain literal 0")
                if abs(lit) > max_var:
                    raise ValueError(
                        f"Literal variable ID {abs(lit)} exceeds declared total variables {max_var}"
                    )
                clause_lits.append(lit)
            normalized_clauses.append(tuple(clause_lits))
        object.__setattr__(self, "clauses", tuple(normalized_clauses))

    @property
    def num_primary(self) -> int:
        """Number of primary grid variables."""
        return self.primary_map.num_primary

    @property
    def num_vars(self) -> int:
        """Total number of declared variables (primary + auxiliary)."""
        return self.num_primary + self.num_aux

    @property
    def num_clauses(self) -> int:
        """Number of clauses in the formula."""
        return len(self.clauses)


# ---------------------------------------------------------------------------
# Binary clue encoders (T06)
# ---------------------------------------------------------------------------


def encode_fact(
    clue: FactClue,
    pmap: PrimaryVarMap,
    aux: AuxAllocator | None = None,
) -> tuple[tuple[int, ...], ...]:
    """Encode FACT(person, status) into CNF.

    FACT(person, CRIMINAL): one unit clause (+var,)
    FACT(person, INNOCENT): one unit clause (-var,)
    Uses zero auxiliary variables.
    """
    var = pmap.cell_to_var(clue.target)
    if clue.status == Status.CRIMINAL:
        return ((var,),)
    return ((-var,),)


def encode_same(
    clue: SameClue,
    pmap: PrimaryVarMap,
    aux: AuxAllocator | None = None,
) -> tuple[tuple[int, ...], ...]:
    """Encode SAME(person_a, person_b) into CNF.

    Equivalent to (a <-> b): (¬a ∨ b) ∧ (a ∨ ¬b).
    Uses zero auxiliary variables.
    """
    va = pmap.cell_to_var(clue.person_a)
    vb = pmap.cell_to_var(clue.person_b)
    return ((-va, vb), (va, -vb))


def encode_different(
    clue: DifferentClue,
    pmap: PrimaryVarMap,
    aux: AuxAllocator | None = None,
) -> tuple[tuple[int, ...], ...]:
    """Encode DIFFERENT(person_a, person_b) into CNF.

    Equivalent to (a XOR b): (a ∨ b) ∧ (¬a ∨ ¬b).
    Uses zero auxiliary variables.
    """
    va = pmap.cell_to_var(clue.person_a)
    vb = pmap.cell_to_var(clue.person_b)
    return ((va, vb), (-va, -vb))


def encode_known_status(
    cell: CellId,
    status: Status,
    pmap: PrimaryVarMap,
) -> tuple[tuple[int, ...], ...]:
    """Encode a known public card status into a unit CNF clause.

    CRIMINAL -> (+var,)
    INNOCENT -> (-var,)
    """
    var = pmap.cell_to_var(cell)
    if status == Status.CRIMINAL:
        return ((var,),)
    return ((-var,),)


# ---------------------------------------------------------------------------
# Cardinality encoders (T07) — Sinz sequential counter
# ---------------------------------------------------------------------------


def _encode_at_most_literals(
    literals: Sequence[int],
    k: int,
    aux: AuxAllocator,
) -> tuple[tuple[int, ...], ...]:
    """Encode at-most-k over an ordered sequence of literals (Sinz 2005 sequential counter).

    Boundary cases (zero auxiliary variables):
    - k == 0: all literals must be false → unit clause (-lit,) for each lit.
    - k >= n: tautology, any count ≤ n is trivially satisfied → 0 clauses.

    Interior case (0 < k < n):
    Allocates n × k fresh auxiliary variables s[i][j] for i ∈ 0..n−1, j ∈ 0..k−1.
    s[i][j] represents "at least j+1 of literals[0..i] are true."

    Clause count: 1 + (n−1) × (2k+1)
    """
    n = len(literals)
    if k == 0:
        return tuple((-lit,) for lit in literals)
    if k >= n:
        return ()

    # Allocate n * k fresh auxiliary variables: s[i][j] for i in 0..n-1, j in 0..k-1
    s = [[aux.fresh() for _ in range(k)] for _ in range(n)]
    clauses: list[tuple[int, ...]] = []

    # i = 0: x[0] -> s[0][0]
    clauses.append((-literals[0], s[0][0]))

    for i in range(1, n):
        # x[i] -> s[i][0]  (any criminal starts the counter)
        clauses.append((-literals[i], s[i][0]))
        # s[i-1][0] -> s[i][0]  (carry counter upward)
        clauses.append((-s[i - 1][0], s[i][0]))

        for j in range(1, k):
            # x[i] ∧ s[i-1][j-1] -> s[i][j]  (advance counter)
            clauses.append((-literals[i], -s[i - 1][j - 1], s[i][j]))
            # s[i-1][j] -> s[i][j]  (carry higher counter upward)
            clauses.append((-s[i - 1][j], s[i][j]))

        # AT_MOST constraint: once counter reached k (s[i-1][k-1] true), x[i] must be false
        clauses.append((-s[i - 1][k - 1], -literals[i]))

    return tuple(clauses)


def encode_at_most(
    clue: AtMostClue,
    pmap: PrimaryVarMap,
    aux: AuxAllocator,
    grid_size: int,
) -> tuple[tuple[int, ...], ...]:
    """Encode AT_MOST(k, region) using sequential counter.

    k=0: unit clauses forcing all cells innocent.
    k=n: empty (tautology).
    0<k<n: Sinz sequential counter with n×k fresh auxiliaries.
    """
    if isinstance(clue.k, bool) or not isinstance(clue.k, int):
        raise TypeError(
            f"Cardinality k must be an integer, got {type(clue.k).__name__}: {clue.k!r}"
        )
    cells = resolve_region(clue.region, grid_size)
    n = len(cells)
    if clue.k < 0 or clue.k > n:
        raise ValueError(
            f"k={clue.k} out of bounds for region of size {n} (0..{n})"
        )
    lits = tuple(pmap.cell_to_var(c) for c in cells)
    return _encode_at_most_literals(lits, clue.k, aux)


def encode_at_least(
    clue: AtLeastClue,
    pmap: PrimaryVarMap,
    aux: AuxAllocator,
    grid_size: int,
) -> tuple[tuple[int, ...], ...]:
    """Encode AT_LEAST(k, region) as AT_MOST(n−k) over negated literals.

    AT_LEAST(k, [x₀..xₙ₋₁]) ≡ AT_MOST(n−k, [¬x₀..¬xₙ₋₁]).
    Auxiliary count: n × (n−k).
    """
    if isinstance(clue.k, bool) or not isinstance(clue.k, int):
        raise TypeError(
            f"Cardinality k must be an integer, got {type(clue.k).__name__}: {clue.k!r}"
        )
    cells = resolve_region(clue.region, grid_size)
    n = len(cells)
    if clue.k < 0 or clue.k > n:
        raise ValueError(
            f"k={clue.k} out of bounds for region of size {n} (0..{n})"
        )
    neg_lits = tuple(-pmap.cell_to_var(c) for c in cells)
    return _encode_at_most_literals(neg_lits, n - clue.k, aux)


def encode_exactly(
    clue: ExactlyClue,
    pmap: PrimaryVarMap,
    aux: AuxAllocator,
    grid_size: int,
) -> tuple[tuple[int, ...], ...]:
    """Encode EXACTLY(k, region) as AT_MOST(k) ∧ AT_LEAST(k).

    Uses two independent sequential counters, each with their own fresh auxiliary
    variables. Total auxiliary count: n×k + n×(n−k).
    """
    if isinstance(clue.k, bool) or not isinstance(clue.k, int):
        raise TypeError(
            f"Cardinality k must be an integer, got {type(clue.k).__name__}: {clue.k!r}"
        )
    cells = resolve_region(clue.region, grid_size)
    n = len(cells)
    if clue.k < 0 or clue.k > n:
        raise ValueError(
            f"k={clue.k} out of bounds for region of size {n} (0..{n})"
        )
    pos_lits = tuple(pmap.cell_to_var(c) for c in cells)
    neg_lits = tuple(-lit for lit in pos_lits)
    at_most_clauses = _encode_at_most_literals(pos_lits, clue.k, aux)
    at_least_clauses = _encode_at_most_literals(neg_lits, n - clue.k, aux)
    return at_most_clauses + at_least_clauses


# ---------------------------------------------------------------------------
# Parity encoder (T08) — Tseitin XOR chain
# ---------------------------------------------------------------------------


def _encode_xor_gate(a: int, b: int, z: int) -> tuple[tuple[int, ...], ...]:
    """Encode z <-> (a XOR b) into 4 Tseitin CNF clauses.

    Forbidden truth-table rows (and the clause that blocks each):
      z=1, a=0, b=0  ->  (a,  b, -z)   i.e. ¬(¬a ∧ ¬b ∧ z)
      z=0, a=0, b=1  ->  (a, -b,  z)   i.e. ¬(¬a ∧  b ∧ ¬z)
      z=0, a=1, b=0  -> (-a,  b,  z)   i.e. ¬( a ∧ ¬b ∧ ¬z)
      z=1, a=1, b=1  -> (-a, -b, -z)   i.e. ¬( a ∧  b ∧  z)
    """
    return (
        (a, b, -z),
        (a, -b, z),
        (-a, b, z),
        (-a, -b, -z),
    )


def encode_parity(
    clue: ParityClue,
    pmap: PrimaryVarMap,
    aux: AuxAllocator,
    grid_size: int,
) -> tuple[tuple[int, ...], ...]:
    """Encode PARITY(region, EVEN|ODD) using a Tseitin XOR chain.

    Empty region (n=0):
    - EVEN: 0 clauses (tautology: 0 % 2 == 0 is always true).
    - ODD:  1 empty clause ((),) — UNSAT (0 % 2 != 1).

    Single cell (n=1), 0 auxiliaries:
    - EVEN: 1 negative unit clause (-x0,) — forces cell innocent.
    - ODD:  1 positive unit clause (+x0,) — forces cell criminal.

    General (n >= 2), n-1 auxiliaries p[0]..p[n-2]:
    - Gate 0: p[0] <-> (x0 XOR x1)                  — 4 Tseitin clauses
    - Gate i (i=1..n-2): p[i] <-> (p[i-1] XOR x_{i+1}) — 4 Tseitin clauses each
    - Parity unit clause on accumulated bit p[n-2]:
        EVEN: (-p[n-2],)   ODD: (+p[n-2],)
    - Total auxiliaries: exactly n - 1.
    - Total clauses: 4*(n-1) + 1.
    """
    if not isinstance(clue.parity, Parity):
        raise TypeError(
            f"clue.parity must be a Parity enum, got {type(clue.parity).__name__}: {clue.parity!r}"
        )

    cells = resolve_region(clue.region, grid_size)
    n = len(cells)

    # --- Empty region ---
    if n == 0:
        if clue.parity == Parity.EVEN:
            return ()
        return ((),)   # One empty clause = UNSAT

    lits = tuple(pmap.cell_to_var(c) for c in cells)

    # --- Single cell ---
    if n == 1:
        if clue.parity == Parity.EVEN:
            return ((-lits[0],),)
        return ((lits[0],),)

    # --- General n >= 2: Tseitin XOR chain ---
    # Allocate n-1 auxiliary variables p[0]..p[n-2]
    p = [aux.fresh() for _ in range(n - 1)]
    clauses: list[tuple[int, ...]] = []

    # First gate: p[0] <-> (lits[0] XOR lits[1])
    clauses.extend(_encode_xor_gate(lits[0], lits[1], p[0]))

    # Subsequent gates: p[i] <-> (p[i-1] XOR lits[i+1])
    for i in range(1, n - 1):
        clauses.extend(_encode_xor_gate(p[i - 1], lits[i + 1], p[i]))

    # Final parity constraint on the accumulated XOR bit
    if clue.parity == Parity.EVEN:
        clauses.append((-p[-1],))   # XOR of all must be 0 (even count)
    else:
        clauses.append((p[-1],))    # XOR of all must be 1 (odd count)

    return tuple(clauses)


# ---------------------------------------------------------------------------
# Public KB builder (T06–T08)
# ---------------------------------------------------------------------------


def build_cnf_from_public_state(state: PublicState) -> CNFFormula:
    """Build a CNFFormula from the current public game state.

    Collects unit clauses for all known statuses, and encodes all revealed
    clues: FACT, SAME, DIFFERENT (T06), AT_MOST, AT_LEAST, EXACTLY (T07),
    and PARITY (T08). Raises TypeError for unknown clue types.
    """
    pmap = PrimaryVarMap(state.grid_size)
    aux = AuxAllocator(pmap)
    clauses: list[tuple[int, ...]] = []

    # Known statuses — deterministic row-major order by cell
    for cell in sorted(state.known_statuses.keys()):
        status = state.known_statuses[cell]
        clauses.extend(encode_known_status(cell, status, pmap))

    # Revealed clues — in stable revealed_clues order (already row-major by owner)
    for clue in state.revealed_clues:
        if isinstance(clue, FactClue):
            clauses.extend(encode_fact(clue, pmap, aux))
        elif isinstance(clue, SameClue):
            clauses.extend(encode_same(clue, pmap, aux))
        elif isinstance(clue, DifferentClue):
            clauses.extend(encode_different(clue, pmap, aux))
        elif isinstance(clue, AtMostClue):
            clauses.extend(encode_at_most(clue, pmap, aux, state.grid_size))
        elif isinstance(clue, AtLeastClue):
            clauses.extend(encode_at_least(clue, pmap, aux, state.grid_size))
        elif isinstance(clue, ExactlyClue):
            clauses.extend(encode_exactly(clue, pmap, aux, state.grid_size))
        elif isinstance(clue, ParityClue):
            clauses.extend(encode_parity(clue, pmap, aux, state.grid_size))
        else:
            raise TypeError(
                f"Unknown clue type: {type(clue).__name__}"
            )

    return CNFFormula(
        clauses=tuple(clauses),
        primary_map=pmap,
        num_aux=aux.num_aux,
    )
