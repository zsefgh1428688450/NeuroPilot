from __future__ import annotations

from datetime import date, datetime, time, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Chronotype(StrEnum):
    MORNING = "morning"
    BALANCED = "balanced"
    EVENING = "evening"


class CognitiveVector(APIModel):
    executive: float = Field(ge=0, le=1)
    attention: float = Field(ge=0, le=1)
    creative: float = Field(ge=0, le=1)
    social: float = Field(ge=0, le=1)

    def weighted_average(self, weights: CognitiveVector) -> float:
        numerator = sum(
            getattr(self, dimension) * getattr(weights, dimension)
            for dimension in ("executive", "attention", "creative", "social")
        )
        denominator = sum(
            getattr(weights, dimension)
            for dimension in ("executive", "attention", "creative", "social")
        )
        return numerator / denominator if denominator else 0.0

    def dominant_dimension(self) -> str:
        return max(
            ("executive", "attention", "creative", "social"),
            key=lambda dimension: getattr(self, dimension),
        )


class UserProfile(APIModel):
    name: str = Field(default="Alex", min_length=1, max_length=80)
    role: str = Field(default="Founder", min_length=1, max_length=100)
    timezone: str = "Asia/Shanghai"
    chronotype: Chronotype = Chronotype.BALANCED
    workday_start: time = time(8, 0)
    workday_end: time = time(19, 0)

    @model_validator(mode="after")
    def validate_workday(self) -> UserProfile:
        if self.workday_start >= self.workday_end:
            raise ValueError("workday_start must be before workday_end")
        return self


class DailySignals(APIModel):
    sleep_hours: float = Field(default=7.5, ge=0, le=14)
    sleep_quality: float = Field(default=0.8, ge=0, le=1)
    energy: float = Field(default=0.75, ge=0, le=1)
    focus: float = Field(default=0.75, ge=0, le=1)
    creativity: float = Field(default=0.7, ge=0, le=1)
    exercise_minutes: int = Field(default=0, ge=0, le=300)
    prior_deep_work_minutes: int = Field(default=0, ge=0, le=720)
    prior_meeting_minutes: int = Field(default=0, ge=0, le=720)


class TaskInput(APIModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    duration_minutes: int = Field(default=60, ge=15, le=240)
    priority: int = Field(default=3, ge=1, le=5)
    deadline_time: time | None = None
    preferred_period: Literal["morning", "afternoon", "evening", "any"] = "any"


class CalendarBlock(APIModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(min_length=1, max_length=160)
    start: time
    end: time
    category: str = "meeting"
    fixed: bool = True

    @model_validator(mode="after")
    def validate_interval(self) -> CalendarBlock:
        if self.start >= self.end:
            raise ValueError("calendar block start must be before end")
        return self


class OptimizeRequest(APIModel):
    target_date: date = Field(default_factory=date.today)
    user: UserProfile = Field(default_factory=UserProfile)
    signals: DailySignals = Field(default_factory=DailySignals)
    tasks: list[TaskInput] = Field(min_length=1, max_length=20)
    calendar: list[CalendarBlock] = Field(default_factory=list, max_length=30)


class CognitiveSlot(APIModel):
    start: time
    end: time
    capacity: CognitiveVector
    fatigue: CognitiveVector
    label: Literal["peak", "good", "steady", "recovery"]


class TaskProfile(APIModel):
    task_id: str
    title: str
    category: str
    requirements: CognitiveVector
    intensity: float = Field(ge=0, le=1)
    analysis_source: Literal["offline_rules", "llm"] = "offline_rules"
    rationale: list[str]


class SlotAlternative(APIModel):
    start: time
    end: time
    score: float = Field(ge=0, le=1)


class ScheduleRecommendation(APIModel):
    task_id: str
    title: str
    category: str
    start: time
    end: time
    fit_score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    improvement_percent: int = Field(ge=0)
    requires_approval: bool = True
    reasons: list[str]
    alternatives: list[SlotAlternative] = Field(default_factory=list)


class SchedulePlan(APIModel):
    recommendations: list[ScheduleRecommendation]
    unscheduled_task_ids: list[str] = Field(default_factory=list)
    recovery_suggestions: list[str] = Field(default_factory=list)


class EvaluationResult(APIModel):
    approved: bool
    confidence: float = Field(ge=0, le=1)
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TraceStep(APIModel):
    agent: str
    status: Literal["completed", "warning", "failed"]
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = Field(ge=0)


class OptimizeResponse(APIModel):
    run_id: str
    status: Literal["pending_approval", "approved", "rejected"] = "pending_approval"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    target_date: date
    forecast: list[CognitiveSlot]
    task_profiles: list[TaskProfile]
    schedule: SchedulePlan
    evaluation: EvaluationResult
    coach_summary: str
    trace: list[TraceStep]
    decision_comment: str | None = None


class DecisionRequest(APIModel):
    decision: Literal["approve", "reject"]
    comment: str | None = Field(default=None, max_length=500)


class HealthResponse(APIModel):
    status: Literal["ok"] = "ok"
    service: str = "neuropilot"
    version: str

