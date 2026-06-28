"""
Correction agent for student records.

The agent detects suspicious names, invalid emails, and non-standard project
labels. Low-risk project aliases can be applied after admin approval; high-risk
identity and email issues remain manual by design.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any


VALID_PROJECTS = [
    "Stock Price Prediction with PyTorch",
    "Building Your First Local RAG Application with Foundry Local",
    "Quantum Kickstart with Q#",
    "Titanic Survival Analysis",
]

PROJECT_ALIASES = {
    "stock": VALID_PROJECTS[0],
    "stock prediction": VALID_PROJECTS[0],
    "pytorch": VALID_PROJECTS[0],
    "rag": VALID_PROJECTS[1],
    "local rag": VALID_PROJECTS[1],
    "foundry": VALID_PROJECTS[1],
    "foundry local": VALID_PROJECTS[1],
    "foundry local rag": VALID_PROJECTS[1],
    "building your first local rag": VALID_PROJECTS[1],
    "quantum": VALID_PROJECTS[2],
    "q#": VALID_PROJECTS[2],
    "qsharp": VALID_PROJECTS[2],
    "titanic": VALID_PROJECTS[3],
    "titanic survival": VALID_PROJECTS[3],
}

SUSPICIOUS_NAME_PATTERNS = [
    "anonymous",
    "admin",
    "dragon",
    "fantastic",
    "guest",
    "john doe",
    "jane doe",
    "lorem",
    "ninja",
    "player",
    "sample",
    "test",
    "user",
    "warrior",
    "wizard",
    "xxx",
    "yyy",
]

NAME_FIELDS = ("Name", "name", "Full Name", "full_name", "Student Name")
EMAIL_FIELDS = ("Email", "email", "E-mail", "Mail", "mail")
PROJECT_FIELDS = ("Project", "project", "Project Choice", "Selected Project")


@dataclass
class CorrectionProposal:
    correction_id: str
    file_id: str
    record_index: int
    field: str
    current_value: str
    proposed_value: str
    issue_type: str
    risk_level: str
    reason: str
    confidence: float
    requires_admin_approval: bool = True
    status: str = "pending"
    admin_note: str = ""
    applied: bool = False


class CorrectionAgent:
    def __init__(self):
        self._records: dict[str, list[dict[str, Any]]] = {}
        self._file_names: dict[str, str] = {}
        self._proposals: dict[str, CorrectionProposal] = {}
        self._active_file_id: str | None = None

    # --- Records lifecycle ---

    def load_records(self, file_id: str, records: list[dict[str, Any]], filename: str = ""):
        self._records[file_id] = [dict(record) for record in records]
        self._file_names[file_id] = filename or file_id
        self._active_file_id = file_id
        self._remove_proposals_for_file(file_id)

    def active_file_id(self) -> str | None:
        return self._active_file_id

    def record_count(self, file_id: str = "latest") -> int:
        file_id = self._resolve_file_id(file_id)
        return len(self._records.get(file_id, [])) if file_id else 0

    def list_files(self) -> list[dict[str, Any]]:
        return [
            {
                "file_id": file_id,
                "filename": self._file_names.get(file_id, file_id),
                "records": len(records),
                "active": file_id == self._active_file_id,
            }
            for file_id, records in self._records.items()
        ]

    def get_records(self, file_id: str = "latest", limit: int = 25) -> list[dict[str, Any]]:
        file_id = self._resolve_file_id(file_id)
        if not file_id:
            return []
        return self._records.get(file_id, [])[:limit]

    # --- Analysis and approval ---

    def analyze(self, file_id: str, instructions: str = "") -> list[dict[str, Any]]:
        """Analyze records and generate correction proposals."""
        file_id = self._resolve_file_id(file_id)
        if not file_id:
            return []

        records = self._records.get(file_id, [])
        self._remove_proposals_for_file(file_id, pending_only=True)

        generated: list[CorrectionProposal] = []
        for idx, record in enumerate(records):
            generated.extend(self._analyze_record(file_id, idx, record))

        visible: list[CorrectionProposal] = []
        for proposal in generated:
            existing = self._proposals.get(proposal.correction_id)
            if existing and existing.status != "pending":
                continue
            self._proposals[proposal.correction_id] = proposal
            visible.append(proposal)

        return [asdict(proposal) for proposal in visible]

    def process_approval(self, correction_id: str, approved: bool, admin_note: str = "") -> dict[str, Any]:
        proposal = self._proposals.get(correction_id)
        if not proposal:
            return {"error": "Correction not found", "correction_id": correction_id}

        proposal.status = "approved" if approved else "rejected"
        proposal.admin_note = admin_note
        proposal.applied = False

        if approved and self._can_apply(proposal):
            record = self._records[proposal.file_id][proposal.record_index]
            actual_field = self._find_field(record, (proposal.field,))
            if actual_field:
                record[actual_field] = proposal.proposed_value
                proposal.applied = True

        return asdict(proposal)

    def get_pending(self) -> list[dict[str, Any]]:
        return [
            asdict(proposal)
            for proposal in self._proposals.values()
            if proposal.status == "pending"
        ]

    def pending_count(self) -> int:
        return len(self.get_pending())

    def summary(self) -> dict[str, int]:
        proposals = list(self._proposals.values())
        return {
            "pending": len([p for p in proposals if p.status == "pending"]),
            "approved": len([p for p in proposals if p.status == "approved"]),
            "rejected": len([p for p in proposals if p.status == "rejected"]),
            "applied": len([p for p in proposals if p.applied]),
        }

    def export_csv(self, file_id: str = "latest") -> str:
        file_id = self._resolve_file_id(file_id)
        if not file_id or file_id not in self._records:
            raise ValueError("No records loaded.")

        records = self._records[file_id]
        fieldnames = self._fieldnames(records)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)
        return output.getvalue()

    # --- Validation helpers ---

    def _analyze_record(self, file_id: str, idx: int, record: dict[str, Any]) -> list[CorrectionProposal]:
        proposals: list[CorrectionProposal] = []

        name_field = self._find_field(record, NAME_FIELDS)
        name = self._value(record, name_field)
        if self._is_suspicious_name(name):
            proposals.append(
                self._proposal(
                    file_id=file_id,
                    idx=idx,
                    field=name_field or "Name",
                    current=name,
                    proposed="[REQUIRES MANUAL CORRECTION]",
                    issue_type="suspicious_name",
                    risk="high",
                    reason="The name is empty or looks like a placeholder/fantasy value.",
                    confidence=0.92,
                )
            )

        email_field = self._find_field(record, EMAIL_FIELDS)
        email = self._value(record, email_field)
        if not self._is_valid_email(email):
            proposals.append(
                self._proposal(
                    file_id=file_id,
                    idx=idx,
                    field=email_field or "Email",
                    current=email,
                    proposed="[REQUIRES MANUAL CORRECTION]",
                    issue_type="invalid_email",
                    risk="high",
                    reason="The email address does not match a valid email format.",
                    confidence=0.98,
                )
            )

        project_field = self._find_field(record, PROJECT_FIELDS)
        project = self._value(record, project_field)
        if project:
            normalized = self._normalize_project(project)
            if normalized != project.strip():
                proposals.append(
                    self._proposal(
                        file_id=file_id,
                        idx=idx,
                        field=project_field or "Project",
                        current=project,
                        proposed=normalized,
                        issue_type="project_standardization",
                        risk="medium",
                        reason="The project value is an alias or close match, not the official title.",
                        confidence=self._project_confidence(project, normalized),
                    )
                )
        else:
            proposals.append(
                self._proposal(
                    file_id=file_id,
                    idx=idx,
                    field=project_field or "Project",
                    current=project,
                    proposed="[REQUIRES MANUAL CORRECTION]",
                    issue_type="missing_project",
                    risk="high",
                    reason="No project selection was found for this record.",
                    confidence=0.95,
                )
            )

        return proposals

    def _proposal(
        self,
        file_id: str,
        idx: int,
        field: str,
        current: str,
        proposed: str,
        issue_type: str,
        risk: str,
        reason: str,
        confidence: float,
    ) -> CorrectionProposal:
        raw_id = f"{file_id}:{idx}:{field}:{current}:{proposed}:{issue_type}"
        correction_id = hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:12]
        return CorrectionProposal(
            correction_id=correction_id,
            file_id=file_id,
            record_index=idx,
            field=field,
            current_value=current,
            proposed_value=proposed,
            issue_type=issue_type,
            risk_level=risk,
            reason=reason,
            confidence=round(confidence, 2),
        )

    def _is_suspicious_name(self, name: str) -> bool:
        normalized = name.lower().strip()
        if not normalized:
            return True
        if any(pattern in normalized for pattern in SUSPICIOUS_NAME_PATTERNS):
            return True
        letters = re.findall(r"[a-zA-Z]", normalized)
        if len(letters) < 2:
            return True
        return False

    def _is_valid_email(self, email: str) -> bool:
        if not email or not email.strip():
            return False
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, email.strip()))

    def _normalize_project(self, project: str) -> str:
        raw = project.strip()
        if raw in VALID_PROJECTS:
            return raw
        compact = self._compact(raw)
        if compact in PROJECT_ALIASES:
            return PROJECT_ALIASES[compact]

        best = max(VALID_PROJECTS, key=lambda valid: SequenceMatcher(None, compact, self._compact(valid)).ratio())
        if self._project_confidence(raw, best) >= 0.45:
            return best
        return "[REQUIRES MANUAL CORRECTION]"

    def _project_confidence(self, project: str, normalized: str) -> float:
        if normalized in PROJECT_ALIASES.values():
            alias_hit = PROJECT_ALIASES.get(self._compact(project))
            if alias_hit == normalized:
                return 0.95
        if normalized not in VALID_PROJECTS:
            return 0.35
        return SequenceMatcher(None, self._compact(project), self._compact(normalized)).ratio()

    def _compact(self, value: str) -> str:
        return " ".join(value.lower().replace("#", "sharp").split())

    def _can_apply(self, proposal: CorrectionProposal) -> bool:
        if proposal.proposed_value.startswith("[REQUIRES"):
            return False
        return proposal.file_id in self._records and proposal.record_index < len(self._records[proposal.file_id])

    def _resolve_file_id(self, file_id: str) -> str | None:
        if file_id == "latest":
            return self._active_file_id
        return file_id

    def _remove_proposals_for_file(self, file_id: str, pending_only: bool = False):
        for proposal_id, proposal in list(self._proposals.items()):
            if proposal.file_id != file_id:
                continue
            if pending_only and proposal.status != "pending":
                continue
            del self._proposals[proposal_id]

    def _find_field(self, record: dict[str, Any], candidates: tuple[str, ...]) -> str | None:
        exact = {key: key for key in record}
        for candidate in candidates:
            if candidate in exact:
                return exact[candidate]
        lower = {key.lower(): key for key in record}
        for candidate in candidates:
            if candidate.lower() in lower:
                return lower[candidate.lower()]
        return None

    def _value(self, record: dict[str, Any], field: str | None) -> str:
        if not field:
            return ""
        value = record.get(field, "")
        return "" if value is None else str(value).strip()

    def _fieldnames(self, records: list[dict[str, Any]]) -> list[str]:
        fieldnames: list[str] = []
        for record in records:
            for field in record:
                if field not in fieldnames:
                    fieldnames.append(field)
        return fieldnames
