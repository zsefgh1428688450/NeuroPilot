from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.agents import NeuroPilotWorkflow
from app.demo import load_demo_request
from app.domain.models import (
    DecisionRequest,
    HealthResponse,
    OptimizeRequest,
    OptimizeResponse,
)
from app.storage import RunNotFoundError, RunRepository


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = FastAPI(
    title="NeuroPilot API",
    version=__version__,
    description=(
        "Human-in-the-loop cognitive energy scheduling. Estimates are productivity signals, "
        "not medical measurements or diagnoses."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

workflow = NeuroPilotWorkflow()
repository = RunRepository()


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(version=__version__)


@app.get("/api/demo", response_model=OptimizeRequest, tags=["demo"])
def demo_scenario() -> OptimizeRequest:
    return load_demo_request()


@app.post("/api/optimize", response_model=OptimizeResponse, tags=["agent"])
def optimize(request: OptimizeRequest) -> OptimizeResponse:
    response = workflow.run(request)
    repository.save(request, response)
    return response


@app.get("/api/runs/{run_id}", response_model=OptimizeResponse, tags=["agent"])
def get_run(run_id: str) -> OptimizeResponse:
    try:
        return repository.get(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workflow run not found") from exc


@app.post("/api/runs/{run_id}/decision", response_model=OptimizeResponse, tags=["approval"])
def decide(run_id: str, decision: DecisionRequest) -> OptimizeResponse:
    try:
        return repository.set_decision(
            run_id,
            "approved" if decision.decision == "approve" else "rejected",
            decision.comment,
        )
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workflow run not found") from exc


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")

