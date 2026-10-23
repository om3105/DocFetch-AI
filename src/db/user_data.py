"""
Per-user data stored in MongoDB: selected model and uploaded-document records.
"""

from datetime import datetime, timezone

from src.db.mongo_client import db
from src.llms.openai import AVAILABLE_MODELS, DEFAULT_MODEL

settings_col = db["user_settings"]
documents_col = db["documents"]

_indexes_created = False


async def _ensure_indexes():
    """Create indexes on first use (idempotent)."""
    global _indexes_created
    if _indexes_created:
        return
    await documents_col.create_index(
        [("user_id", 1), ("created_at", -1)],
        name="user_documents_by_recency",
    )
    _indexes_created = True


async def get_user_model(user_id: str) -> str:
    """Return the user's selected model id, or the default."""
    doc = await settings_col.find_one({"_id": user_id})
    model_id = doc.get("model_id") if doc else None
    return model_id if model_id in AVAILABLE_MODELS else DEFAULT_MODEL


async def set_user_model(user_id: str, model_id: str) -> None:
    """Persist the user's selected model id."""
    await settings_col.update_one(
        {"_id": user_id},
        {"$set": {"model_id": model_id}},
        upsert=True,
    )


async def add_document_record(user_id: str, filename: str, description: str, enhanced: str) -> dict:
    """Record an uploaded document and return it in API form."""
    await _ensure_indexes()
    doc = {
        "user_id": user_id,
        "filename": filename,
        "description": description,
        "enhanced_description": enhanced,
        "created_at": datetime.now(timezone.utc),
    }
    result = await documents_col.insert_one(doc)
    return {
        "id": str(result.inserted_id),
        "filename": filename,
        "description": description,
        "created_at": doc["created_at"],
    }


async def list_documents(user_id: str) -> list[dict]:
    """Return the user's uploaded documents, newest first."""
    await _ensure_indexes()
    docs = await documents_col.find(
        {"user_id": user_id},
        {"filename": 1, "description": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(length=500)
    return [
        {
            "id": str(d["_id"]),
            "filename": d["filename"],
            "description": d.get("description", ""),
            "created_at": d["created_at"],
        }
        for d in docs
    ]


async def get_doc_description(user_id: str) -> str | None:
    """
    Combine the user's document descriptions into one retriever-tool
    description, or None if they have no documents.
    """
    docs = await documents_col.find(
        {"user_id": user_id},
        {"filename": 1, "enhanced_description": 1},
    ).sort("created_at", -1).to_list(length=50)
    if not docs:
        return None
    return "\n".join(f"- {d['filename']}: {d['enhanced_description']}" for d in docs)
