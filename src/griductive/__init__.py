"""Griductive Solver — Modular Monolith Architecture.

Modules:
- domain: Core entities, coordinates, clues, regions, and independent semantics.
- solver: CNF encoding, DPLL SAT solver, knowledge base, and logical entailment.
- game: Game engine (private truth), puzzle loader, and gameplay controller.
- analysis: Offline puzzle validation and benchmarking experiments.
- ui: Interactive graphical user interface.
"""

from griductive import analysis, domain, game, solver, ui

__all__ = [
    "domain",
    "solver",
    "game",
    "analysis",
    "ui",
]
