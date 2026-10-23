"""
API routes for model selection and document upload.
"""

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Header
from pydantic import BaseModel

from src.auth import verify_firebase_token
from src.core.rate_limiter import limiter
from src.db.user_data import (
    add_document_record, get_user_model, list_documents, set_user_model,
)
from src.llms.openai import AVAILABLE_MODELS
from src.rag.document_upload import SUPPORTED_EXTENSIONS, process_document

router = APIRouter()

# ── Upload constraints ──────────────────────────────────────────────────────

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


# ── Model switching ─────────────────────────────────────────────────────────

class ModelSwitchRequest(BaseModel):
    """Request model for switching the active LLM."""
    model_id: str


@router.get("/models")
@limiter.limit("30/minute")
async def list_models(request: Request, user: dict = Depends(verify_firebase_token)):
    """List available LLM models and the user's selected one."""
    return {
        "models": AVAILABLE_MODELS,
        "active": await get_user_model(user["uid"]),
    }


@router.post("/models/switch")
@limiter.limit("10/minute")
async def switch_model(
    request: Request,
    req: ModelSwitchRequest,
    user: dict = Depends(verify_firebase_token),
):
    """Switch the user's selected LLM model (affects only this user)."""
    if req.model_id not in AVAILABLE_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {req.model_id}")
    await set_user_model(user["uid"], req.model_id)
    return {"active": req.model_id, **AVAILABLE_MODELS[req.model_id]}


# ── Documents ───────────────────────────────────────────────────────────────

@router.get("/rag/documents")
@limiter.limit("30/minute")
async def get_documents(request: Request, user: dict = Depends(verify_firebase_token)):
    """List the user's uploaded documents."""
    return {"documents": await list_documents(user["uid"])}


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
    The document is only searchable by the uploading user.

    Args:
        request: The incoming HTTP request (needed for rate-limiter key extraction).
        file: The file to upload (PDF, TXT, MD, DOCX).
        description: Document description provided via header.
        user: Decoded Firebase token (injected via dependency).

    Returns:
        Upload status and the stored document record.
    """
    # Validate file extension
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Accepted: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    # Validate description length
    description = description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="Description is required")
    if len(description) > 500:
        raise HTTPException(status_code=400, detail="Description exceeds 500 character limit")

    # Validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit")

    uid = user["uid"]
    model_id = await get_user_model(uid)

    # Parsing, embedding and the LLM call block — keep them off the event loop
    enhanced = await asyncio.to_thread(
        process_document, uid, description, file.filename, content, model_id,
    )
    record = await add_document_record(uid, file.filename, description, enhanced)
    return {"status": True, "document": record}
