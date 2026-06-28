# Summer School RAG Agent

A local-first enterprise AI assistant built with Microsoft Foundry Local. It enables grounded question answering over private documents and structured records, while safely handling record correction requests through validation, proposed patches, human approval, and audit logging.

## Project Overview

This project is built as part of the **Building Your First Local RAG Application with Foundry Local** track in the Microsoft Summer School program.

The agent addresses a real operational problem: student registration lists often contain name spelling errors, invalid email addresses, and incorrect project selections. Instead of manually reviewing each record, the agent:

1. Ingests documents (PDF, TXT, CSV, XLSX, HTML) and creates a searchable knowledge base
2. Answers natural language questions with source citations using local LLM + embeddings
3. Detects problematic records in structured data (CSV/XLSX)
4. Proposes corrections as structured JSON patches
5. Routes corrections through an admin approval workflow
6. Logs every action to an immutable audit trail

## Architecture

```
User → Web UI (HTML/CSS/JS) → FastAPI Backend
                                    ├── RAG Pipeline (Foundry Local)
                                    │   ├── Document Ingestion
                                    │   ├── Chunking + Embedding (qwen3-embedding-0.6b)
                                    │   ├── Vector Search (cosine similarity)
                                    │   └── Grounded Response (qwen2.5-0.5b)
                                    ├── Correction Agent
                                    │   ├── Name validation
                                    │   ├── Email format check
                                    │   ├── Project option validation
                                    │   └── JSON patch generation
                                    ├── Approval Workflow
                                    │   ├── Admin review queue
                                    │   ├── Approve / Reject
                                    │   └── Record update
                                    └── Audit Log (SQLite)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Runtime | Microsoft Foundry Local SDK |
| Embedding Model | qwen3-embedding-0.6b |
| Chat Model | qwen2.5-0.5b |
| Backend | Python + FastAPI |
| Frontend | HTML/CSS/JS (vanilla) |
| Document Parsing | PyMuPDF, python-docx, openpyxl, pandas |
| Database | SQLite |
| Deployment | Docker Compose |

## Quick Start

```bash
# Install Foundry Local SDK
pip install foundry-local-sdk openai

# Install backend dependencies
pip install fastapi uvicorn pandas PyMuPDF python-docx openpyxl

# Run the backend
cd backend
uvicorn main:app --reload --port 8000

# Open the frontend
cd frontend
python3 -m http.server 3000
```

## Project Structure

```
summer-school-rag-agent/
├── backend/
│   ├── main.py           # FastAPI app + routes
│   ├── rag.py            # RAG pipeline (ingest, embed, search, answer)
│   ├── correction.py     # Correction agent (validation + patch)
│   ├── ingestion.py      # Document parsing (PDF, TXT, CSV, XLSX, HTML)
│   └── audit.py           # Audit log (SQLite)
├── frontend/
│   ├── index.html         # Web UI
│   ├── style.css          # Terminal-themed styles
│   └── app.js             # Frontend logic
├── data/
│   ├── documents/         # Uploaded documents
│   └── uploads/           # Uploaded CSV/XLSX files
├── tests/
│   └── test_rag.py        # Test cases
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## License

MIT