import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_upload_plan_transform_flow(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        usage_db_path=tmp_path / "usage.db",
        openai_api_key=None,
        openai_model="gpt-4.1-mini",
        max_free_uses=5,
        preview_rows=10,
        cors_origins=["http://localhost:5173"],
    )
    client = TestClient(create_app(settings))

    csv_data = b"name,amount,tax\nanna,10,1\nmario,20,2\n"
    upload_response = client.post(
        "/api/files/upload",
        files={"file": ("sample.csv", csv_data, "text/csv")},
    )
    assert upload_response.status_code == 200
    file_id = upload_response.json()["file_id"]

    plan_response = client.post(
        "/api/plan",
        json={
            "file_id": file_id,
            "prompt": "trim whitespace and uppercase name",
            "user_id": "tester",
        },
    )
    assert plan_response.status_code == 200
    plan = plan_response.json()["plan"]
    assert "operations" in plan

    preview_response = client.post(
        "/api/transform/preview",
        json={
            "file_id": file_id,
            "plan": {"operations": [{"type": "change_case", "columns": ["name"], "case": "upper"}]},
        },
    )
    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    assert "summary" in preview_payload
    assert len(preview_payload["steps"]) == 1
    assert len(preview_payload["analysis"]["preview"]) <= 10

    usage_after_preview = client.get("/api/usage/tester")
    assert usage_after_preview.status_code == 200
    assert usage_after_preview.json()["usage_count"] == 0

    apply_response = client.post(
        "/api/transform",
        json={
            "file_id": file_id,
            "user_id": "tester",
            "output_format": "csv",
            "plan": {"operations": [{"type": "change_case", "columns": ["name"], "case": "upper"}]},
        },
    )
    assert apply_response.status_code == 200
    payload = apply_response.json()
    assert payload["usage_count"] == 1
    assert payload["remaining_uses"] == 4

    download_response = client.get(f"/api/results/{payload['result_id']}/download")
    assert download_response.status_code == 200

    failed_apply_response = client.post(
        "/api/transform",
        json={
            "file_id": file_id,
            "user_id": "tester",
            "output_format": "csv",
            "plan": {"operations": [{"type": "unsupported_op"}]},
        },
    )
    assert failed_apply_response.status_code == 400

    with sqlite3.connect(settings.usage_db_path) as connection:
        rows = connection.execute(
            """
            SELECT status, error_code, transformation_type, plan_tier, file_size_bytes, processing_ms
            FROM analytics_events
            ORDER BY id
            """
        ).fetchall()

    assert len(rows) == 2
    success_row, error_row = rows
    assert success_row[0] == "success"
    assert success_row[1] is None
    assert success_row[2] == "clean"
    assert success_row[3] == "free"
    assert int(success_row[4]) == len(csv_data)
    assert int(success_row[5]) >= 0

    assert error_row[0] == "error"
    assert error_row[1] == "invalid_plan"
    assert error_row[3] == "free"
    assert int(error_row[4]) == len(csv_data)


def test_ambiguous_prompt_requires_clarification(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        usage_db_path=tmp_path / "usage.db",
        openai_api_key=None,
        openai_model="gpt-4.1-mini",
        max_free_uses=5,
        preview_rows=10,
        cors_origins=["http://localhost:5173"],
    )
    app = create_app(settings)
    app.state.services.llm_planner.create_plan = lambda prompt, analysis: (
        {
            "needs_clarification": True,
            "clarification_question": "Intendi raggruppare per cliente o per data?",
            "operations": [],
        },
        [],
    )
    client = TestClient(app)

    csv_data = b"cliente,data,amount\nA,2026-01-01,100\nB,2026-01-02,200\n"
    upload_response = client.post(
        "/api/files/upload",
        files={"file": ("sample.csv", csv_data, "text/csv")},
    )
    assert upload_response.status_code == 200
    file_id = upload_response.json()["file_id"]

    plan_response = client.post(
        "/api/plan",
        json={
            "file_id": file_id,
            "prompt": "fammi un riepilogo",
            "user_id": "tester",
        },
    )
    assert plan_response.status_code == 200
    plan_payload = plan_response.json()
    assert plan_payload["needs_clarification"] is True
    assert plan_payload["clarification_question"] == "Intendi raggruppare per cliente o per data?"

    preview_response = client.post(
        "/api/transform/preview",
        json={
            "file_id": file_id,
            "plan": plan_payload["plan"],
        },
    )
    assert preview_response.status_code == 400
    assert "cliente o per data" in preview_response.json()["detail"]

    apply_response = client.post(
        "/api/transform",
        json={
            "file_id": file_id,
            "user_id": "tester",
            "output_format": "csv",
            "plan": plan_payload["plan"],
        },
    )
    assert apply_response.status_code == 400
    assert "cliente o per data" in apply_response.json()["detail"]
