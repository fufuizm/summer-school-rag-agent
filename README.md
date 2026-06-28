# ForgeLens

A local-first RAG and correction-review application for the Microsoft Summer School
project track: **Building Your First Local RAG Application with Foundry Local**.

The app indexes private documents locally, answers questions with citations, analyzes
student registration records, proposes structured corrections, routes every proposed
change through human approval, and records the workflow in a SQLite audit log.

## Name

**ForgeLens** combines the Foundry Local runtime with the idea of a lens over private
documents and operational records. It is short, demo-friendly, and easier to present
than a generic RAG chatbot name.

## Why This Project Stands Out

Most first RAG demos stop at "upload a PDF and chat with it." This project keeps the
assigned Foundry Local RAG scope, then adds a realistic operations workflow:

1. Upload a project guide or student list.
2. Ask grounded questions over the local document index.
3. Detect invalid names, invalid emails, and non-standard project selections.
4. Approve or reject proposed patches.
5. Export the corrected CSV.
6. Show a local audit trail for the full workflow.

## Architecture

```text
Browser UI
  |
  | HTTP
  v
FastAPI backend
  |-- DocumentParser: PDF, TXT, CSV, XLSX, HTML, DOCX
  |-- RAGPipeline: Foundry Local embeddings/chat plus deterministic fallback
  |-- CorrectionAgent: validation, patch proposals, approval workflow
  |-- AuditLog: SQLite event trail
  v
Local data folder
```

Primary AI runtime:

- Embeddings: `qwen3-embedding-0.6b`
- Chat: `qwen2.5-0.5b`
- SDK: Microsoft Foundry Local SDK

Development fallback:

- Set `SUMMER_RAG_FORCE_FALLBACK=1`
- Uses deterministic local hashing retrieval and extractive grounded snippets
- Keeps tests and demos working even before Foundry Local models finish downloading

## Quick Start

Use Python 3.11.

```bash
git clone https://github.com/fufuizm/summer-school-rag-agent.git
cd summer-school-rag-agent

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

make test
```

Run the local demo without waiting for model downloads:

```bash
make api
```

In a second terminal:

```bash
make web
```

Open:

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

For the real Foundry Local runtime, remove `SUMMER_RAG_FORCE_FALLBACK=1` and start the
backend normally:

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The first real run downloads and loads the Foundry Local models.

## Demo Flow

1. Start backend and frontend.
2. Upload `data/sample_project_guide.txt` in the Upload tab.
3. Ask: `What is the Foundry Local RAG project about?`
4. Upload `data/sample_students.csv`.
5. Open Corrections and click Analyze.
6. Approve safe project-standardization patches.
7. Reject or leave manual identity/email fixes for human review.
8. Export the corrected CSV.
9. Open Audit to show the local event trail.

## API Surface

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Runtime, document, record, and correction status |
| `POST` | `/api/upload/document` | Index a document for RAG |
| `POST` | `/api/chat` | Ask a grounded question |
| `GET` | `/api/documents` | List indexed documents |
| `DELETE` | `/api/documents` | Clear local RAG index |
| `POST` | `/api/upload/records` | Load CSV/XLSX records |
| `POST` | `/api/correction/analyze` | Generate correction proposals |
| `POST` | `/api/correction/approve` | Approve or reject a proposal |
| `GET` | `/api/correction/export/{file_id}` | Download corrected CSV |
| `GET` | `/api/audit` | Read recent audit events |

## Project Structure

```text
summer-school-rag-agent/
  backend/
    audit.py
    correction.py
    ingestion.py
    main.py
    rag.py
  data/
    sample_project_guide.txt
    sample_students.csv
  docs/
    architecture.md
    azure-container-apps.md
    demo-script.md
    evaluation.md
  frontend/
    app.js
    index.html
    style.css
  tests/
    test_rag.py
  Dockerfile
  docker-compose.yml
  Makefile
  requirements.txt
  requirements-dev.txt
```

## Docker

```bash
docker compose up --build
```

Then open http://localhost:3000.

## Azure Credit Usage

Foundry Local runs on device, so the core project does not require cloud inference.
The optional Azure story is deployment and presentation polish:

- Containerize the FastAPI backend and static frontend.
- Deploy to Azure Container Apps for a remote demo.
- Keep the model-serving story local-first for privacy and cost control.

See [docs/azure-container-apps.md](docs/azure-container-apps.md).

## Testing

```bash
make test
```

The test suite forces fallback mode so it runs without downloading local LLM models.
It covers document parsing, fallback RAG retrieval, correction detection, duplicate
prevention, approval application, rejection persistence, and CSV export.

## References

- [Microsoft Learn: Build a RAG app with Foundry Local](https://learn.microsoft.com/en-us/azure/foundry-local/tutorials/tutorial-build-rag-app)
- [Microsoft Learn: Foundry Local SDK reference](https://learn.microsoft.com/en-us/azure/foundry-local/reference/reference-sdk-current)

## License

MIT
