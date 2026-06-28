# Evaluation Plan

## RAG Quality Checks

Use the sample guide and ask:

1. What is the Foundry Local RAG project about?
2. What are the project prerequisites?
3. When is the kickoff meeting?
4. Which projects are available?
5. What should the system say if the answer is not in the document?

Expected behavior:

- Answers cite indexed sources.
- Unknown answers should not be hallucinated.
- The fallback runtime should return grounded snippets.
- The Foundry Local runtime should produce a concise natural-language answer.

## Correction Checks

Use `data/sample_students.csv`.

Expected findings:

- `Local RAG` -> `Building Your First Local RAG Application with Foundry Local`
- `Quantum` -> `Quantum Kickstart with Q#`
- `Stock Prediction` -> `Stock Price Prediction with PyTorch`
- `Foundry Local RAG` -> `Building Your First Local RAG Application with Foundry Local`
- Empty name is flagged for manual review
- `Player1` and `test user` are flagged as suspicious names
- Invalid emails are flagged for manual review

## Human Approval Checks

1. Approve a project-standardization proposal.
2. Confirm the value changes in the Records view.
3. Reject a suspicious-name proposal.
4. Re-run Analyze.
5. Confirm the rejected proposal is not recreated as pending.

## Non-Functional Checks

- Backend starts with `make api`.
- Frontend starts with `make web`.
- `make test` passes in fallback mode.
- Audit log records upload, chat, analyze, approve, and reject actions.
- Exported CSV contains approved safe patches.
