"""Solver module for Griductive.

Contains CNF encoding, DPLL SAT solver, public knowledge base, and logical entailment.
"""

from griductive.solver.cnf import (
    AuxAllocator,
    CNFFormula,
    PrimaryVarMap,
    build_cnf_from_public_state,
    encode_at_least,
    encode_at_most,
    encode_different,
    encode_exactly,
    encode_fact,
    encode_known_status,
    encode_parity,
    encode_same,
)
from griductive.solver.dpll import (
    DpllMetrics,
    SatResult,
    solve_dpll,
)
from griductive.solver.kb import (
    KnowledgeBase,
    KnowledgeBaseBuilder,
    build_knowledge_base,
)
from griductive.solver.logic import (
    CellClassification,
    LogicAgent,
    ProofReport,
    ProofService,
    SatQueryRecord,
)

__all__ = [
    # CNF
    "PrimaryVarMap",
    "AuxAllocator",
    "CNFFormula",
    "encode_fact",
    "encode_same",
    "encode_different",
    "encode_known_status",
    "encode_at_most",
    "encode_at_least",
    "encode_exactly",
    "encode_parity",
    "build_cnf_from_public_state",
    # DPLL
    "SatResult",
    "DpllMetrics",
    "solve_dpll",
    # KB
    "KnowledgeBase",
    "KnowledgeBaseBuilder",
    "build_knowledge_base",
    # Logic
    "SatQueryRecord",
    "CellClassification",
    "ProofReport",
    "ProofService",
    "LogicAgent",
]
