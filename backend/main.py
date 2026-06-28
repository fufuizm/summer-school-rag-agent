"""
Summer School RAG Agent backend.

FastAPI application with local-first RAG, student record correction, approval,
export, and audit logging.
"""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from audit import AuditLog
from correction import CorrectionAgent
from ingestion import DocumentParser
from rag import RAGPipeline


app = FastAPI(
    title="Summer School RAG Agent",
    version="1.1.0",
    description="Local-first RAG and human-in-the-loop correction agent.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


DATA_DIR = Path(__file__).parent.parent / "data"
DOCS_DIR = DATA_DIR / "documents"
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "audit.db"
INDEX_PATH = DATA_DIR / "rag_index.json"

for directory in (DATA_DIR, DOCS_DIR, UPLOADS_DIR):
    directory.mkdir(parents=True, exist_ok=True)


rag = RAGPipeline(index_path=INDEX_PATH)
correction_agent = CorrectionAgent()
audit = AuditLog(str(DB_PATH))
parser = DocumentParser()


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(4, ge=1, le=8)


class CorrectionRequest(BaseModel):
    file_id: str = "latest"
    instructions: str = ""


class ApprovalRequest(BaseModel):
    correction_id: str
    approved: bool
    admin_note: Optional[str] = ""


def safe_filename(filename: str) -> str:
    base = Path(filename).name.strip()
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base)
    base = re.sub(r"\s+", "_", base)
    return base or f"upload_{uuid.uuid4().hex[:8]}"


async def save_upload(file: UploadFile, target_dir: Path) -> tuple[Path, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    safe_name = safe_filename(file.filename)
    target_path = target_dir / f"{uuid.uuid4().hex[:8]}_{safe_name}"

    with target_path.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)

    return target_path, safe_name


@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Summer School RAG Agent",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "runtime": rag.runtime_status(),
        "documents_indexed": rag.document_count(),
        "chunks_indexed": rag.chunk_count(),
        "active_records_file": correction_agent.active_file_id(),
        "records_loaded": correction_agent.record_count(),
        "corrections": correction_agent.summary(),
    }


@app.post("/api/upload/document")
async def upload_document(file: UploadFile = File(...)):
    """Upload a document for RAG indexing."""
    file_path, display_name = await save_upload(file, DOCS_DIR)

    try:
        chunks = parser.parse(str(file_path))
        rag.ingest(chunks, source=display_name)
        audit.log("document_upload", display_name, {"chunks": len(chunks)})
        return {
            "status": "indexed",
            "filename": display_name,
            "chunks": len(chunks),
            "runtime": rag.runtime_status(),
        }
    except Exception as exc:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Ask a question and get a grounded answer with citations."""
    try:
        answer, sources = rag.query(request.query, top_k=request.top_k)
        audit.log("chat_query", request.query, {"sources": sources})
        return {
            "answer": answer,
            "sources": sources,
            "runtime": rag.runtime_status(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}") from exc


@app.get("/api/documents")
async def list_documents():
    return {"documents": rag.list_documents(), "chunks": rag.chunk_count()}


@app.delete("/api/documents")
async def clear_documents():
    rag.clear()
    audit.log("document_index_clear", "all", {})
    return {"status": "cleared"}


@app.post("/api/upload/records")
async def upload_records(file: UploadFile = File(...)):
    """Upload a CSV/XLSX file with student records for correction analysis."""
    file_path, display_name = await save_upload(file, UPLOADS_DIR)

    try:
        records = parser.parse_records(str(file_path))
        file_id = f"records_{uuid.uuid4().hex[:10]}"
        correction_agent.load_records(file_id, records, filename=display_name)
        audit.log("records_upload", display_name, {"file_id": file_id, "records": len(records)})
        return {
            "status": "loaded",
            "file_id": file_id,
            "filename": display_name,
            "records": len(records),
            "preview": records[:5],
        }
    except Exception as exc:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to parse records: {exc}") from exc


@app.get("/api/records")
async def list_record_files():
    return {"files": correction_agent.list_files()}


@app.get("/api/records/{file_id}")
async def preview_records(file_id: str, limit: int = 25):
    return {
        "file_id": file_id,
        "records": correction_agent.get_records(file_id, limit=limit),
    }


@app.post("/api/correction/analyze")
async def analyze_corrections(request: CorrectionRequest):
    try:
        proposals = correction_agent.analyze(request.file_id, request.instructions)
        audit.log("correction_analysis", request.file_id, {"proposals": len(proposals)})
        return {
            "corrections": proposals,
            "summary": correction_agent.summary(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc


@app.post("/api/correction/approve")
async def approve_correction(request: ApprovalRequest):
    try:
        result = correction_agent.process_approval(
            request.correction_id,
            request.approved,
            request.admin_note or "",
        )
        audit.log(
            "correction_approval",
            request.correction_id,
            {"approved": request.approved, "result": result},
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Approval failed: {exc}") from exc


@app.get("/api/corrections/pending")
async def pending_corrections():
    return {
        "corrections": correction_agent.get_pending(),
        "summary": correction_agent.summary(),
    }


@app.get("/api/correction/export/{file_id}")
async def export_records(file_id: str):
    try:
        csv_text = correction_agent.export_csv(file_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    filename = f"{safe_filename(file_id)}_corrected.csv"
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/audit")
async def get_audit_log(limit: int = 50):
    return {"entries": audit.get_recent(limit)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
