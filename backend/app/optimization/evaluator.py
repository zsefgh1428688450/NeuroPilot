from __future__ import annotations

from app.domain.models import (
    CalendarBlock,
    EvaluationResult,
    SchedulePlan,
    TaskInput,
    TaskProfile,
)


def _minutes(value) -> int:
    return value.hour * 60 + value.minute


class ScheduleEvaluator:
    def evaluate(
        self,
        plan: SchedulePlan,
        tasks: list[TaskInput],
        profiles: list[TaskProfile],
        calendar: list[CalendarBlock],
    ) -> EvaluationResult:
        issues: list[str] = []
        warnings: list[str] = []
        profile_by_id = {profile.task_id: profile for profile in profiles}

        expected_ids = {task.id for task in tasks}
        planned_ids = {item.task_id for item in plan.recommendations}
        if expected_ids - planned_ids:
            issues.append(f"{len(expected_ids - planned_ids)} task(s) could not be placed within the workday.")

        all_intervals = [
            (_minutes(item.start), _minutes(item.end), item.title)
            for item in plan.recommendations
        ]
        for index, first in enumerate(all_intervals):
            for second in all_intervals[index + 1 :]:
                if first[0] < second[1] and first[1] > second[0]:
                    issues.append(f"Schedule overlap detected between {first[2]} and {second[2]}.")
        for start, end, title in all_intervals:
            for block in calendar:
                if start < _minutes(block.end) and end > _minutes(block.start):
                    issues.append(f"{title} conflicts with fixed calendar block {block.title}.")

        for item in plan.recommendations:
            if item.fit_score < 0.5:
                warnings.append(f"{item.title} has a relatively weak cognitive fit ({item.fit_score:.0%}).")

        high_load = [
            item
            for item in plan.recommendations
            if profile_by_id[item.task_id].intensity >= 0.72
        ]
        for previous, current in zip(high_load, high_load[1:]):
            if 0 <= _minutes(current.start) - _minutes(previous.end) < 15:
                warnings.append("Two high-load tasks are adjacent; add a recovery buffer if possible.")
                break

        scores = [item.fit_score for item in plan.recommendations]
        mean_score = sum(scores) / len(scores) if scores else 0.0
        confidence = max(0.2, min(0.97, mean_score - len(warnings) * 0.03 - len(issues) * 0.15))
        return EvaluationResult(
            approved=not issues,
            confidence=round(confidence, 3),
            issues=list(dict.fromkeys(issues)),
            warnings=list(dict.fromkeys(warnings)),
        )
