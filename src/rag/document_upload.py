"""
Document upload and processing module.
"""

import logging
import os
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, File
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.rag.retriever_setup import retriever_chain, invalidate_description_cache
from src.tools.common_tools import enhance_description_with_llm

logger = logging.getLogger(__name__)

# Compute project root for deterministic file paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DESCRIPTION_PATH = PROJECT_ROOT / "description.txt"

# Pre-built splitter — reused across uploads instead of re-instantiating
_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)

_SUPPORTED_EXTENSIONS = {".pdf", ".txt"}


def documents(description: str, filename: str, file_bytes: bytes):
    """
    Process and upload a document for RAG.

    Args:
        description: User-provided document description.
        filename: Name of the uploaded file.
        file_bytes: File contents in bytes.

    Returns:
        Boolean indicating success of the upload process.
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext not in _SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and TXT files are supported",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
        tmp_file.write(file_bytes)
        tmp_path = tmp_file.name

    loader = PyPDFLoader(tmp_path) if ext == ".pdf" else TextLoader(tmp_path, encoding="utf-8")

    try:
        docs = loader.load()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to process the uploaded file")
    finally:
        os.unlink(tmp_path)

    # Enhance and persist description
    description_llm = enhance_description_with_llm(description)
    with open(DESCRIPTION_PATH, "w", encoding="utf-8") as f:
        f.write(description_llm)

    # Invalidate cached description so retriever picks up the new one
    invalidate_description_cache()

    logger.info("Processing '%s': %d pages/sections loaded", filename, len(docs))

    chunks = _splitter.split_documents(docs)
    return retriever_chain(chunks)
