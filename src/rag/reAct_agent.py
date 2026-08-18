"""
ReAct agent setup for document retrieval and question answering.
"""

import logging
import os
from pathlib import Path

from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate

from src.config.settings import Config
from src.llms.openai import get_llm, get_active_model_id

logger = logging.getLogger(__name__)

# Compute project root for deterministic file paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]

config = Config()

# Lazy-initialized agent — rebuilt when active LLM changes
_agent_executor = None
_agent_model_id = None


def get_agent_executor() -> AgentExecutor:
    """
    Lazily build and cache the ReAct agent executor.

    Rebuilds the executor when the active LLM changes so
    model switching takes effect immediately.

    Returns:
        AgentExecutor instance for the currently active LLM.
    """
    global _agent_executor, _agent_model_id
    current_model = get_active_model_id()

    if _agent_executor is not None and _agent_model_id == current_model:
        return _agent_executor

    from src.rag.retriever_setup import get_retriever

    tools = [get_retriever()]

    prompt = ChatPromptTemplate.from_messages([
        ("system", config.prompt("system_prompt")),
        ("human", "{input}"),
        ("ai", "{agent_scratchpad}"),
    ])

    react_agent = create_react_agent(get_llm(), tools, prompt)
    _agent_executor = AgentExecutor(
        agent=react_agent,
        tools=tools,
        handle_parsing_errors=True,
        max_iterations=2,
        verbose=False,
        return_intermediate_steps=True,
    )
    _agent_model_id = current_model

    logger.info("ReAct agent executor initialized with model: %s", current_model)
    return _agent_executor
