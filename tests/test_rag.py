"""
Test cases for Summer School RAG Agent.

Run with:
    python -m pytest -v
"""

import os
import sys

os.environ["SUMMER_RAG_FORCE_FALLBACK"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from correction import CorrectionAgent
from ingestion import DocumentParser
from rag import RAGPipeline


class TestCorrectionAgent:
    def setup_method(self):
        self.agent = CorrectionAgent()
        self.records = [
            {
                "Name": "Ada Yilmaz",
                "Email": "ada.yilmaz@example.com",
                "Project": "Building Your First Local RAG Application with Foundry Local",
            },
            {"Name": "Fantastic Dragon", "Email": "student123@mail.com", "Project": "Quantum"},
            {"Name": "Ahmet Kaya", "Email": "ahmet.kaya@mail.com", "Project": "Stock"},
            {"Name": "", "Email": "invalid-email", "Project": "Unknown Project"},
        ]
        self.agent.load_records("test_file", self.records, filename="students.csv")

    def test_suspicious_name_detection(self):
        proposals = self.agent.analyze("test_file")
        name_proposals = [p for p in proposals if p["issue_type"] == "suspicious_name"]
        assert any(p["current_value"] == "Fantastic Dragon" for p in name_proposals)

    def test_empty_name_detection(self):
        proposals = self.agent.analyze("test_file")
        empty_names = [
            p
            for p in proposals
            if p["issue_type"] == "suspicious_name" and p["current_value"] == ""
        ]
        assert len(empty_names) == 1

    def test_invalid_email_detection(self):
        proposals = self.agent.analyze("test_file")
        email_issues = [p for p in proposals if p["issue_type"] == "invalid_email"]
        assert any(p["current_value"] == "invalid-email" for p in email_issues)

    def test_project_standardization(self):
        proposals = self.agent.analyze("test_file")
        quantum = [p for p in proposals if p["current_value"] == "Quantum"]
        stock = [p for p in proposals if p["current_value"] == "Stock"]
        assert quantum[0]["proposed_value"] == "Quantum Kickstart with Q#"
        assert stock[0]["proposed_value"] == "Stock Price Prediction with PyTorch"

    def test_valid_record_not_flagged(self):
        proposals = self.agent.analyze("test_file")
        valid_record_issues = [p for p in proposals if p["record_index"] == 0]
        assert valid_record_issues == []

    def test_analysis_does_not_duplicate_pending_items(self):
        first = self.agent.analyze("test_file")
        second = self.agent.analyze("test_file")
        assert len(first) == len(second)
        assert self.agent.pending_count() == len(second)

    def test_approval_applies_safe_project_patch(self):
        proposals = self.agent.analyze("test_file")
        quantum = [p for p in proposals if p["current_value"] == "Quantum"][0]
        result = self.agent.process_approval(quantum["correction_id"], True, "Approved")
        assert result["status"] == "approved"
        assert result["applied"] is True
        assert self.agent.get_records("test_file")[1]["Project"] == "Quantum Kickstart with Q#"

    def test_manual_correction_is_not_auto_applied(self):
        proposals = self.agent.analyze("test_file")
        manual = [p for p in proposals if p["proposed_value"].startswith("[REQUIRES")][0]
        result = self.agent.process_approval(manual["correction_id"], True, "Needs human data")
        assert result["status"] == "approved"
        assert result["applied"] is False

    def test_rejection_stays_out_of_future_pending_list(self):
        proposals = self.agent.analyze("test_file")
        rejected = proposals[0]
        self.agent.process_approval(rejected["correction_id"], False, "Rejected")
        refreshed = self.agent.analyze("test_file")
        assert all(p["correction_id"] != rejected["correction_id"] for p in refreshed)

    def test_export_csv(self):
        csv_text = self.agent.export_csv("test_file")
        assert "Ada Yilmaz" in csv_text
        assert "Project" in csv_text


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
        assert len(chunks) == 2
        assert chunks[0].startswith("[Row 1]")

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

    def test_empty_file_raises(self, tmp_path):
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")
        try:
            self.parser.parse(str(test_file))
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_chunking_overlap(self):
        text = "word " * 1000
        chunks = self.parser._chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) > 1
        assert len(chunks[0].split()) <= 100


class TestRAGPipeline:
    def test_fallback_rag_returns_grounded_sources(self):
        rag = RAGPipeline()
        rag.ingest(
            [
                "Foundry Local lets developers run language and embedding models on device.",
                "The summer school final presentation is a five minute demo.",
            ],
            source="guide.txt",
        )
        answer, sources = rag.query("What does Foundry Local run?")
        assert "fallback" in answer.lower()
        assert len(sources) >= 1
        assert sources[0]["source"] == "guide.txt"
