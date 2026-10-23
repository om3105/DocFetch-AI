"""
Retriever setup and vector store configuration.

Documents are isolated per user: every chunk is tagged with the uploader's
Firebase uid and every search is filtered to that uid.

Uses Qdrant Cloud when QDRANT_URL and QDRANT_API_KEY are set; otherwise
falls back to an in-memory FAISS index per user (local development only —
FAISS data is lost on restart).
"""

import logging
import os
import time

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.tools import create_retriever_tool
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

logger = logging.getLogger(__name__)

USER_ID_KEY = "metadata.user_id"

_embeddings = None


def _embedding_provider() -> str:
    """Pick the embeddings provider from available keys: NVIDIA, then Google, then local."""
    if os.getenv("NVIDIA_API_KEY"):
        return "nvidia"
    if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        return "google"
    return "local"


class _RetryingEmbeddings(Embeddings):
    """
    Embed in small batches, retrying with backoff on rate limits, so large
    uploads survive the NVIDIA free tier's per-minute request limit.
    """

    BATCH_SIZE = 50
    MAX_ATTEMPTS = 6

    def __init__(self, inner: Embeddings):
        self.inner = inner

    def _with_retry(self, fn, *args):
        for attempt in range(self.MAX_ATTEMPTS):
            try:
                return fn(*args)
            except Exception as e:
                if "429" not in str(e) or attempt == self.MAX_ATTEMPTS - 1:
                    raise
                delay = 2 ** attempt
                logger.warning("Embeddings rate-limited, retrying in %ds", delay)
                time.sleep(delay)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            vectors.extend(self._with_retry(self.inner.embed_documents, texts[i:i + self.BATCH_SIZE]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._with_retry(self.inner.embed_query, text)


def get_embeddings():
    """Lazy-load embeddings model to minimize boot memory footprint on 512MB instances."""
    global _embeddings
    if _embeddings is None:
        provider = _embedding_provider()
        if provider == "nvidia":
            from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
            _embeddings = _RetryingEmbeddings(NVIDIAEmbeddings(
                model="nvidia/nemotron-3-embed-1b",
                api_key=os.getenv("NVIDIA_API_KEY"),
                truncate="END",
            ))
            logger.info("Initialized NVIDIA Embeddings (nemotron-3-embed-1b).")
        elif provider == "google":
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            _embeddings = GoogleGenerativeAIEmbeddings(
                model="models/gemini-embedding-2",
                google_api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"),
            )
            logger.info("Initialized Google Embeddings (gemini-embedding-2).")
        else:
            try:
                import torch
                torch.set_num_threads(1)
            except Exception:
                pass
            _embeddings = HuggingFaceEmbeddings(
                model_name="all-MiniLM-L6-v2",
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True, "batch_size": 16},
            )
            logger.info("Initialized HuggingFace Embeddings (all-MiniLM-L6-v2).")
    return _embeddings


# Module-level caches
_qdrant_store = None
_faiss_stores: dict[str, FAISS] = {}


def _get_qdrant_client_info():
    """Extract Qdrant configuration from environment."""
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")
    collection_name = os.getenv("QDRANT_DOCS_COLLECTION", "guidelines")

    # Each embeddings provider has its own vector size, so each gets its own collection
    provider = _embedding_provider()
    if provider != "local":
        collection_name = f"{collection_name}_{provider}"

    if url and api_key:
        return url, api_key, collection_name
    return None, None, None


def _get_qdrant_store():
    """
    Connect to the shared Qdrant collection, creating it and the
    user_id payload index on first use. Returns None if Qdrant isn't configured.
    """
    global _qdrant_store
    if _qdrant_store is not None:
        return _qdrant_store

    url, api_key, collection_name = _get_qdrant_client_info()
    if not (url and api_key):
        return None

    from qdrant_client import QdrantClient, models
    from langchain_qdrant import QdrantVectorStore

    client = QdrantClient(url=url, api_key=api_key, timeout=30.0)
    if not client.collection_exists(collection_name):
        dim = len(get_embeddings().embed_query("dimension probe"))
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
        )
        logger.info("Created Qdrant collection '%s' (dim=%d)", collection_name, dim)

    # Index the owner field so per-user filtered search stays fast (idempotent)
    client.create_payload_index(
        collection_name=collection_name,
        field_name=USER_ID_KEY,
        field_schema=models.PayloadSchemaType.KEYWORD,
    )

    _qdrant_store = QdrantVectorStore(
        client=client,
        collection_name=collection_name,
        embedding=get_embeddings(),
    )
    logger.info("Connected to Qdrant collection: %s", collection_name)
    return _qdrant_store


def add_user_documents(user_id: str, chunks: list[Document]) -> None:
    """
    Store document chunks owned by user_id.

    Raises on failure so the upload endpoint can report it, rather than
    silently writing to a store that won't be searched.
    """
    for chunk in chunks:
        chunk.metadata["user_id"] = user_id

    store = _get_qdrant_store()
    if store is not None:
        store.add_documents(chunks)
        logger.info("Stored %d chunks in Qdrant for user %s", len(chunks), user_id)
        return

    existing = _faiss_stores.get(user_id)
    if existing is None:
        _faiss_stores[user_id] = FAISS.from_documents(chunks, get_embeddings())
    else:
        existing.add_documents(chunks)
    logger.info("Stored %d chunks in local FAISS for user %s", len(chunks), user_id)


def get_user_retriever(user_id: str):
    """
    Return a retriever that only searches user_id's documents,
    or None if the user has no documents in the active store.
    """
    store = _get_qdrant_store()
    if store is not None:
        from qdrant_client import models
        user_filter = models.Filter(must=[
            models.FieldCondition(key=USER_ID_KEY, match=models.MatchValue(value=user_id)),
        ])
        return store.as_retriever(search_kwargs={"k": 3, "filter": user_filter})

    faiss_store = _faiss_stores.get(user_id)
    if faiss_store is None:
        return None
    return faiss_store.as_retriever(search_kwargs={"k": 3})


def make_retriever_tool(retriever, description: str):
    """Wrap a user's retriever as a tool for the ReAct agent."""
    return create_retriever_tool(
        retriever,
        "retriever_customer_uploaded_documents",
        f"Use this tool **only** to answer questions about: {description}\n"
        "Don't use this tool to answer anything else.",
    )
