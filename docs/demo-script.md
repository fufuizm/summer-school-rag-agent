# Demo Script

Target length: 4 to 5 minutes.

## 1. Opening

This is a local-first RAG application built for the Microsoft Foundry Local project
track. It answers questions over private documents and adds a practical
human-in-the-loop correction workflow for student records.

## 2. Show Runtime

Open the UI at http://localhost:3000.

Point out:

- Runtime status
- Document count
- Record count
- Pending correction count

If Foundry Local is loaded, the runtime shows `foundry_local`. If not, the demo uses
the local fallback so the workflow still works.

## 3. RAG Workflow

Upload:

```text
data/sample_project_guide.txt
```

Ask:

```text
What is the Foundry Local RAG project about?
```

Expected result:

- Answer includes grounded snippets
- Sources show the uploaded document and similarity scores
- Audit log records the upload and chat query

## 4. Correction Workflow

Upload:

```text
data/sample_students.csv
```

Open Corrections and click Analyze.

Show examples:

- `Local RAG` becomes the official Foundry Local project title
- `Quantum` becomes `Quantum Kickstart with Q#`
- Suspicious names are flagged for manual review
- Invalid emails are flagged for manual review

Approve a safe project-standardization proposal.

Open Records and show that the approved value changed.

Reject a risky identity/email proposal.

## 5. Export and Audit

Click Export CSV.

Open Audit and show:

- document upload
- records upload
- correction analysis
- approval or rejection event

## 6. Closing

The important design choice is local-first AI with human approval. The app keeps
private records local, gives source-grounded answers, and never silently modifies
high-risk identity fields.
