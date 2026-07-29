from __future__ import annotations

import json
from pathlib import Path

from app.domain.models import OptimizeRequest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_SCENARIO = PROJECT_ROOT / "data" / "demo_scenario.json"


def load_demo_request() -> OptimizeRequest:
    return OptimizeRequest.model_validate(json.loads(DEMO_SCENARIO.read_text(encoding="utf-8")))

