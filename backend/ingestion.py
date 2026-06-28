"""
Document Parser - Extracts text from multiple file formats.
Supports: PDF, TXT, CSV, XLSX, HTML, DOCX
"""

import os
from typing import Optional


class DocumentParser:
    """Parse documents into text chunks for RAG indexing."""

    def parse(self, file_path: str) -> list[str]:
        """Parse a file and return a list of text chunks."""
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf":
            return self._parse_pdf(file_path)
        elif ext == ".txt":
            return self._parse_txt(file_path)
        elif ext == ".csv":
            return self._parse_csv(file_path)
        elif ext in (".xlsx", ".xls"):
            return self._parse_xlsx(file_path)
        elif ext in (".html", ".htm"):
            return self._parse_html(file_path)
        elif ext == ".docx":
            return self._parse_docx(file_path)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    def parse_records(self, file_path: str) -> list[dict]:
        """Parse a CSV/XLSX file into structured records for correction analysis."""
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".csv":
            return self._csv_to_records(file_path)
        elif ext in (".xlsx", ".xls"):
            return self._xlsx_to_records(file_path)
        else:
            raise ValueError(f"Records file must be CSV or XLSX, got: {ext}")

    # --- Text extraction ---

    def _parse_pdf(self, file_path: str) -> list[str]:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        chunks = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text().strip()
            if text:
                chunks.extend(self._chunk_text(text, page_size=page_num + 1))
        doc.close()
        return chunks

    def _parse_txt(self, file_path: str) -> list[str]:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        return self._chunk_text(text)

    def _parse_csv(self, file_path: str) -> list[str]:
        import pandas as pd
        df = pd.read_csv(file_path)
        chunks = []
        for _, row in df.iterrows():
            row_text = " | ".join(f"{col}: {val}" for col, val in row.items())
            chunks.append(row_text)
        return chunks

    def _parse_xlsx(self, file_path: str) -> list[str]:
        import pandas as pd
        xls = pd.ExcelFile(file_path)
        chunks = []
        for sheet in xls.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet)
            for _, row in df.iterrows():
                row_text = " | ".join(f"{col}: {val}" for col, val in row.items())
                chunks.append(f"[Sheet: {sheet}] {row_text}")
        return chunks

    def _parse_html(self, file_path: str) -> list[str]:
        from bs4 import BeautifulSoup
        with open(file_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator="\n").strip()
        return self._chunk_text(text)

    def _parse_docx(self, file_path: str) -> list[str]:
        from docx import Document
        doc = Document(file_path)
        full_text = "\n".join(para.text for para in doc.paragraphs if para.text.strip())
        return self._chunk_text(full_text)

    # --- Structured records ---

    def _csv_to_records(self, file_path: str) -> list[dict]:
        import pandas as pd
        df = pd.read_csv(file_path)
        return df.to_dict(orient="records")

    def _xlsx_to_records(self, file_path: str) -> list[dict]:
        import pandas as pd
        df = pd.read_excel(file_path)
        return df.to_dict(orient="records")

    # --- Chunking ---

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50, page_size: int = 0) -> list[str]:
        """Split text into overlapping chunks."""
        words = text.split()
        if not words:
            return []

        chunks = []
        start = 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            chunk = " ".join(words[start:end])
            if page_size:
                chunk = f"[Page {page_size}] {chunk}"
            chunks.append(chunk)
            start += chunk_size - overlap
        return chunks