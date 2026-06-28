import os
import sys

os.environ["SUMMER_RAG_FORCE_FALLBACK"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "runtime" in data


def test_document_upload_and_chat_flow():
    content = (
        "Foundry Local runs language and embedding models on device. "
        "The RAG application answers using indexed local documents."
    )
    upload = client.post(
        "/api/upload/document",
        files={"file": ("guide.txt", content, "text/plain")},
    )
    assert upload.status_code == 200
    assert upload.json()["chunks"] == 1

    chat = client.post(
        "/api/chat",
        json={"query": "Where does Foundry Local run models?"},
    )
    assert chat.status_code == 200
    payload = chat.json()
    assert payload["sources"]
    assert payload["runtime"]["runtime"] == "fallback"


def test_records_correction_approval_flow():
    csv_text = (
        "Name,Email,Project\n"
        "Ada Yilmaz,ada.yilmaz@example.com,Local RAG\n"
        "Player1,player1@example.com,Quantum\n"
    )
    upload = client.post(
        "/api/upload/records",
        files={"file": ("students.csv", csv_text, "text/csv")},
    )
    assert upload.status_code == 200
    file_id = upload.json()["file_id"]

    analysis = client.post(
        "/api/correction/analyze",
        json={"file_id": file_id, "instructions": "check all fields"},
    )
    assert analysis.status_code == 200
    corrections = analysis.json()["corrections"]
    assert corrections

    safe_patch = [
        correction
        for correction in corrections
        if correction["issue_type"] == "project_standardization"
    ][0]
    approval = client.post(
        "/api/correction/approve",
        json={"correction_id": safe_patch["correction_id"], "approved": True},
    )
    assert approval.status_code == 200
    assert approval.json()["applied"] is True

    exported = client.get(f"/api/correction/export/{file_id}")
    assert exported.status_code == 200
    assert "Building Your First Local RAG Application with Foundry Local" in exported.text
