"""
Test cases for Summer School RAG Agent.
Run with: python -m pytest tests/test_rag.py -v
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from correction import CorrectionAgent, VALID_PROJECTS
from ingestion import DocumentParser


class TestCorrectionAgent:
    def setup_method(self):
        self.agent = CorrectionAgent()
        self.records = [
            {"Name": "Furkan Sarica", "Email": "sarica.furkan@icloud.com", "Project": "Building Your First Local RAG Application with Foundry Local"},
            {"Name": "Fantastic Dragon", "Email": "student123@mail.com", "Project": "Quantum"},
            {"Name": "Ahmet Kaya", "Email": "ahmet.kaya@mail.com", "Project": "Stock"},
            {"Name": "", "Email": "invalid-email", "Project": "Unknown Project"},
        ]
        self.agent.load_records("test_file", self.records)

    def test_fantasy_name_detection(self):
        proposals = self.agent.analyze("test_file")
        fantasy_proposals = [p for p in proposals if p["issue_type"] == "fantasy_name"]
        assert len(fantasy_proposals) > 0
        assert any(p["current_value"] == "Fantastic Dragon" for p in fantasy_proposals)

    def test_empty_name_detection(self):
        proposals = self.agent.analyze("test_file")
        empty_names = [p for p in proposals if p["issue_type"] == "fantasy_name" and p["current_value"] == ""]
        assert len(empty_names) > 0

    def test_invalid_email_detection(self):
        proposals = self.agent.analyze("test_file")
        email_issues = [p for p in proposals if p["issue_type"] == "invalid_email"]
        assert any(p["current_value"] == "invalid-email" for p in email_issues)

    def test_invalid_project_detection(self):
        proposals = self.agent.analyze("test_file")
        project_issues = [p for p in proposals if p["issue_type"] == "invalid_project"]
        assert len(project_issues) > 0

    def test_valid_record_not_flagged(self):
        proposals = self.agent.analyze("test_file")
        # Furkan's record should not have any issues
        furkan_issues = [p for p in proposals if p["record_index"] == 0]
        assert len(furkan_issues) == 0

    def test_project_matching(self):
        proposals = self.agent.analyze("test_file")
        # "Quantum" should match "Quantum Kickstart with Q#"
        quantum = [p for p in proposals if p["current_value"] == "Quantum"]
        if quantum:
            assert quantum[0]["proposed_value"] == "Quantum Kickstart with Q#"

    def test_approval_flow(self):
        proposals = self.agent.analyze("test_file")
        if proposals:
            cid = proposals[0]["correction_id"]
            result = self.agent.process_approval(cid, True, "Approved by admin")
            assert result["status"] == "approved"
            assert result["applied"] is True

    def test_rejection_flow(self):
        proposals = self.agent.analyze("test_file")
        if proposals:
            cid = proposals[0]["correction_id"]
            result = self.agent.process_approval(cid, False, "Rejected")
            assert result["status"] == "rejected"

    def test_pending_count(self):
        self.agent.analyze("test_file")
        initial = self.agent.pending_count()
        assert initial > 0


class TestDocumentParser:
    def setup_method(self):
        self.parser = DocumentParser()

    def test_txt_parsing(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("This is a test document. It has multiple words.")
        chunks = self.parser.parse(str(test_file))
        assert len(chunks) > 0
        assert "test document" in chunks[0].lower()

    def test_csv_parsing(self, tmp_path):
        test_file = tmp_path / "test.csv"
        test_file.write_text("Name,Email,Project\nFurkan,furkan@test.com,RAG\nAhmet,ahmet@test.com,Quantum\n")
        chunks = self.parser.parse(str(test_file))
        assert len(chunks) >= 2

    def test_csv_records(self, tmp_path):
        test_file = tmp_path / "records.csv"
        test_file.write_text("Name,Email,Project\nFurkan,furkan@test.com,RAG\n")
        records = self.parser.parse_records(str(test_file))
        assert len(records) == 1
        assert records[0]["Name"] == "Furkan"

    def test_unsupported_file(self, tmp_path):
        test_file = tmp_path / "test.xyz"
        test_file.write_text("content")
        try:
            self.parser.parse(str(test_file))
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_chunking_overlap(self):
        text = "word " * 1000  # 1000 words
        chunks = self.parser._chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) > 1
        # Each chunk should have roughly 100 words
        assert len(chunks[0].split()) <= 100