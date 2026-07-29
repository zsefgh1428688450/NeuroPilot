from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.domain.models import OptimizeRequest, OptimizeResponse


class RunNotFoundError(KeyError):
    pass


class RunRepository:
    """Local-first SQLite store for workflow results and approval decisions."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.getenv("NEUROPILOT_DB_PATH", "data/neuropilot.db")
        self.path = Path(configured)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def save(self, request: OptimizeRequest, response: OptimizeResponse) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_runs (
                    run_id, status, request_json, response_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    response.run_id,
                    response.status,
                    request.model_dump_json(),
                    response.model_dump_json(),
                    now,
                    now,
                ),
            )

    def get(self, run_id: str) -> OptimizeResponse:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT response_json FROM workflow_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise RunNotFoundError(run_id)
        return OptimizeResponse.model_validate_json(row["response_json"])

    def set_decision(self, run_id: str, status: str, comment: str | None) -> OptimizeResponse:
        response = self.get(run_id)
        response.status = status  # type: ignore[assignment]
        response.decision_comment = comment
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE workflow_runs
                SET status = ?, response_json = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (status, response.model_dump_json(), now, run_id),
            )
        return response

