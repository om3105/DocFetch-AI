"""
State model for the graph-based RAG system.
"""

from typing import TypedDict, Annotated, Optional

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages


class State(TypedDict):
    """State schema for the RAG graph."""

    messages: Annotated[list[AnyMessage], add_messages]
    binary_score: Optional[str]
    route: Optional[str]
    latest_query: Optional[str]
    # Per-request context supplied by the API layer
    user_id: str
    model_id: Optional[str]
    # Combined descriptions of the user's documents; None when they have none
    doc_description: Optional[str]
    rewrite_count: int
    # Retrieved document text for latest_query (set by the classifier, refreshed after rewrites)
    context: Optional[str]
