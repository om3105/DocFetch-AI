"""
Chat history storage using MongoDB backend with instant in-memory fallback.
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, messages_from_dict

from src.db.mongo_client import db

logger = logging.getLogger(__name__)

collection = db["chat_history"]

# In-memory storage fallback if MongoDB connection fails
_in_memory_store: Dict[str, List[BaseMessage]] = {}
_mongo_disabled = False
_index_created = False


async def _ensure_indexes():
    """Create compound index on first use (idempotent)."""
    global _index_created, _mongo_disabled
    if _mongo_disabled or _index_created:
        return
    try:
        await collection.create_index([("session_id", 1), ("timestamp", 1)])
        _index_created = True
    except Exception as e:
        logger.warning("MongoDB unavailable, switching permanently to in-memory history: %s", e)
        _mongo_disabled = True


class MongoDBChatMessageHistory(BaseChatMessageHistory):
    """Chat history backed by MongoDB with instant in-memory fallback."""

    def __init__(self, session_id: str):
        """
        Initialize chat history for a session.

        Args:
            session_id: Unique session identifier.
        """
        self.session_id = session_id
        if session_id not in _in_memory_store:
            _in_memory_store[session_id] = []

    async def add_message(self, message: BaseMessage) -> None:
        """
        Save a message to memory, and asynchronously persist to Mongo if online.

        Args:
            message: The message to save.
        """
        global _mongo_disabled
        _in_memory_store[self.session_id].append(message)

        if _mongo_disabled:
            return

        try:
            await _ensure_indexes()
            if not _mongo_disabled:
                await collection.insert_one({
                    "session_id": self.session_id,
                    "type": message.type,
                    "content": message.content,
                    "additional_kwargs": message.additional_kwargs,
                    "timestamp": datetime.now(timezone.utc),
                })
        except Exception as e:
            logger.warning("MongoDB write failed, disabling Mongo for session: %s", e)
            _mongo_disabled = True

    async def get_messages(self) -> List[BaseMessage]:
        """
        Load all messages for a session from MongoDB or in-memory fallback.

        Returns:
            List of messages in chronological order.
        """
        global _mongo_disabled
        if not _mongo_disabled:
            try:
                cursor = collection.find(
                    {"session_id": self.session_id}
                ).sort("timestamp", 1)
                docs = await cursor.to_list(length=1000)

                if docs:
                    return messages_from_dict([
                        {
                            "type": d["type"],
                            "data": {
                                "content": d["content"],
                                "additional_kwargs": d.get("additional_kwargs", {}),
                            },
                        }
                        for d in docs
                    ])
            except Exception as e:
                logger.warning("MongoDB read failed, using in-memory history: %s", e)
                _mongo_disabled = True

        return _in_memory_store.get(self.session_id, [])

    async def clear(self) -> None:
        """Delete all messages for a session."""
        global _mongo_disabled
        _in_memory_store[self.session_id] = []
        if not _mongo_disabled:
            try:
                await collection.delete_many({"session_id": self.session_id})
            except Exception as e:
                logger.warning("MongoDB clear failed: %s", e)
                _mongo_disabled = True


class ChatHistory:
    """Factory for MongoDB-backed chat history."""

    @classmethod
    def get_session_history(cls, session_id: str) -> MongoDBChatMessageHistory:
        """
        Get or create chat history for a session.

        Args:
            session_id: Unique session identifier.

        Returns:
            MongoDBChatMessageHistory instance for the session.
        """
        return MongoDBChatMessageHistory(session_id)
