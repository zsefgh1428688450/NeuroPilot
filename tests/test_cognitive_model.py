from datetime import date

from app.cognitive import CognitiveModel
from app.domain.models import DailySignals, UserProfile


def test_forecast_covers_workday_with_normalized_values():
    model = CognitiveModel()
    forecast = model.forecast(
        date(2026, 7, 29),
        UserProfile(),
        DailySignals(),
        [],
    )

    assert forecast[0].start.strftime("%H:%M") == "08:00"
    assert forecast[-1].end.strftime("%H:%M") == "19:00"
    assert len(forecast) == 22
    for slot in forecast:
        assert all(0 <= value <= 1 for value in slot.capacity.model_dump().values())
        assert all(0 <= value <= 1 for value in slot.fatigue.model_dump().values())


def test_low_sleep_reduces_morning_executive_capacity():
    model = CognitiveModel()
    user = UserProfile()
    strong_recovery = model.forecast(
        date(2026, 7, 29), user, DailySignals(sleep_hours=7.8, sleep_quality=0.9), []
    )
    weak_recovery = model.forecast(
        date(2026, 7, 29), user, DailySignals(sleep_hours=4.5, sleep_quality=0.3), []
    )

    assert strong_recovery[0].capacity.executive > weak_recovery[0].capacity.executive

