"""
Correction Agent - Detects and proposes corrections for student records.
Validates names, emails, project selections, and generates JSON patches.
"""

import re
import uuid
from typing import Optional
from dataclasses import dataclass, field, asdict


# Valid project options from the summer school
VALID_PROJECTS = [
    "Stock Price Prediction with PyTorch",
    "Building Your First Local RAG Application with Foundry Local",
    "Quantum Kickstart with Q#",
    "Titanic Survival Analysis",
]

# Common fantasy / placeholder names that indicate errors
FANTASY_PATTERNS = [
    "fantastic", "dragon", "wizard", "ninja", "warrior", "player",
    "user", "test", "admin", "guest", "anonymous", "xxx", "yyy",
]


@dataclass
class CorrectionProposal:
    correction_id: str
    record_index: int
    field: str
    current_value: str
    proposed_value: str
    issue_type: str
    risk_level: str
    requires_admin_approval: bool = True
    status: str = "pending"  # pending | approved | rejected
    admin_note: str = ""


class CorrectionAgent:
    def __init__(self):
        self._records: dict[str, list[dict]] = {}
        self._proposals: list[CorrectionProposal] = []

    def load_records(self, file_id: str, records: list[dict]):
        self._records[file_id] = records
        print(f"✓ Loaded {len(records)} records for {file_id}.")

    def analyze(self, file_id: str, instructions: str = "") -> list[dict]:
        """Analyze records and generate correction proposals."""
        if file_id == "latest" and self._records:
            file_id = list(self._records.keys())[-1]
        records = self._records.get(file_id)
        if not records:
            return []

        proposals = []
        for idx, record in enumerate(records):
            # Check name
            name = str(record.get("Name", record.get("name", "")))
            if self._is_fantasy_name(name):
                p = CorrectionProposal(
                    correction_id=str(uuid.uuid4())[:8],
                    record_index=idx,
                    field="name",
                    current_value=name,
                    proposed_value="[REQUIRES MANUAL CORRECTION]",
                    issue_type="fantasy_name",
                    risk_level="high",
                )
                self._proposals.append(p)
                proposals.append(asdict(p))

            # Check email
            email = str(record.get("Email", record.get("email", "")))
            if not self._is_valid_email(email):
                p = CorrectionProposal(
                    correction_id=str(uuid.uuid4())[:8],
                    record_index=idx,
                    field="email",
                    current_value=email,
                    proposed_value="[REQUIRES MANUAL CORRECTION]",
                    issue_type="invalid_email",
                    risk_level="high",
                )
                self._proposals.append(p)
                proposals.append(asdict(p))

            # Check project
            project = str(record.get("Project", record.get("project", "")))
            if project and not self._is_valid_project(project):
                matched = self._find_closest_project(project)
                p = CorrectionProposal(
                    correction_id=str(uuid.uuid4())[:8],
                    record_index=idx,
                    field="project",
                    current_value=project,
                    proposed_value=matched,
                    issue_type="invalid_project",
                    risk_level="medium",
                )
                self._proposals.append(p)
                proposals.append(asdict(p))

        return proposals

    def process_approval(self, correction_id: str, approved: bool, admin_note: str = "") -> dict:
        """Process an approval or rejection."""
        for p in self._proposals:
            if p.correction_id == correction_id:
                p.status = "approved" if approved else "rejected"
                p.admin_note = admin_note
                return {
                    "correction_id": correction_id,
                    "status": p.status,
                    "field": p.field,
                    "record_index": p.record_index,
                    "applied": approved,
                }
        return {"error": "Correction not found"}

    def get_pending(self) -> list[dict]:
        return [asdict(p) for p in self._proposals if p.status == "pending"]

    def pending_count(self) -> int:
        return len([p for p in self._proposals if p.status == "pending"])

    # --- Validation helpers ---

    def _is_fantasy_name(self, name: str) -> bool:
        name_lower = name.lower().strip()
        if not name_lower:
            return True
        for pattern in FANTASY_PATTERNS:
            if pattern in name_lower:
                return True
        # Check if it looks like a real name (at least 2 chars, has space)
        if len(name_lower) < 2:
            return True
        return False

    def _is_valid_email(self, email: str) -> bool:
        if not email or not email.strip():
            return False
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email.strip()))

    def _is_valid_project(self, project: str) -> bool:
        return project.strip() in VALID_PROJECTS

    def _find_closest_project(self, project: str) -> str:
        """Find the closest matching valid project name."""
        project_lower = project.lower().strip()
        best_match = None
        best_score = 0

        for valid in VALID_PROJECTS:
            valid_lower = valid.lower()
            # Simple word overlap score
            words_input = set(project_lower.split())
            words_valid = set(valid_lower.split())
            overlap = len(words_input & words_valid)
            score = overlap / max(len(words_valid), 1)

            if score > best_score:
                best_score = score
                best_match = valid

        return best_match or VALID_PROJECTS[1]  # Default to RAG project