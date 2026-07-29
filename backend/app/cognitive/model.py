from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from app.domain.models import (
    CalendarBlock,
    Chronotype,
    CognitiveSlot,
    CognitiveVector,
    DailySignals,
    UserProfile,
)


DIMENSIONS = ("executive", "attention", "creative", "social")


def clamp(value: float, minimum: float = 0.05, maximum: float = 0.98) -> float:
    return round(max(minimum, min(maximum, value)), 3)


class CognitiveModel:
    """Explainable, non-medical baseline for half-hour cognitive forecasts.

    This is intentionally a parameterized model rather than a claim of direct
    brain-state measurement. Its output is suitable for ranking work slots and
    can later be calibrated from user feedback or replaced by an ML predictor.
    """

    SLOT_MINUTES = 30

    _PEAK_CENTERS = {
        Chronotype.MORNING: 10.0,
        Chronotype.BALANCED: 12.0,
        Chronotype.EVENING: 15.5,
    }

    def forecast(
        self,
        target_date: date,
        user: UserProfile,
        signals: DailySignals,
        calendar: list[CalendarBlock],
    ) -> list[CognitiveSlot]:
        current = datetime.combine(target_date, user.workday_start)
        end = datetime.combine(target_date, user.workday_end)
        slots: list[CognitiveSlot] = []

        while current + timedelta(minutes=self.SLOT_MINUTES) <= end:
            hour = current.hour + current.minute / 60
            meeting_minutes = signals.prior_meeting_minutes + self._elapsed_meeting_minutes(
                current, target_date, calendar
            )
            elapsed_work_minutes = max(
                0,
                int((current - datetime.combine(target_date, user.workday_start)).total_seconds() / 60),
            )
            fatigue = self._fatigue_vector(
                hour,
                elapsed_work_minutes,
                signals.prior_deep_work_minutes,
                meeting_minutes,
            )
            capacity = self._capacity_vector(hour, user.chronotype, signals, fatigue)
            label = self._label(capacity)
            slots.append(
                CognitiveSlot(
                    start=current.time(),
                    end=(current + timedelta(minutes=self.SLOT_MINUTES)).time(),
                    capacity=capacity,
                    fatigue=fatigue,
                    label=label,
                )
            )
            current += timedelta(minutes=self.SLOT_MINUTES)
        return slots

    def _capacity_vector(
        self,
        hour: float,
        chronotype: Chronotype,
        signals: DailySignals,
        fatigue: CognitiveVector,
    ) -> CognitiveVector:
        peak_center = self._PEAK_CENTERS[chronotype]
        circadian = 0.42 + 0.52 * math.exp(-0.5 * ((hour - peak_center) / 3.1) ** 2)
        lunch_dip = 0.10 * math.exp(-0.5 * ((hour - 13.7) / 0.9) ** 2)
        sleep_duration = math.exp(-0.5 * ((signals.sleep_hours - 7.7) / 1.8) ** 2)
        recovery = 0.55 * signals.sleep_quality + 0.45 * sleep_duration
        movement_boost = min(signals.exercise_minutes / 120, 1) * 0.08

        executive = (
            0.42 * circadian
            + 0.24 * signals.focus
            + 0.18 * signals.energy
            + 0.16 * recovery
            - 0.30 * fatigue.executive
            - lunch_dip
        )
        attention = (
            0.36 * circadian
            + 0.33 * signals.focus
            + 0.18 * recovery
            + 0.13 * signals.energy
            - 0.34 * fatigue.attention
            - lunch_dip
        )
        creative = (
            0.24 * circadian
            + 0.38 * signals.creativity
            + 0.18 * signals.energy
            + 0.12 * recovery
            + movement_boost
            - 0.22 * fatigue.creative
            - lunch_dip * 0.45
        )
        social = (
            0.23 * circadian
            + 0.35 * signals.energy
            + 0.22 * recovery
            + 0.18
            - 0.32 * fatigue.social
            - lunch_dip * 0.35
        )
        return CognitiveVector(
            executive=clamp(executive),
            attention=clamp(attention),
            creative=clamp(creative),
            social=clamp(social),
        )

    def _fatigue_vector(
        self,
        hour: float,
        elapsed_work_minutes: int,
        prior_deep_work_minutes: int,
        meeting_minutes: int,
    ) -> CognitiveVector:
        time_load = min(elapsed_work_minutes / 660, 1)
        deep_load = min(prior_deep_work_minutes / 300, 1)
        meeting_load = min(meeting_minutes / 300, 1)
        late_day = max(0, hour - 16) / 5
        return CognitiveVector(
            executive=clamp(0.05 + 0.35 * time_load + 0.30 * deep_load + 0.18 * meeting_load + 0.12 * late_day, 0, 0.95),
            attention=clamp(0.04 + 0.39 * time_load + 0.34 * deep_load + 0.10 * meeting_load + 0.13 * late_day, 0, 0.95),
            creative=clamp(0.04 + 0.22 * time_load + 0.24 * deep_load + 0.12 * meeting_load + 0.08 * late_day, 0, 0.95),
            social=clamp(0.03 + 0.16 * time_load + 0.10 * deep_load + 0.48 * meeting_load + 0.10 * late_day, 0, 0.95),
        )

    @staticmethod
    def _elapsed_meeting_minutes(
        current: datetime,
        target_date: date,
        calendar: list[CalendarBlock],
    ) -> int:
        total = 0
        for block in calendar:
            if block.category not in {"meeting", "interview", "social"}:
                continue
            start = datetime.combine(target_date, block.start)
            end = datetime.combine(target_date, block.end)
            if end <= current:
                total += int((end - start).total_seconds() / 60)
        return total

    @staticmethod
    def _label(capacity: CognitiveVector) -> str:
        average = sum(getattr(capacity, dimension) for dimension in DIMENSIONS) / len(DIMENSIONS)
        if average >= 0.77:
            return "peak"
        if average >= 0.66:
            return "good"
        if average >= 0.52:
            return "steady"
        return "recovery"
