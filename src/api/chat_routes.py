"""
Chat conversation CRUD routes — ChatGPT-style multi-conversation system.

All endpoints enforce account isolation by including user_id in every
MongoDB query filter. A user can never access another user's conversations.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from src.auth import verify_firebase_token
from src.core.rate_limiter import limiter
from src.db.mongo_client import db
from src.llms.openai import get_llm

logger = logging.getLogger(__name__)

chat_router = APIRouter(prefix="/chats", tags=["chats"])

# ── MongoDB collections ────────────────────────────────────────────────────

conversations_col = db["conversations"]
messages_col = db["messages"]

_indexes_created = False


async def _ensure_indexes():
    """Create indexes on first request (idempotent)."""
    global _indexes_created
    if _indexes_created:
        return
    try:
        await conversations_col.create_index(
            [("user_id", 1), ("updated_at", -1)],
            name="user_conversations_by_recency",
        )
        await messages_col.create_index(
            [("conversation_id", 1), ("created_at", 1)],
            name="messages_chronological",
        )
        await messages_col.create_index(
            [("user_id", 1), ("conversation_id", 1)],
            name="messages_user_isolation",
        )
        _indexes_created = True
    except Exception as e:
        logger.warning("Index creation failed (non-fatal): %s", e)


# ── Request / Response models ──────────────────────────────────────────────

class CreateChatRequest(BaseModel):
    """Optional title when creating a new chat."""
    title: Optional[str] = None


class SendMessageRequest(BaseModel):
    """User message to send to the AI."""
    query: str

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        import re
        v = v.strip()
        if not v:
            raise ValueError("Query cannot be empty")
        if len(v) > 4000:
            raise ValueError("Query exceeds 4000 character limit")
        v = re.sub(r"<[^>]+>", "", v)
        return v


class RenameChatRequest(BaseModel):
    """New title for a conversation."""
    title: str

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title cannot be empty")
        if len(v) > 200:
            raise ValueError("Title exceeds 200 character limit")
        return v


# ── Helper: ObjectId validation ────────────────────────────────────────────

def _validate_object_id(chat_id: str) -> ObjectId:
    """Validate and convert a string to ObjectId."""
    try:
        return ObjectId(chat_id)
    except Exception:
        raise HTTPException(400, "Invalid conversation ID format")


def _serialize_doc(doc: dict) -> dict:
    """Convert MongoDB document to JSON-safe dict."""
    doc["id"] = str(doc.pop("_id"))
    if "conversation_id" in doc:
        doc["conversation_id"] = str(doc["conversation_id"])
    return doc


# ── Helper: Auto-title generation ─────────────────────────────────────────

async def _generate_title(user_message: str) -> str:
    """
    Use the active LLM to auto-generate a concise chat title
    from the first user message (ChatGPT-style).
    """
    import asyncio
    try:
        prompt = (
            f'Generate a concise title (5-8 words max) for a conversation '
            f'that starts with: "{user_message[:200]}". '
            f'Return ONLY the title text, nothing else. No quotes.'
        )
        result = await asyncio.to_thread(get_llm().invoke, prompt)
        title = result.content.strip().strip('"').strip("'")
        return title[:100] if title else "New Chat"
    except Exception as e:
        logger.warning("Auto-title generation failed: %s", e)
        return "New Chat"


# ── 1. POST /api/chats — Create a new conversation ────────────────────────

@chat_router.post("")
@limiter.limit("10/minute")
async def create_chat(
    request: Request,
    body: CreateChatRequest = CreateChatRequest(),
    user: dict = Depends(verify_firebase_token),
):
    """Create a new empty conversation thread."""
    await _ensure_indexes()

    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user["uid"],
        "title": body.title or "New Chat",
        "created_at": now,
        "updated_at": now,
    }
    result = await conversations_col.insert_one(doc)
    doc["_id"] = result.inserted_id

    return _serialize_doc(doc)


# ── 2. GET /api/chats — List conversations (cursor-paginated) ─────────────

@chat_router.get("")
@limiter.limit("30/minute")
async def list_chats(
    request: Request,
    limit: int = 20,
    cursor: Optional[str] = None,
    user: dict = Depends(verify_firebase_token),
):
    """
    Fetch all conversation threads for the logged-in user,
    ordered by updated_at descending. Supports cursor-based pagination.

    Query params:
        limit: Max conversations per page (default 20, max 100)
        cursor: ISO timestamp of last item from previous page
    """
    await _ensure_indexes()

    limit = min(max(1, limit), 100)
    query = {"user_id": user["uid"]}

    # Cursor-based pagination: fetch items older than cursor
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            query["updated_at"] = {"$lt": cursor_dt}
        except ValueError:
            raise HTTPException(400, "Invalid cursor format")

    docs = await conversations_col.find(query)\
        .sort("updated_at", -1)\
        .limit(limit)\
        .to_list(length=limit)

    chats = [_serialize_doc(d) for d in docs]

    # Build next cursor from last item
    next_cursor = None
    if len(chats) == limit:
        last = chats[-1]
        next_cursor = last["updated_at"].isoformat() if isinstance(last["updated_at"], datetime) else str(last["updated_at"])

    return {"chats": chats, "next_cursor": next_cursor}


# ── 3. GET /api/chats/{id} — Get conversation + messages ──────────────────

@chat_router.get("/{chat_id}")
@limiter.limit("30/minute")
async def get_chat(
    request: Request,
    chat_id: str,
    msg_limit: int = 50,
    msg_cursor: Optional[str] = None,
    user: dict = Depends(verify_firebase_token),
):
    """
    Fetch a conversation and its message history.
    Account isolation: user_id must match.
    Supports cursor-based pagination on messages.
    """
    oid = _validate_object_id(chat_id)

    # Account isolation enforcement
    conversation = await conversations_col.find_one({
        "_id": oid,
        "user_id": user["uid"],
    })
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    # Fetch messages with optional cursor pagination
    msg_limit = min(max(1, msg_limit), 200)
    msg_query = {
        "conversation_id": oid,
        "user_id": user["uid"],
    }
    if msg_cursor:
        try:
            cursor_dt = datetime.fromisoformat(msg_cursor)
            msg_query["created_at"] = {"$gt": cursor_dt}
        except ValueError:
            raise HTTPException(400, "Invalid msg_cursor format")

    msg_docs = await messages_col.find(msg_query)\
        .sort("created_at", 1)\
        .limit(msg_limit)\
        .to_list(length=msg_limit)

    messages = [_serialize_doc(m) for m in msg_docs]

    next_msg_cursor = None
    if len(messages) == msg_limit:
        last_msg = messages[-1]
        ts = last_msg["created_at"]
        next_msg_cursor = ts.isoformat() if isinstance(ts, datetime) else str(ts)

    chat_data = _serialize_doc(conversation)
    chat_data["messages"] = messages
    chat_data["next_msg_cursor"] = next_msg_cursor

    return chat_data


# ── 4. POST /api/chats/{id}/messages — Send message + get AI response ─────

@chat_router.post("/{chat_id}/messages")
@limiter.limit("10/minute")
async def send_message(
    request: Request,
    chat_id: str,
    body: SendMessageRequest,
    user: dict = Depends(verify_firebase_token),
):
    """
    Save the user message, invoke the RAG pipeline, save the AI response.
    Auto-generates a title on the first message (ChatGPT-style).
    """
    from langchain_core.messages import HumanMessage, AIMessage
    from src.rag.graph_builder import builder

    oid = _validate_object_id(chat_id)
    await _ensure_indexes()

    # Account isolation enforcement
    conversation = await conversations_col.find_one({
        "_id": oid,
        "user_id": user["uid"],
    })
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    now = datetime.now(timezone.utc)
    uid = user["uid"]

    # Save user message
    user_msg_doc = {
        "conversation_id": oid,
        "user_id": uid,
        "role": "user",
        "content": body.query,
        "created_at": now,
    }
    await messages_col.insert_one(user_msg_doc)

    # Load conversation history for RAG context
    history_docs = await messages_col.find({
        "conversation_id": oid,
        "user_id": uid,
    }).sort("created_at", 1).to_list(length=100)

    # Convert to LangChain messages for the RAG pipeline
    lc_messages = []
    for doc in history_docs:
        if doc["role"] == "user":
            lc_messages.append(HumanMessage(content=doc["content"]))
        else:
            lc_messages.append(AIMessage(content=doc["content"]))

    # Invoke RAG pipeline without blocking event loop
    import asyncio
    result = await asyncio.to_thread(builder.invoke, {"messages": lc_messages})
    ai_content = result["messages"][-1].content

    # Save AI response
    ai_now = datetime.now(timezone.utc)
    ai_msg_doc = {
        "conversation_id": oid,
        "user_id": uid,
        "role": "assistant",
        "content": ai_content,
        "created_at": ai_now,
    }
    await messages_col.insert_one(ai_msg_doc)

    # Update conversation timestamp
    update_fields = {"updated_at": ai_now}

    # Auto-generate title on first message (if still "New Chat")
    generated_title = None
    if conversation.get("title") == "New Chat":
        generated_title = await _generate_title(body.query)
        update_fields["title"] = generated_title

    await conversations_col.update_one(
        {"_id": oid, "user_id": uid},
        {"$set": update_fields},
    )

    return {
        "user_message": _serialize_doc(user_msg_doc),
        "ai_message": _serialize_doc(ai_msg_doc),
        "generated_title": generated_title,
    }


# ── 5. PATCH /api/chats/{id} — Rename conversation ────────────────────────

@chat_router.patch("/{chat_id}")
@limiter.limit("10/minute")
async def rename_chat(
    request: Request,
    chat_id: str,
    body: RenameChatRequest,
    user: dict = Depends(verify_firebase_token),
):
    """Rename a conversation. Account isolation enforced."""
    oid = _validate_object_id(chat_id)

    result = await conversations_col.update_one(
        {"_id": oid, "user_id": user["uid"]},
        {"$set": {
            "title": body.title,
            "updated_at": datetime.now(timezone.utc),
        }},
    )

    if result.matched_count == 0:
        raise HTTPException(404, "Conversation not found")

    return {"id": chat_id, "title": body.title}


# ── 6. DELETE /api/chats/{id} — Delete conversation + messages ─────────────

@chat_router.delete("/{chat_id}")
@limiter.limit("10/minute")
async def delete_chat(
    request: Request,
    chat_id: str,
    user: dict = Depends(verify_firebase_token),
):
    """
    Delete a conversation and all associated messages.
    Account isolation enforced — user can only delete their own chats.
    """
    oid = _validate_object_id(chat_id)
    uid = user["uid"]

    # Delete conversation (with user_id check)
    result = await conversations_col.delete_one({
        "_id": oid,
        "user_id": uid,
    })

    if result.deleted_count == 0:
        raise HTTPException(404, "Conversation not found")

    # Cascade delete all messages (also user_id scoped for safety)
    await messages_col.delete_many({
        "conversation_id": oid,
        "user_id": uid,
    })

    return {"deleted": True, "id": chat_id}
