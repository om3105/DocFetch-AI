"""
API routes for RAG operations.
"""

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Header
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel

from src.auth import verify_firebase_token
from src.core.rate_limiter import limiter
from src.memory.chat_history_mongo import ChatHistory
from src.models.query_request import QueryRequest
from src.rag.document_upload import documents
from src.rag.graph_builder import builder
from src.llms.openai import (
    AVAILABLE_MODELS, set_active_llm, get_active_model_id,
)

router = APIRouter()

# ── Upload constraints ──────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


# ── Model switching ─────────────────────────────────────────────────────────

class ModelSwitchRequest(BaseModel):
    """Request model for switching the active LLM."""
    model_id: str


@router.get("/models")
@limiter.limit("30/minute")
async def list_models(request: Request, user: dict = Depends(verify_firebase_token)):
    """List available LLM models and the currently active one."""
    return {
        "models": AVAILABLE_MODELS,
        "active": get_active_model_id(),
    }


@router.post("/models/switch")
@limiter.limit("10/minute")
async def switch_model(
    request: Request,
    req: ModelSwitchRequest,
    user: dict = Depends(verify_firebase_token),
):
    """Switch the active LLM model."""
    info = set_active_llm(req.model_id)
    return {"active": req.model_id, **info}


# ── RAG queries ─────────────────────────────────────────────────────────────

@router.post("/rag/query")
@limiter.limit("10/minute")
async def rag_query(request: Request, req: QueryRequest, user: dict = Depends(verify_firebase_token)):
    """
    Process a RAG query and return the result.
    Requires Firebase authentication.

    Args:
        request: The incoming HTTP request (needed for rate-limiter key extraction).
        req: The query request containing query text and session_id.
        user: Decoded Firebase token (injected via dependency).

    Returns:
        The generated response from the RAG pipeline.
    """
    # Use Firebase uid as session scope for chat history
    session_id = user["uid"]
    chat_history = ChatHistory.get_session_history(session_id)
    await chat_history.add_message(HumanMessage(content=req.query))

    # Fetch full history
    messages = await chat_history.get_messages()
    result = await asyncio.to_thread(builder.invoke, {
        "messages": messages
    })
    output_text = result["messages"][-1].content

    # Save assistant message
    await chat_history.add_message(AIMessage(content=output_text))

    return {"result": result["messages"][-1]}


# ── Document upload ─────────────────────────────────────────────────────────

@router.post("/rag/documents/upload")
@limiter.limit("5/minute")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    description: str = Header(..., alias="X-Description"),
    user: dict = Depends(verify_firebase_token),
):
    """
    Upload a document for RAG processing.
    Requires Firebase authentication.

    Args:
        request: The incoming HTTP request (needed for rate-limiter key extraction).
        file: The file to upload (PDF, TXT, MD, DOCX).
        description: Document description provided via header.
        user: Decoded Firebase token (injected via dependency).

    Returns:
        Upload status.
    """
    # Validate file extension
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit")
    await file.seek(0)  # Reset stream position for downstream processing

    # Validate description length
    if len(description) > 500:
        raise HTTPException(status_code=400, detail="Description exceeds 500 character limit")

    status_upload = documents(description, file.filename, content)
    return {"status": status_upload}
