"""Public knowledge base construction (T10).

Builds immutable, deterministic SAT knowledge bases exclusively from public state
(revealed clues and publicly known verdicts). Ensures strict isolation from private
puzzle models and hidden labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from griductive.domain.model import CellId, PublicState, Status
from griductive.solver.cnf import CNFFormula, PrimaryVarMap, build_cnf_from_public_state


@dataclass(frozen=True)
class KnowledgeBase:
    """Immutable representation of the public knowledge base at a given state revision.

    Attributes:
        formula: Compiled immutable CNFFormula containing status units and clue clauses.
        revision: Public state revision number at build time.
        active_clue_ids: Deterministic sequence of active (revealed) clue IDs.
        known_statuses: Immutable mapping of public known statuses.
    """

    formula: CNFFormula
    revision: int
    active_clue_ids: tuple[str, ...]
    known_statuses: Mapping[CellId, Status]

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_clue_ids", tuple(self.active_clue_ids))
        object.__setattr__(
            self, "known_statuses", MappingProxyType(dict(self.known_statuses))
        )

    @property
    def num_primary(self) -> int:
        """Number of primary grid variables."""
        return self.formula.num_primary

    @property
    def num_aux(self) -> int:
        """Number of auxiliary variables allocated across all active clues."""
        return self.formula.num_aux

    @property
    def num_vars(self) -> int:
        """Total number of declared variables (primary + auxiliary)."""
        return self.formula.num_vars

    @property
    def num_clauses(self) -> int:
        """Total number of clauses in the knowledge base."""
        return self.formula.num_clauses

    @property
    def clauses(self) -> tuple[tuple[int, ...], ...]:
        """All CNF clauses in the knowledge base."""
        return self.formula.clauses

    @property
    def primary_map(self) -> PrimaryVarMap:
        """Deterministic mapping between CellIds and primary variable integers."""
        return self.formula.primary_map


class KnowledgeBaseBuilder:
    """Builder for constructing public knowledge bases from public snapshots."""

    @staticmethod
    def build(state: PublicState) -> KnowledgeBase:
        """Construct an immutable KnowledgeBase from the given PublicState.

        Guarantees:
        - Only revealed clues and public known statuses are included.
        - Primary variables, auxiliary variables, and clauses follow deterministic ordering.
        - Formula is completely isolated from hidden puzzle solutions or unrevealed cards.
        """
        formula = build_cnf_from_public_state(state)
        active_ids = tuple(clue.clue_id for clue in state.revealed_clues)
        return KnowledgeBase(
            formula=formula,
            revision=state.revision,
            active_clue_ids=active_ids,
            known_statuses=state.known_statuses,
        )


def build_knowledge_base(state: PublicState) -> KnowledgeBase:
    """Convenience function to build a KnowledgeBase from a PublicState."""
    return KnowledgeBaseBuilder.build(state)
