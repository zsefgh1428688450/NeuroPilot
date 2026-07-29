from __future__ import annotations

from app.domain.models import EvaluationResult, SchedulePlan, UserProfile


class CoachAgent:
    def explain(
        self,
        user: UserProfile,
        plan: SchedulePlan,
        evaluation: EvaluationResult,
    ) -> str:
        if not plan.recommendations:
            return "I could not find a safe open slot for the requested work. Keep the current calendar unchanged and widen the planning window."
        best = max(plan.recommendations, key=lambda item: item.fit_score)
        summary = (
            f"{user.name}, your strongest match is {best.title} at {best.start.strftime('%H:%M')} "
            f"with a {best.fit_score:.0%} cognitive-fit score. "
            "The plan protects higher-capacity windows for demanding work and leaves lower-load work for steadier periods. "
        )
        if evaluation.warnings:
            summary += f"One caution: {evaluation.warnings[0]} "
        summary += "Nothing is written to your calendar until you approve the proposal."
        return summary

