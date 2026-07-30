# backend/services/vectorstore.py
"""
Manages the ChromaDB vector store: chunking documents, generating
embeddings via local HuggingFace models, storing them, and
running semantic search queries across uploaded files.
"""

import hashlib
import math
import re

from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

CHROMA_PERSIST_DIR = "./memory/chroma_db"
EMBEDDING_DIMENSIONS = 384

_embeddings: Embeddings | None = None

_text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150,
)


class HashingEmbeddings(Embeddings):
    """Offline fallback embedding function for Chroma."""

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSIONS
        tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def get_embeddings() -> Embeddings:
    """Loads HuggingFace embeddings lazily, falling back to offline hashing."""
    global _embeddings
    if _embeddings is not None:
        return _embeddings

    try:
        _embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"local_files_only": True},
        )
    except Exception:
        _embeddings = HashingEmbeddings()

    return _embeddings


def get_vectorstore() -> Chroma:
    """Returns the persistent Chroma vector store instance."""
    return Chroma(
        collection_name="uploaded_files",
        embedding_function=get_embeddings(),
        persist_directory=CHROMA_PERSIST_DIR,
    )


def get_personalization_store() -> Chroma:
    """Returns a separate persistent store for user/session preferences."""
    return Chroma(
        collection_name="personalization",
        embedding_function=get_embeddings(),
        persist_directory=CHROMA_PERSIST_DIR,
    )


def add_file_to_vectorstore(
    file_path: str, text_content: str, session_id: str
) -> int:
    """
    Splits text content into chunks and stores them in the vector store
    with metadata (file path, session) for later filtering/retrieval.

    Returns the number of chunks added.
    """
    if not text_content.strip():
        return 0

    chunks = _text_splitter.split_text(text_content)
    documents = [
        Document(
            page_content=chunk,
            metadata={"source": file_path, "session_id": session_id},
        )
        for chunk in chunks
    ]

    store = get_vectorstore()
    store.add_documents(documents)
    return len(documents)


def search_relevant_chunks(query: str, session_id: str, k: int = 5) -> list[dict]:
    """
    Performs semantic search over uploaded files for a given session,
    returning the top-k most relevant chunks.
    """
    store = get_vectorstore()
    results = store.similarity_search(
        query, k=k, filter={"session_id": session_id}
    )
    return [
        {"content": doc.page_content, "source": doc.metadata.get("source")}
        for doc in results
    ]


def add_personalization_memory(
    *, session_id: str, user_request: str, summary: str
) -> None:
    """Stores a compact memory for future personalization."""
    if not session_id or not summary.strip():
        return
    document = Document(
        page_content=f"Request: {user_request}\nGenerated project: {summary}",
        metadata={"session_id": session_id, "kind": "generated_project"},
    )
    get_personalization_store().add_documents([document])


def search_personalization(query: str, session_id: str, k: int = 3) -> list[str]:
    """Finds relevant user/session preferences and prior project memories."""
    if not session_id:
        return []
    store = get_personalization_store()
    results = store.similarity_search(query, k=k, filter={"session_id": session_id})
    return [doc.page_content for doc in results]


def delete_session_memory(session_id: str) -> None:
    """Best-effort deletion of uploaded-file and personalization vectors."""
    for store_factory in (get_vectorstore, get_personalization_store):
        try:
            store = store_factory()
            store._collection.delete(where={"session_id": session_id})
        except Exception:
            continue
