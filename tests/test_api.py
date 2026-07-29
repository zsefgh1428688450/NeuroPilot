from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_demo_can_be_optimized_and_approved():
    demo = client.get("/api/demo")
    assert demo.status_code == 200

    optimized = client.post("/api/optimize", json=demo.json())
    assert optimized.status_code == 200
    body = optimized.json()
    assert body["status"] == "pending_approval"
    assert len(body["trace"]) == 5

    approved = client.post(
        f"/api/runs/{body['run_id']}/decision", json={"decision": "approve"}
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


def test_root_serves_the_demo_application():
    response = client.get("/")
    assert response.status_code == 200
    assert "NeuroPilot" in response.text

