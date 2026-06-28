"""
RAG pipeline for document indexing, retrieval, and grounded answers.

Foundry Local is the primary runtime. A deterministic local fallback keeps the
demo, tests, and UI usable on machines where the SDK or model cache is not ready.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


EMBEDDING_MODEL = "qwen3-embedding-0.6b"
CHAT_MODEL = "qwen2.5-0.5b"
FALLBACK_DIMENSIONS = 512


@dataclass
class DocumentChunk:
    text: str
    source: str
    chunk_id: int
    embedding: list[float] = field(default_factory=list)
    page: int | None = None


class RAGPipeline:
    def __init__(self, index_path: str | Path | None = None):
        self.index_path = Path(index_path) if index_path else None
        self.chunks: list[DocumentChunk] = []
        self._manager: Any = None
        self._embedding_client: Any = None
        self._chat_client: Any = None
        self._models_loaded = False
        self._runtime = "not_loaded"
        self._load_index()

    # --- Runtime management ---

    def _ensure_models(self):
        """Load Foundry Local models, or use deterministic local fallback."""
        if self._models_loaded:
            return

        if os.getenv("SUMMER_RAG_FORCE_FALLBACK", "").lower() in {"1", "true", "yes"}:
            self._activate_fallback("forced_by_env")
            return

        try:
            from foundry_local_sdk import Configuration, FoundryLocalManager

            config = Configuration(app_name="summer_school_rag")
            FoundryLocalManager.initialize(config)
            self._manager = FoundryLocalManager.instance

            embedding_model = self._manager.catalog.get_model(EMBEDDING_MODEL)
            embedding_model.download(
                lambda p: print(
                    f"\rDownloading embedding model: {p:.1f}%",
                    end="",
                    flush=True,
                )
            )
            print()
            embedding_model.load()
            self._embedding_client = embedding_model.get_embedding_client()

            chat_model = self._manager.catalog.get_model(CHAT_MODEL)
            chat_model.download(
                lambda p: print(
                    f"\rDownloading chat model: {p:.1f}%",
                    end="",
                    flush=True,
                )
            )
            print()
            chat_model.load()
            self._chat_client = chat_model.get_chat_client()

            self._runtime = "foundry_local"
            self._models_loaded = True
        except Exception as exc:
            self._activate_fallback(str(exc))

    def _activate_fallback(self, reason: str):
        self._runtime = "fallback"
        self._models_loaded = True
        self._fallback_reason = reason

    def is_ready(self) -> bool:
        return self._models_loaded

    def runtime_status(self) -> dict:
        return {
            "ready": self._models_loaded,
            "runtime": self._runtime,
            "embedding_model": EMBEDDING_MODEL if self._runtime == "foundry_local" else "local_hashing",
            "chat_model": CHAT_MODEL if self._runtime == "foundry_local" else "extractive_fallback",
            "fallback_reason": getattr(self, "_fallback_reason", None),
        }

    # --- Index lifecycle ---

    def document_count(self) -> int:
        return len({chunk.source for chunk in self.chunks})

    def chunk_count(self) -> int:
        return len(self.chunks)

    def list_documents(self) -> list[str]:
        return sorted({chunk.source for chunk in self.chunks})

    def ingest(self, texts: list[str], source: str):
        """Ingest document chunks into the knowledge base."""
        cleaned_texts = [text.strip() for text in texts if text and text.strip()]
        if not cleaned_texts:
            raise ValueError("No readable text was found in the uploaded file.")

        self._ensure_models()
        self._remove_source(source)
        embeddings = self._embed_texts(cleaned_texts)

        for text, embedding in zip(cleaned_texts, embeddings):
            self.chunks.append(
                DocumentChunk(
                    text=text,
                    source=source,
                    chunk_id=len(self.chunks),
                    embedding=embedding,
                )
            )
        self._renumber_chunks()
        self._save_index()

    def clear(self):
        self.chunks = []
        self._save_index()

    def _remove_source(self, source: str):
        self.chunks = [chunk for chunk in self.chunks if chunk.source != source]
        self._renumber_chunks()

    def _renumber_chunks(self):
        for idx, chunk in enumerate(self.chunks):
            chunk.chunk_id = idx

    def _load_index(self):
        if not self.index_path or not self.index_path.exists():
            return
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            self.chunks = [DocumentChunk(**item) for item in payload.get("chunks", [])]
        except Exception:
            self.chunks = []

    def _save_index(self):
        if not self.index_path:
            return
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"chunks": [asdict(chunk) for chunk in self.chunks]}
        self.index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # --- Embedding and search ---

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self._runtime == "foundry_local" and self._embedding_client:
            response = self._embedding_client.generate_embeddings(texts)
            return [item.embedding for item in response.data]
        return [self._hash_embedding(text) for text in texts]

    def _embed_query(self, question: str) -> list[float]:
        if self._runtime == "foundry_local" and self._embedding_client:
            response = self._embedding_client.generate_embedding(question)
            return response.data[0].embedding
        return self._hash_embedding(question)

    def _hash_embedding(self, text: str) -> list[float]:
        vector = [0.0] * FALLBACK_DIMENSIONS
        for token in self._tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            idx = int(digest[:8], 16) % FALLBACK_DIMENSIONS
            vector[idx] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if not norm:
            return vector
        return [value / norm for value in vector]

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"[a-zA-Z0-9#+.-]+", text.lower())

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

    def _find_relevant(self, query_embedding: list[float], top_k: int = 4) -> list[tuple[int, float]]:
        scores = [
            (idx, self._cosine_similarity(query_embedding, chunk.embedding))
            for idx, chunk in enumerate(self.chunks)
        ]
        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[:top_k]

    # --- Question answering ---

    def query(self, question: str, top_k: int = 4) -> tuple[str, list[dict]]:
        """Query the RAG pipeline and return (answer, sources)."""
        if not question or not question.strip():
            raise ValueError("Question cannot be empty.")

        self._ensure_models()

        if not self.chunks:
            return "No documents have been indexed yet. Upload a document first.", []

        query_embedding = self._embed_query(question)
        results = self._find_relevant(query_embedding, top_k=top_k)
        relevant = [(self.chunks[idx], score) for idx, score in results if score > 0]
        if not relevant:
            return "I do not know based on the indexed documents.", []

        sources = [
            {
                "source": chunk.source,
                "chunk_id": chunk.chunk_id,
                "score": round(score, 4),
                "text": self._preview(chunk.text),
            }
            for chunk, score in relevant
        ]

        context = "\n\n".join(
            f"[Source: {chunk.source}, chunk {chunk.chunk_id}]\n{chunk.text}"
            for chunk, _ in relevant
        )

        if self._runtime == "foundry_local" and self._chat_client:
            answer = self._answer_with_foundry(question, context)
        else:
            answer = self._answer_with_fallback(question, relevant)

        return answer, sources

    def _answer_with_foundry(self, question: str, context: str) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a precise assistant for a Microsoft summer school project. "
                    "Answer using only the provided context. If the answer is not in the "
                    "context, say that you do not know based on the indexed documents. "
                    "Mention the source names that support your answer.\n\n"
                    f"Context:\n{context}"
                ),
            },
            {"role": "user", "content": question},
        ]

        answer = ""
        for chunk in self._chat_client.complete_streaming_chat(messages):
            content = chunk.choices[0].delta.content
            if content:
                answer += content
        return answer.strip() or "I do not know based on the indexed documents."

    def _answer_with_fallback(self, question: str, relevant: list[tuple[DocumentChunk, float]]) -> str:
        best_snippets = []
        for chunk, score in relevant[:3]:
            best_snippets.append(
                f"- {self._preview(chunk.text, limit=320)} [source: {chunk.source}, score: {score:.2f}]"
            )
        return (
            "Foundry Local is not loaded, so I am using the built-in local retrieval "
            "fallback for this demo. Relevant grounded snippets:\n"
            + "\n".join(best_snippets)
        )

    def _preview(self, text: str, limit: int = 220) -> str:
        text = " ".join(text.split())
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."
