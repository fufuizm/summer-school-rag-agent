# Architecture

## Goal

Build a local-first RAG application that demonstrates Microsoft Foundry Local while
solving a practical data-cleanup workflow for summer school records.

## Components

### Frontend

The frontend is a static HTML/CSS/JS control panel. It has five work views:

- Chat
- Upload
- Corrections
- Records
- Audit

The UI is intentionally dependency-free so it can run from `python -m http.server`,
Docker Compose, or any static host.

### FastAPI Backend

`backend/main.py` exposes the REST API and coordinates the core modules:

- `ingestion.py`: extracts text and structured records
- `rag.py`: embeds, retrieves, and answers from local context
- `correction.py`: proposes and applies approved record corrections
- `audit.py`: stores immutable workflow events in SQLite

### RAG Pipeline

The RAG pipeline has two runtime modes:

- `foundry_local`: uses the Foundry Local SDK with local embedding and chat models
- `fallback`: uses deterministic hash embeddings and extractive snippets

Fallback mode is not the final AI story. It exists so that tests, CI, and the UI demo
stay reliable before model downloads complete.

### Correction Agent

The correction agent is deliberately conservative:

- Project aliases can be standardized after admin approval.
- Suspicious names are flagged but not auto-corrected.
- Invalid emails are flagged but not auto-corrected.
- Rejected proposals are not recreated as new pending proposals.

This keeps the system human-in-the-loop and avoids silently changing identity data.

## Data Flow

```text
Document upload
  -> parse file
  -> chunk text
  -> embed chunks
  -> save local index
  -> answer questions with citations

Records upload
  -> parse CSV/XLSX
  -> analyze rows
  -> propose patches
  -> admin approve/reject
  -> apply safe patches
  -> export corrected CSV
```

## Local Files

- `data/audit.db`: SQLite audit log, ignored by Git
- `data/rag_index.json`: local vector index, ignored by Git
- `data/documents/`: uploaded RAG files, ignored by Git
- `data/uploads/`: uploaded records files, ignored by Git
