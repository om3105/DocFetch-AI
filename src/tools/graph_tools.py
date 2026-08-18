"""
Tools for graph routing and document grading.
"""

import logging
from typing import Literal

from src.models.state import State

logger = logging.getLogger(__name__)


def routing_tool(state: State) -> Literal["retriever", "general_llm", "web_search"]:
    """
    Route the graph to the appropriate node based on query classification.

    Args:
        state (State): The current state of the graph.

    Returns:
        The next node to execute: "retriever", "general_llm", or "web_search".
    """
    route = state["route"]
    if route == "index":
        return "retriever"
    elif route == "general":
        return "general_llm"
    return "web_search"


def doc_tool(state: State) -> Literal["rewrite", "generate"]:
    """
    Determine whether the query needs rewriting based on grading score.

    Args:
        state (State): The current state of the graph.

    Returns:
        The next node: "generate" if score is "yes", otherwise "rewrite".
    """
    score = state["binary_score"]
    logger.debug("Routing based on score: %s", score)
    if score == "yes":
        return "generate"
    return "rewrite"
