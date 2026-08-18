"""
Retriever setup and vector store configuration.
Supports Qdrant Cloud vector database with local FAISS fallback.
"""

import logging
import os
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.tools import create_retriever_tool
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

logger = logging.getLogger(__name__)

# Compute project root for deterministic file paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DESCRIPTION_PATH = PROJECT_ROOT / "description.txt"

_embeddings = None


def get_embeddings():
    """Lazy-load embeddings model to minimize boot memory footprint on 512MB instances."""
    global _embeddings
    if _embeddings is None:
        google_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if google_api_key:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            _embeddings = GoogleGenerativeAIEmbeddings(
                model="models/gemini-embedding-2",
                google_api_key=google_api_key
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
_vectorstore = None
_cached_retriever_tool = None
_cached_description = None


def _get_qdrant_client_info():
    """Extract Qdrant configuration from environment."""
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")
    collection_name = os.getenv("QDRANT_DOCS_COLLECTION", "guidelines")
    
    # Use a different collection if using Google embeddings to avoid dimension mismatch (768 vs 384)
    if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        collection_name = f"{collection_name}_google"
        
    if url and api_key:
        return url, api_key, collection_name
    return None, None, None


def retriever_chain(chunks: list[Document]):
    """
    Initialize and store documents in Qdrant vector store (or FAISS fallback).

    Invalidates the cached retriever tool so the next get_retriever()
    call picks up the new documents.

    Args:
        chunks: List of document chunks to store.

    Returns:
        Boolean indicating success of the operation.
    """
    global _vectorstore, _cached_retriever_tool

    url, api_key, collection_name = _get_qdrant_client_info()

    if url and api_key:
        try:
            from qdrant_client import QdrantClient
            from langchain_qdrant import QdrantVectorStore
            client = QdrantClient(url=url, api_key=api_key, timeout=3.0)
            _vectorstore = QdrantVectorStore(
                client=client,
                collection_name=collection_name,
                embedding=get_embeddings(),
            )
            _vectorstore.add_documents(chunks)
            _cached_retriever_tool = None
            logger.info("Qdrant Cloud vectorstore initialized with %d chunks (collection: %s)", len(chunks), collection_name)
            return True
        except Exception as e:
            logger.error("Failed to store in Qdrant Cloud, falling back to FAISS: %s", e)

    # Fallback to local FAISS
    try:
        _vectorstore = FAISS.from_documents(
            documents=chunks,
            embedding=get_embeddings(),
        )
        _cached_retriever_tool = None
        logger.info("FAISS vectorstore initialized with %d chunks", len(chunks))
        return True
    except Exception as e:
        logger.error("Error storing documents in FAISS: %s", e)
        return False


def _load_description() -> str | None:
    """Load and cache the document description from disk."""
    global _cached_description
    if _cached_description is not None:
        return _cached_description

    if DESCRIPTION_PATH.exists():
        with open(DESCRIPTION_PATH, "r", encoding="utf-8") as f:
            _cached_description = f.read()
    return _cached_description


def invalidate_description_cache():
    """Clear the cached description (called after upload)."""
    global _cached_description
    _cached_description = None


def get_retriever():
    """
    Get a cached retriever tool connected to the vector store.

    Returns the cached tool if available. Otherwise builds one from
    existing documents or a dummy placeholder.

    Returns:
        A LangChain retriever tool configured for the vector store.
    """
    global _vectorstore, _cached_retriever_tool

    if _cached_retriever_tool is not None:
        return _cached_retriever_tool

    try:
        url, api_key, collection_name = _get_qdrant_client_info()

        if _vectorstore is None and url and api_key:
            try:
                from qdrant_client import QdrantClient
                qc = QdrantClient(url=url, api_key=api_key, timeout=3.0)
                if qc.collection_exists(collection_name):
                    from langchain_qdrant import QdrantVectorStore
                    _vectorstore = QdrantVectorStore(
                        client=qc,
                        collection_name=collection_name,
                        embedding=get_embeddings(),
                    )
                    logger.info("Connected to existing Qdrant Cloud collection: %s", collection_name)
                else:
                    logger.info("Qdrant collection '%s' does not exist yet.", collection_name)
            except Exception as e:
                logger.warning("Could not check/connect to Qdrant collection: %s", e)

        if _vectorstore is not None:
            retriever = _vectorstore.as_retriever(search_kwargs={"k": 3})
            logger.info("Using active vectorstore retriever")
        else:
            logger.info("No documents uploaded, creating placeholder vectorstore")
            dummy_doc = Document(
                page_content="No documents have been uploaded yet. Please upload a document first.",
                metadata={"source": "initialization"},
            )
            placeholder_vs = FAISS.from_documents(
                documents=[dummy_doc],
                embedding=get_embeddings(),
            )
            retriever = placeholder_vs.as_retriever(search_kwargs={"k": 1})

        description = _load_description() or "General Knowledge Base"

        _cached_retriever_tool = create_retriever_tool(
            retriever,
            "retriever_customer_uploaded_documents",
            f"Use this tool **only** to answer questions about: {description}\n"
            "Don't use this tool to answer anything else.",
        )
        return _cached_retriever_tool

    except Exception as e:
        logger.error("Error initializing retriever: %s", e)
        raise
