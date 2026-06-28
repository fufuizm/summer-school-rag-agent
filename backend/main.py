"""
Summer School RAG Agent - Backend
FastAPI application with RAG pipeline and correction agent.
"""

import os
import json
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from rag import RAGPipeline
from correction import CorrectionAgent
from audit import AuditLog
from ingestion import DocumentParser

# Initialize components
app = FastAPI(title="Summer School RAG Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data directories
DATA_DIR = Path(__file__).parent.parent / "data"
DOCS_DIR = DATA_DIR / "documents"
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "audit.db"

DOCS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Initialize core components
rag = RAGPipeline()
correction_agent = CorrectionAgent()
audit = AuditLog(str(DB_PATH))
parser = DocumentParser()


# ===== Models =====

class ChatRequest(BaseModel):
    query: str


class CorrectionRequest(BaseModel):
    file_id: str
    instructions: str


class ApprovalRequest(BaseModel):
    correction_id: str
    approved: bool
    admin_note: Optional[str] = ""


# ===== Routes =====

@app.get("/")
async def root():
    return {"status": "online", "service": "Summer School RAG Agent"}


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "models_loaded": rag.is_ready(),
        "documents_indexed": rag.document_count(),
        "pending_corrections": correction_agent.pending_count(),
    }


# --- Document Upload & RAG ---

@app.post("/api/upload/document")
async def upload_document(file: UploadFile = File(...)):
    """Upload a document (PDF, TXT, CSV, XLSX, HTML, DOCX) for RAG indexing."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Save file
    file_path = DOCS_DIR / file.filename
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Parse and index
    try:
        chunks = parser.parse(str(file_path))
        rag.ingest(chunks, source=file.filename)
        audit.log("document_upload", file.filename, {"chunks": len(chunks)})
        return {
            "status": "indexed",
            "filename": file.filename,
            "chunks": len(chunks),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Ask a question and get a grounded answer with citations."""
    if not rag.is_ready():
        raise HTTPException(status_code=503, detail="Models not loaded yet")

    try:
        answer, sources = rag.query(request.query)
        audit.log("chat_query", request.query, {"sources": sources})
        return {"answer": answer, "sources": sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@app.get("/api/documents")
async def list_documents():
    """List all indexed documents."""
    return {"documents": rag.list_documents()}


# --- Correction Agent ---

@app.post("/api/upload/records")
async def upload_records(file: UploadFile = File(...)):
    """Upload a CSV/XLSX file with student records for correction analysis."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    file_path = UPLOADS_DIR / file.filename
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        records = parser.parse_records(str(file_path))
        file_id = f"records_{len(records)}"
        correction_agent.load_records(file_id, records)
        audit.log("records_upload", file.filename, {"records": len(records)})
        return {
            "status": "loaded",
            "file_id": file_id,
            "records": len(records),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse records: {str(e)}")


@app.post("/api/correction/analyze")
async def analyze_corrections(request: CorrectionRequest):
    """Analyze records and propose corrections."""
    try:
        proposals = correction_agent.analyze(request.file_id, request.instructions)
        audit.log("correction_analysis", request.file_id, {"proposals": len(proposals)})
        return {"corrections": proposals}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.post("/api/correction/approve")
async def approve_correction(request: ApprovalRequest):
    """Approve or reject a proposed correction."""
    try:
        result = correction_agent.process_approval(
            request.correction_id,
            request.approved,
            request.admin_note,
        )
        audit.log(
            "correction_approval",
            request.correction_id,
            {"approved": request.approved, "result": result},
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Approval failed: {str(e)}")


@app.get("/api/corrections/pending")
async def pending_corrections():
    """List all pending corrections awaiting approval."""
    return {"corrections": correction_agent.get_pending()}


# --- Audit Log ---

@app.get("/api/audit")
async def get_audit_log(limit: int = 50):
    """Retrieve recent audit log entries."""
    return {"entries": audit.get_recent(limit)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)