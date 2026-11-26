"""Presentation of verdicts, hints, and solver results from the game controller."""

from __future__ import annotations

from dataclasses import replace

from griductive.domain.model import CellId, Status
from griductive.game.controller import (
    AutoSolveReport,
    AutoSolveStatus,
    CallResult,
    DeductionStep,
    Hint,
    RejectionReason,
)
from griductive.solver.cnf import PrimaryVarMap
from griductive.solver.dpll import DpllMetrics
from griductive.solver.logic import SatQueryRecord
from griductive.ui import formatting
from griductive.ui.theme import AUTO_SOLVE_LABEL, CHECK_BOARD_LABEL, LOGS_LABEL


class _SolverActions:
    """Gameplay commands used by GriductiveApp."""

    def call_criminal(self) -> CallResult:
        """Submit a manual call that the selected cell is CRIMINAL."""
        return self._make_call(Status.CRIMINAL)

    def call_innocent(self) -> CallResult:
        """Submit a manual call that the selected cell is INNOCENT."""
        return self._make_call(Status.INNOCENT)

    def _make_call(self, proposed_status: Status) -> CallResult:
        """Handle a manual call submission with proper acceptance and rejection feedback."""
        self.stop_auto_solve()
        self.clear_highlights()
        if self.selected_cell is None:
            self.last_rejection_reason = RejectionReason.INVALID_CELL
            self.status_message = "Select a card first."
            self.status_subtitle = "Choose a face-down card to make a call."
            res = CallResult(
                cell=CellId.from_coords(1, 1),
                proposed_status=proposed_status,
                accepted=False,
                rejection_reason=RejectionReason.INVALID_CELL,
                message="No cell selected.",
            )
            self.last_call_result = res
            return res

        target = self.selected_cell
        res = self.controller.make_call(target, proposed_status)
        self.last_call_result = res
        if res.classification is not None:
            for query in res.classification.queries:
                self._log_sat_query(query)
        if res.rejection_reason == RejectionReason.INCONSISTENT:
            self._add_log("sat", "Public Clues", "UNSAT")

        if res.accepted:
            self.last_rejection_reason = None
            verdict = proposed_status.value.lower()
            self.status_message = f"{target} is {verdict}. New clue revealed."
            clue = res.revealed_clue
            self.status_subtitle = formatting.format_clue_text(clue, self.controller.public_state) if clue else ""
            detail = f"{verdict.title()}, clue {clue.clue_id}" if clue else verdict.title()
            self._add_log("action", f"Revealed {target}", detail)
            if self.controller.is_solved:
                self.status_message = "Puzzle solved."
                self._add_log("deduction", "Puzzle Solved", "Every card was revealed without guessing.")
        else:
            reason = res.rejection_reason
            self.last_rejection_reason = reason
            if reason == RejectionReason.NOT_PROVABLE:
                self.status_message = "Not enough evidence yet."
                self.status_subtitle = f"Both verdicts are still possible for {target}. Read another clue or use Hint."
            elif reason == RejectionReason.CONTRADICTED:
                self.status_message = "The clues prove the opposite verdict."
                self.status_subtitle = f"Review the clues that refer to {target}."
            elif reason == RejectionReason.INCONSISTENT:
                self.status_message = "The revealed clues conflict."
                self.status_subtitle = f"Use {CHECK_BOARD_LABEL} to inspect the public clues."
            else:
                self.status_message = "Verdict not accepted."
                self.status_subtitle = res.message or ""
            if reason is not None:
                self._add_log("info", reason.value, self.status_subtitle)

        if self.root is not None:
            self._refresh_ui()

        return res

    def _log_sat_query(self, query: SatQueryRecord) -> None:
        variables = PrimaryVarMap(self.controller.grid_size)
        assumptions = []
        for literal in query.assumptions:
            cell = variables.var_to_cell(abs(literal))
            assumptions.append(f"{cell} = {'Criminal' if literal > 0 else 'Innocent'}")
        self._add_log("sat", ", ".join(assumptions) or "Public Clues",
                      "SAT" if query.is_sat else "UNSAT")

    def check_board(self, claim: AutoSolveStatus | None = None) -> AutoSolveStatus | None:
        """Verify the player's board claim against public evidence only."""
        self.stop_auto_solve()
        self.clear_highlights()
        proof = self.controller.assess_board()
        self._log_sat_query(proof.base_query)
        for classification in proof.classifications.values():
            for query in classification.queries:
                self._log_sat_query(query)
        if not proof.base_consistent:
            status = AutoSolveStatus.INCONSISTENT
            detail = "No assignment satisfies the revealed clues and known statuses."
        elif proof.first_forced_cell is not None:
            status = None
            detail = "Select Hint to see the relevant clues."
        elif self.controller.is_solved:
            status = AutoSolveStatus.SOLVED
            detail = "All cards have been revealed and the public clues agree."
        else:
            status = AutoSolveStatus.STALLED
            detail = "The revealed clues agree, but no remaining verdict is forced."
        label = {
            AutoSolveStatus.INCONSISTENT: "The revealed clues conflict.",
            AutoSolveStatus.SOLVED: "Puzzle solved.",
            AutoSolveStatus.STALLED: "No provable move remains.",
        }.get(status, "A provable move remains.")
        prefix = "" if claim is None else ("Correct. " if claim == status else "Claim not supported. ")
        self.status_message = prefix + label
        self.status_subtitle = detail
        self._add_log("deduction", CHECK_BOARD_LABEL, f"{label} {detail}")
        if self.root is not None:
            self._refresh_ui()
        return status

    def hint(self) -> Hint:
        """Start with public evidence, without selecting or flipping the target."""
        self.stop_auto_solve()
        self.clear_highlights()
        self.selected_cell = None
        hint = self.controller.hint()
        self.last_hint = hint
        if hint.classification is not None:
            for query in hint.classification.queries:
                self._log_sat_query(query)

        if not hint.base_consistent:
            self.status_message = "The revealed clues conflict."
            self._add_log("sat", "Public Clues", "UNSAT")
        elif hint.has_forced_cell:
            clues = self.controller.public_state.revealed_clues
            self.hint_clue_cells = frozenset(
                clue.owner for clue in clues if clue.clue_id in hint.relevant_clue_ids
            )
            evidence = ", ".join(str(cell) for cell in sorted(self.hint_clue_cells))
            self.status_message = (
                f"Read the evidence on {evidence}. Select Reveal for the next person."
                if evidence else "Select Reveal to see who you can identify next."
            )
            self._add_log("deduction", "Hint", f"Evidence on {evidence}" if evidence else "Next move is provable")
        else:
            self.status_message = "Puzzle solved." if self.controller.is_solved else "No provable move remains."
        self.status_subtitle = ""
        if self.root is not None:
            self._refresh_ui()
            if self.hint_clue_cells:
                self._scroll_to_hint(min(self.hint_clue_cells))
        return hint

    def _advance_hint(self) -> None:
        """Cycle from evidence to the target and then clear the spotlight."""
        if self.hinted_cell is not None:
            self.status_message = "Spotlight cleared."
            self.status_subtitle = "Continue investigating the revealed clues."
            self.selected_cell = None
            self.clear_highlights()
        elif self.last_hint and self.last_hint.has_forced_cell and self.hint_clue_cells:
            self._reveal_hint_target()
        else:
            hint = self.hint()
            if hint.has_forced_cell and not self.hint_clue_cells:
                self._reveal_hint_target()

    def _reveal_hint_target(self) -> None:
        hint = self.last_hint
        if hint is None or hint.cell is None:
            return
        self.hinted_cell = hint.cell
        person = self.controller.public_state.cards[hint.cell].character
        self.status_message = f"Next person: {person.name} ({hint.cell}). Select the card to make your call."
        self.status_subtitle = "Use the highlighted clues to decide the verdict."
        if self.root is not None:
            self._refresh_ui()
            self._scroll_to_hint(hint.cell)

    def step(self) -> DeductionStep | None:
        """Execute a single deterministic deduction step."""
        self.stop_auto_solve()
        self.clear_highlights()
        step_res = self.controller.step()
        if step_res is not None:
            self._log_deduction_step(step_res)
            self.status_message = (
                f"Step {step_res.step_number} · {step_res.target_cell} is "
                f"{step_res.target_verdict.value.lower()}."
            )
            self.status_subtitle = formatting.format_clue_text(step_res.revealed_clue, self.controller.public_state)
            self.selected_cell = step_res.target_cell
            if self.controller.is_solved:
                self.status_message = "Puzzle solved."
                self.status_subtitle = "Every card was revealed without guessing."
                self._add_log("deduction", "Complete", "Puzzle solved successfully")
        else:
            if self.controller.is_solved:
                self.status_message = "The puzzle is already solved."
                self.status_subtitle = "All character cards have been exposed."
            else:
                terminal_report = self.controller.auto_solve()
                self.last_auto_solve_report = terminal_report
                if terminal_report.status == AutoSolveStatus.INCONSISTENT:
                    self.status_message = "The revealed clues conflict."
                    self.status_subtitle = "No assignment fits the revealed clues and known verdicts."
                else:
                    self.status_message = "No provable move remains."
                    self.status_subtitle = "The current clues leave more than one possibility."
            self._add_log("info", "Step Result", self.status_message)

        if self.root is not None:
            self._refresh_ui()

        return step_res

    def auto_solve(self, max_steps: int | None = None) -> AutoSolveReport:
        """Run the full deduction loop until solved, stalled, or inconsistent."""
        self.stop_auto_solve()
        self.clear_highlights()
        report = self.controller.auto_solve(max_steps=max_steps)
        self.last_auto_solve_report = report

        for step in report.steps:
            self._log_deduction_step(step)
        self._show_auto_solve_result(report)

        if self.root is not None:
            self._refresh_ui()

        return report

    def _log_deduction_step(self, step: DeductionStep) -> None:
        """Group the evidence used and the newly revealed clue around each step."""
        active_clues = ", ".join(step.active_clue_ids) or "None"
        self._add_log("deduction", f"Step {step.step_number}",
                      f"Active Clues: {active_clues}")
        for query in step.all_queries:
            self._log_sat_query(query)
        verdict = step.target_verdict.value.lower()
        self._add_log("deduction", f"{step.target_cell} is {verdict}",
                      f"Revealed clue {step.revealed_clue_id}.")

    def _show_auto_solve_result(self, report: AutoSolveReport) -> None:
        """Use the same player-facing result for animated and immediate runs."""
        count = report.total_steps
        steps = f"{count} {'step' if count == 1 else 'steps'}"
        result = {
            AutoSolveStatus.SOLVED: f"Solved in {steps}.",
            AutoSolveStatus.STALLED: "No provable move remains.",
            AutoSolveStatus.INCONSISTENT: "The revealed clues conflict.",
            AutoSolveStatus.ALREADY_SOLVED: "The puzzle is already solved.",
            AutoSolveStatus.STEP_LIMIT_REACHED: f"Paused after {steps}.",
        }[report.status]
        self.status_message = f"{AUTO_SOLVE_LABEL} · {result}"
        self.status_subtitle = f"Steps: {count} · SAT Queries: {report.total_sat_calls}"
        self._add_log("deduction", AUTO_SOLVE_LABEL, f"{result} {self.status_subtitle}.")

    def stop_auto_solve(self) -> None:
        """Cancel pending frames; invalidate callbacks across restart/load/pause."""
        self.auto_running = False
        self._auto_generation += 1
        if self._auto_after_id is not None and self.root is not None:
            self.root.after_cancel(self._auto_after_id)
        self._auto_after_id = None
        for button in getattr(self, "_auto_buttons", (getattr(self, "_auto_button", None),)):
            if button is None:
                continue
            button.config(text=AUTO_SOLVE_LABEL)

    def toggle_auto_solve(self) -> None:
        """Animate actual public reveals, one proven card per timer callback."""
        if self.auto_running:
            self.stop_auto_solve()
            self.status_message = f"{AUTO_SOLVE_LABEL} paused."
            self._refresh_ui()
            return
        if self.root is None:
            return
        self.stop_auto_solve()
        self.clear_highlights()
        self.hinted_cell = None
        self.last_rejection_reason = None
        self.last_hint = None
        self.last_auto_solve_report = None
        self._animation_reports = []
        self.auto_running = True
        for button in getattr(self, "_auto_buttons", (self._auto_button,)):
            button.config(text="Pause")
        generation = self._auto_generation
        self.status_message = f"{AUTO_SOLVE_LABEL} is revealing proven cards."
        self._refresh_ui()
        self._auto_after_id = self.root.after(
            100, lambda: self._animate_next_card(generation)
        )

    def _animate_next_card(self, generation: int) -> None:
        """Never pre-solve hidden cards; each frame advances the controller once."""
        if not self.auto_running or generation != self._auto_generation:
            return
        self._auto_after_id = None
        try:
            report = self.controller.auto_solve(max_steps=1)
        except Exception as exc:
            self.stop_auto_solve()
            self.status_message = f"{AUTO_SOLVE_LABEL} stopped. See {LOGS_LABEL} for details."
            self.status_subtitle = str(exc)
            self._add_log("error", AUTO_SOLVE_LABEL, str(exc))
            self._refresh_ui()
            return
        prior_steps = sum(r.total_steps for r in self._animation_reports)
        report = replace(report, steps=tuple(
            replace(step, step_number=prior_steps + index)
            for index, step in enumerate(report.steps, start=1)
        ))
        self._animation_reports.append(report)
        for step in report.steps:
            self._log_deduction_step(step)
            self.selected_cell = step.target_cell
            self.status_message = f"{AUTO_SOLVE_LABEL} · {step.target_cell} is {step.target_verdict.value.lower()}."
            self.status_subtitle = formatting.format_clue_text(step.revealed_clue, self.controller.public_state)
        self.last_auto_solve_report = replace(
            report,
            steps=tuple(s for r in self._animation_reports for s in r.steps),
            total_steps=sum(r.total_steps for r in self._animation_reports),
            total_sat_calls=sum(r.total_sat_calls for r in self._animation_reports),
            aggregate_metrics=DpllMetrics(
                sum(r.aggregate_metrics.decisions for r in self._animation_reports),
                sum(r.aggregate_metrics.propagations for r in self._animation_reports),
                sum(r.aggregate_metrics.backtracks for r in self._animation_reports),
                sum(r.aggregate_metrics.runtime for r in self._animation_reports),
            ),
        )
        if report.status == AutoSolveStatus.STEP_LIMIT_REACHED:
            assert self.root is not None
            self._auto_after_id = self.root.after(
                self.animation_delay_ms, lambda: self._animate_next_card(generation)
            )
        else:
            self.stop_auto_solve()
            if report.status in (AutoSolveStatus.STALLED, AutoSolveStatus.INCONSISTENT):
                self._add_log("sat", "Public Clues",
                              "UNSAT" if report.status == AutoSolveStatus.INCONSISTENT else "SAT")
            self._show_auto_solve_result(self.last_auto_solve_report)
        self._refresh_ui()
