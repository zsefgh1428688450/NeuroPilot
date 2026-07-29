from __future__ import annotations

import operator
from time import perf_counter
from typing import Annotated, Literal, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from app.agents.coach_agent import CoachAgent
from app.agents.task_agent import TaskAnalyst
from app.cognitive import CognitiveModel
from app.domain.models import (
    CognitiveSlot,
    EvaluationResult,
    OptimizeRequest,
    OptimizeResponse,
    SchedulePlan,
    TaskProfile,
    TraceStep,
)
from app.optimization import CognitiveScheduler, ScheduleEvaluator


class NeuroState(TypedDict, total=False):
    request: OptimizeRequest
    forecast: list[CognitiveSlot]
    task_profiles: list[TaskProfile]
    schedule: SchedulePlan
    evaluation: EvaluationResult
    coach_summary: str
    attempts: int
    trace: Annotated[list[TraceStep], operator.add]


class NeuroPilotWorkflow:
    """LangGraph workflow with deterministic agents and human approval at the API boundary."""

    def __init__(self) -> None:
        self.cognitive_model = CognitiveModel()
        self.task_analyst = TaskAnalyst()
        self.scheduler = CognitiveScheduler()
        self.evaluator = ScheduleEvaluator()
        self.coach = CoachAgent()
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(NeuroState)
        builder.add_node("cognitive_analyst", self._cognitive_node)
        builder.add_node("task_analyst", self._task_node)
        builder.add_node("planner", self._planner_node)
        builder.add_node("reviewer", self._review_node)
        builder.add_node("coach", self._coach_node)

        builder.add_edge(START, "cognitive_analyst")
        builder.add_edge(START, "task_analyst")
        builder.add_edge("cognitive_analyst", "planner")
        builder.add_edge("task_analyst", "planner")
        builder.add_edge("planner", "reviewer")
        builder.add_conditional_edges(
            "reviewer",
            self._review_route,
            {"retry": "planner", "coach": "coach"},
        )
        builder.add_edge("coach", END)
        return builder.compile()

    def run(self, request: OptimizeRequest) -> OptimizeResponse:
        final_state = self.graph.invoke({"request": request, "attempts": 0, "trace": []})
        return OptimizeResponse(
            run_id=str(uuid4()),
            target_date=request.target_date,
            forecast=final_state["forecast"],
            task_profiles=final_state["task_profiles"],
            schedule=final_state["schedule"],
            evaluation=final_state["evaluation"],
            coach_summary=final_state["coach_summary"],
            trace=final_state["trace"],
        )

    def _cognitive_node(self, state: NeuroState) -> dict:
        started = perf_counter()
        request = state["request"]
        forecast = self.cognitive_model.forecast(
            request.target_date, request.user, request.signals, request.calendar
        )
        peak_slots = [slot for slot in forecast if slot.label == "peak"]
        peak_window = (
            f"{peak_slots[0].start.strftime('%H:%M')}–{peak_slots[-1].end.strftime('%H:%M')}"
            if peak_slots
            else "No distinct peak"
        )
        trace = TraceStep(
            agent="Cognitive Analyst",
            status="completed",
            summary=f"Forecast {len(forecast)} half-hour cognitive states; peak window: {peak_window}.",
            details={"peak_window": peak_window, "model": "explainable_parameterized_baseline"},
            duration_ms=round((perf_counter() - started) * 1000),
        )
        return {"forecast": forecast, "trace": [trace]}

    def _task_node(self, state: NeuroState) -> dict:
        started = perf_counter()
        profiles = self.task_analyst.analyze(state["request"].tasks)
        trace = TraceStep(
            agent="Task Analyst",
            status="completed",
            summary=f"Classified {len(profiles)} tasks into cognitive demand profiles.",
            details={"categories": {profile.title: profile.category for profile in profiles}},
            duration_ms=round((perf_counter() - started) * 1000),
        )
        return {"task_profiles": profiles, "trace": [trace]}

    def _planner_node(self, state: NeuroState) -> dict:
        started = perf_counter()
        attempts = state.get("attempts", 0) + 1
        request = state["request"]
        plan = self.scheduler.schedule(
            request.tasks,
            state["task_profiles"],
            state["forecast"],
            request.calendar,
            strictness=1.0 + (attempts - 1) * 0.25,
        )
        trace = TraceStep(
            agent="Planning Agent",
            status="completed" if not plan.unscheduled_task_ids else "warning",
            summary=f"Placed {len(plan.recommendations)} of {len(request.tasks)} tasks on attempt {attempts}.",
            details={
                "attempt": attempts,
                "fit_scores": {item.title: item.fit_score for item in plan.recommendations},
                "unscheduled_task_ids": plan.unscheduled_task_ids,
            },
            duration_ms=round((perf_counter() - started) * 1000),
        )
        return {"schedule": plan, "attempts": attempts, "trace": [trace]}

    def _review_node(self, state: NeuroState) -> dict:
        started = perf_counter()
        request = state["request"]
        evaluation = self.evaluator.evaluate(
            state["schedule"], request.tasks, state["task_profiles"], request.calendar
        )
        trace = TraceStep(
            agent="Safety Reviewer",
            status="completed" if evaluation.approved else "warning",
            summary=(
                "Schedule passed deterministic safety checks."
                if evaluation.approved
                else "Schedule needs another planning pass."
            ),
            details={"issues": evaluation.issues, "warnings": evaluation.warnings},
            duration_ms=round((perf_counter() - started) * 1000),
        )
        return {"evaluation": evaluation, "trace": [trace]}

    @staticmethod
    def _review_route(state: NeuroState) -> Literal["retry", "coach"]:
        if not state["evaluation"].approved and state.get("attempts", 0) < 2:
            return "retry"
        return "coach"

    def _coach_node(self, state: NeuroState) -> dict:
        started = perf_counter()
        summary = self.coach.explain(
            state["request"].user, state["schedule"], state["evaluation"]
        )
        trace = TraceStep(
            agent="Cognitive Coach",
            status="completed",
            summary="Generated an explainable, approval-gated recommendation.",
            details={"human_approval_required": True},
            duration_ms=round((perf_counter() - started) * 1000),
        )
        return {"coach_summary": summary, "trace": [trace]}
