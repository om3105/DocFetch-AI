"""
Document upload and processing module.
"""

import logging
import os
import tempfile

from fastapi import HTTPException
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.rag.retriever_setup import add_user_documents
from src.tools.common_tools import enhance_description_with_llm

logger = logging.getLogger(__name__)

# Pre-built splitter — reused across uploads instead of re-instantiating
_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)

_LOADERS = {
    ".pdf": PyPDFLoader,
    ".docx": Docx2txtLoader,
    ".txt": lambda path: TextLoader(path, encoding="utf-8"),
    ".md": lambda path: TextLoader(path, encoding="utf-8"),
}

SUPPORTED_EXTENSIONS = set(_LOADERS)


def process_document(
    user_id: str,
    description: str,
    filename: str,
    file_bytes: bytes,
    model_id: str | None = None,
) -> str:
    """
    Parse, chunk and index a document for one user.

    Blocking (file parsing, LLM call, embeddings) — call it via asyncio.to_thread.

    Args:
        user_id: Firebase uid of the uploader; the chunks are only searchable by them.
        description: User-provided document description.
        filename: Name of the uploaded file.
        file_bytes: File contents in bytes.
        model_id: The user's selected LLM, used to enhance the description.

    Returns:
        The LLM-enhanced description, for storing alongside the document record.
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext not in _LOADERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Accepted: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
        tmp_file.write(file_bytes)
        tmp_path = tmp_file.name

    try:
        docs = _LOADERS[ext](tmp_path).load()
    except Exception as e:
        logger.error("Failed to parse '%s': %s", filename, e)
        raise HTTPException(status_code=422, detail="Failed to process the uploaded file")
    finally:
        os.unlink(tmp_path)

    for doc in docs:
        doc.metadata["source"] = filename

    chunks = _splitter.split_documents(docs)
    if not chunks:
        raise HTTPException(status_code=422, detail="No readable text found in the file")

    logger.info("Processing '%s': %d pages/sections, %d chunks", filename, len(docs), len(chunks))

    try:
        add_user_documents(user_id, chunks)
    except Exception as e:
        logger.error("Failed to index '%s': %s", filename, e)
        raise HTTPException(status_code=502, detail="Failed to store the document — please try again")

    return enhance_description_with_llm(description, model_id)
