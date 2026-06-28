"""
RAG Pipeline - Document ingestion, embedding, search, and grounded response generation.
Uses Microsoft Foundry Local SDK for on-device LLM and embedding models.
"""

import math
import os
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class DocumentChunk:
    text: str
    source: str
    chunk_id: int
    embedding: list = field(default_factory=list)


class RAGPipeline:
    def __init__(self):
        self.chunks: list[DocumentChunk] = []
        self._manager = None
        self._embedding_client = None
        self._chat_client = None
        self._models_loaded = False

    def _ensure_models(self):
        """Lazy-load Foundry Local models on first use."""
        if self._models_loaded:
            return

        from foundry_local_sdk import Configuration, FoundryLocalManager

        config = Configuration(app_name="summer_school_rag")
        FoundryLocalManager.initialize(config)
        self._manager = FoundryLocalManager.instance

        # Load embedding model
        emb_model = self._manager.catalog.get_model("qwen3-embedding-0.6b")
        emb_model.download(
            lambda p: print(f"\rDownloading embedding model: {p:.1f}%", end="", flush=True)
        )
        print()
        emb_model.load()
        self._embedding_client = emb_model.get_embedding_client()

        # Load chat model
        chat_model = self._manager.catalog.get_model("qwen2.5-0.5b")
        chat_model.download(
            lambda p: print(f"\rDownloading chat model: {p:.1f}%", end="", flush=True)
        )
        print()
        chat_model.load()
        self._chat_client = chat_model.get_chat_client()

        self._models_loaded = True
        print("✓ Foundry Local models loaded.")

    def is_ready(self) -> bool:
        return self._models_loaded

    def document_count(self) -> int:
        return len({c.source for c in self.chunks})

    def list_documents(self) -> list[str]:
        return sorted({c.source for c in self.chunks})

    def ingest(self, texts: list[str], source: str):
        """Ingest document chunks into the knowledge base."""
        self._ensure_models()

        # Generate embeddings in batch
        response = self._embedding_client.generate_embeddings(texts)
        for i, (text, emb_data) in enumerate(zip(texts, response.data)):
            chunk = DocumentChunk(
                text=text,
                source=source,
                chunk_id=len(self.chunks),
                embedding=emb_data.embedding,
            )
            self.chunks.append(chunk)
        print(f"✓ Indexed {len(texts)} chunks from {source}.")

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

    def _find_relevant(self, query_embedding: list[float], top_k: int = 3) -> list[tuple[int, float]]:
        scores = []
        for i, chunk in enumerate(self.chunks):
            score = self._cosine_similarity(query_embedding, chunk.embedding)
            scores.append((i, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def query(self, question: str, top_k: int = 3) -> tuple[str, list[dict]]:
        """Query the RAG pipeline and return (answer, sources)."""
        self._ensure_models()

        if not self.chunks:
            return "No documents have been indexed yet. Please upload a document first.", []

        # Embed the query
        query_response = self._embedding_client.generate_embedding(question)
        query_embedding = query_response.data[0].embedding

        # Retrieve relevant chunks
        results = self._find_relevant(query_embedding, top_k=top_k)
        context_parts = []
        sources = []
        for idx, score in results:
            chunk = self.chunks[idx]
            context_parts.append(f"[{chunk.source}] {chunk.text}")
            sources.append({
                "source": chunk.source,
                "chunk_id": chunk.chunk_id,
                "score": round(score, 4),
                "text": chunk.text[:200] + "..." if len(chunk.text) > 200 else chunk.text,
            })

        context = "\n\n".join(context_parts)

        # Build prompt
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant for a Microsoft summer school program. "
                    "Answer the user's question using ONLY the provided context. "
                    "If the context doesn't contain enough information, say you don't know. "
                    "Always cite the source document.\n\n"
                    f"Context:\n{context}"
                ),
            },
            {"role": "user", "content": question},
        ]

        # Generate response
        answer = ""
        for chunk in self._chat_client.complete_streaming_chat(messages):
            content = chunk.choices[0].delta.content
            if content:
                answer += content

        return answer, sources