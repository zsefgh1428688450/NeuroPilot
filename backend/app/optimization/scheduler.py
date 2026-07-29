from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.domain.models import (
    CalendarBlock,
    CognitiveSlot,
    CognitiveVector,
    SchedulePlan,
    ScheduleRecommendation,
    SlotAlternative,
    TaskInput,
    TaskProfile,
)


DIMENSIONS = ("executive", "attention", "creative", "social")


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _time_after(value: time, minutes: int) -> time:
    return (datetime.combine(date.today(), value) + timedelta(minutes=minutes)).time()


def _average_vector(vectors: list[CognitiveVector]) -> CognitiveVector:
    count = len(vectors)
    return CognitiveVector(
        **{
            dimension: sum(getattr(vector, dimension) for vector in vectors) / count
            for dimension in DIMENSIONS
        }
    )


@dataclass(frozen=True)
class Candidate:
    start: time
    end: time
    score: float
    capacity: CognitiveVector
    fatigue: CognitiveVector


class CognitiveScheduler:
    """Greedy constrained optimizer for a hackathon-sized task set."""

    def schedule(
        self,
        tasks: list[TaskInput],
        profiles: list[TaskProfile],
        forecast: list[CognitiveSlot],
        calendar: list[CalendarBlock],
        strictness: float = 1.0,
    ) -> SchedulePlan:
        profile_by_id = {profile.task_id: profile for profile in profiles}
        occupied = [(_minutes(block.start), _minutes(block.end), block.category) for block in calendar]
        recommendations: list[ScheduleRecommendation] = []
        unscheduled: list[str] = []

        ordered_tasks = sorted(
            tasks,
            key=lambda task: (
                task.priority,
                profile_by_id[task.id].intensity,
                task.duration_minutes,
            ),
            reverse=True,
        )
        for task in ordered_tasks:
            profile = profile_by_id[task.id]
            candidates = self._candidates(task, profile, forecast, occupied, strictness)
            if not candidates:
                unscheduled.append(task.id)
                continue
            best = candidates[0]
            occupied.append((_minutes(best.start), _minutes(best.end), profile.category))
            baseline = statistics.median(candidate.score for candidate in candidates)
            improvement = max(0, round((best.score - baseline) / max(baseline, 0.01) * 100))
            dominant = profile.requirements.dominant_dimension()
            dominant_capacity = getattr(best.capacity, dominant)
            reasons = [
                f"{dominant.title()} is the task's strongest demand and is forecast at {dominant_capacity:.0%}.",
                f"This slot has a {best.score:.0%} cognitive-fit score after fatigue and calendar constraints.",
            ]
            if task.preferred_period != "any":
                reasons.append(f"It also respects the task's {task.preferred_period} preference.")
            recommendations.append(
                ScheduleRecommendation(
                    task_id=task.id,
                    title=task.title,
                    category=profile.category,
                    start=best.start,
                    end=best.end,
                    fit_score=best.score,
                    confidence=min(0.96, round(0.68 + max(0, best.score - (candidates[1].score if len(candidates) > 1 else 0.5)) * 0.7, 3)),
                    improvement_percent=improvement,
                    reasons=reasons,
                    alternatives=[
                        SlotAlternative(start=item.start, end=item.end, score=item.score)
                        for item in candidates[1:3]
                    ],
                )
            )

        recommendations.sort(key=lambda item: item.start)
        return SchedulePlan(
            recommendations=recommendations,
            unscheduled_task_ids=unscheduled,
            recovery_suggestions=self._recovery_suggestions(recommendations, profile_by_id, forecast),
        )

    def _candidates(
        self,
        task: TaskInput,
        profile: TaskProfile,
        forecast: list[CognitiveSlot],
        occupied: list[tuple[int, int, str]],
        strictness: float,
    ) -> list[Candidate]:
        rounded_duration = int(math.ceil(task.duration_minutes / 30) * 30)
        required_slots = rounded_duration // 30
        results: list[Candidate] = []

        for index in range(0, len(forecast) - required_slots + 1):
            selected = forecast[index : index + required_slots]
            start = selected[0].start
            end = selected[-1].end
            start_minute, end_minute = _minutes(start), _minutes(end)
            if any(start_minute < busy_end and end_minute > busy_start for busy_start, busy_end, _ in occupied):
                continue
            if task.deadline_time and end > task.deadline_time:
                continue
            if any(selected[position].end != selected[position + 1].start for position in range(len(selected) - 1)):
                continue

            capacity = _average_vector([slot.capacity for slot in selected])
            fatigue = _average_vector([slot.fatigue for slot in selected])
            score = self._score(task, profile, capacity, fatigue, start, occupied, strictness)
            results.append(Candidate(start=start, end=end, score=score, capacity=capacity, fatigue=fatigue))
        return sorted(results, key=lambda item: (item.score, -_minutes(item.start)), reverse=True)

    def _score(
        self,
        task: TaskInput,
        profile: TaskProfile,
        capacity: CognitiveVector,
        fatigue: CognitiveVector,
        start: time,
        occupied: list[tuple[int, int, str]],
        strictness: float,
    ) -> float:
        fit = capacity.weighted_average(profile.requirements)
        fatigue_cost = fatigue.weighted_average(profile.requirements)
        requirement_total = sum(getattr(profile.requirements, dimension) for dimension in DIMENSIONS)
        deficit = sum(
            max(0.0, getattr(profile.requirements, dimension) - getattr(capacity, dimension))
            * getattr(profile.requirements, dimension)
            for dimension in DIMENSIONS
        ) / requirement_total
        preference_bonus = 0.0
        if task.preferred_period == "morning" and start.hour < 12:
            preference_bonus = 0.04
        elif task.preferred_period == "afternoon" and 12 <= start.hour < 17:
            preference_bonus = 0.04
        elif task.preferred_period == "evening" and start.hour >= 17:
            preference_bonus = 0.04

        start_minute = _minutes(start)
        neighbor_categories = [
            category
            for busy_start, busy_end, category in occupied
            if abs(start_minute - busy_end) <= 15 or abs(busy_start - start_minute) <= 15
        ]
        context_cost = 0.035 if neighbor_categories and profile.category not in neighbor_categories else 0.0
        priority_bonus = (task.priority - 3) * 0.008
        raw = (
            0.76 * fit
            + 0.20 * (1 - deficit)
            - 0.16 * fatigue_cost * strictness
            - context_cost
            + preference_bonus
            + priority_bonus
        )
        return round(max(0.0, min(1.0, raw)), 3)

    @staticmethod
    def _recovery_suggestions(
        recommendations: list[ScheduleRecommendation],
        profile_by_id: dict[str, TaskProfile],
        forecast: list[CognitiveSlot],
    ) -> list[str]:
        suggestions: list[str] = []
        high_load = [
            item for item in recommendations if profile_by_id[item.task_id].intensity >= 0.7
        ]
        for previous, current in zip(high_load, high_load[1:]):
            gap = _minutes(current.start) - _minutes(previous.end)
            if 0 <= gap < 20:
                suggestions.append(
                    f"Add a 15–20 minute low-stimulation break after {previous.title}."
                )
                break
        if forecast and max(slot.fatigue.attention for slot in forecast) >= 0.65:
            suggestions.append("Protect one screen-free recovery window in the late afternoon.")
        return suggestions

