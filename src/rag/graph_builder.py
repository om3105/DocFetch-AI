"""
Graph builder module for the adaptive RAG system.
"""

import logging

from langchain_community.tools import TavilySearchResults
from langchain_core.messages import AIMessage
from langchain_core.prompts import PromptTemplate
from langgraph.constants import START, END
from langgraph.graph.state import StateGraph

from src.rag.retriever_setup import get_user_retriever, make_retriever_tool
from src.config.settings import Config
from src.llms.openai import get_llm
from src.models.grade import Grade
from src.models.route_identifier import RouteIdentifier
from src.models.state import State
from src.tools.graph_tools import routing_tool, doc_tool

logger = logging.getLogger(__name__)

config = Config()


# How many recent messages to show the LLM when resolving follow-up questions
HISTORY_WINDOW = 10


# Node implementations
def contextualize(state: State):
    """
    Turn the latest message into a standalone question using recent history,
    so follow-ups like "tell me more" retrieve the right documents.

    Args:
        state (State): The current state of the graph.

    Returns:
        dict: latest_query set to the standalone question.
    """
    messages = state["messages"]
    question = messages[-1].content
    if len(messages) < 2:
        return {"latest_query": question}

    history = "\n".join(
        f"{'User' if m.type == 'human' else 'Assistant'}: {m.content}"
        for m in messages[-HISTORY_WINDOW - 1:-1]
    )
    prompt = PromptTemplate(
        template=config.prompt("contextualize_prompt"),
        input_variables=["history", "question"],
    )
    result = (prompt | get_llm(state.get("model_id"))).invoke({"history": history, "question": question})
    standalone = result.content.strip() or question
    logger.debug("Standalone question: %s", standalone)
    return {"latest_query": standalone}


def _user_retriever_tool(state: State):
    """Retriever tool over the requesting user's documents, or None if they have none."""
    if not state.get("doc_description"):
        return None
    retriever = get_user_retriever(state["user_id"])
    if retriever is None:
        return None
    return make_retriever_tool(retriever, state["doc_description"])


def query_classifier(state: State):
    """
    Classify the query to determine if it's related to indexed documents.

    Args:
        state (State): The current state of the graph.

    Returns:
        dict: Updated state with route.
    """
    question = state["latest_query"]
    retriever_tool = _user_retriever_tool(state)
    context = ""
    if retriever_tool is not None:
        try:
            context = retriever_tool.invoke(question)
        except Exception as e:
            logger.warning("Retriever context search failed/timed out: %s", e)
    logger.debug("Retrieved context for classification: %s", context)

    llm_with_structured_output = get_llm(state.get("model_id")).with_structured_output(RouteIdentifier)
    classify_prompt = PromptTemplate(
        template=config.prompt("classify_prompt"),
        input_variables=["question", "context"],
    )
    chain = classify_prompt | llm_with_structured_output
    result = chain.invoke({"question": question, "context": context})
    route = result.route
    # Without documents there is nothing to retrieve from
    if route == "index" and retriever_tool is None:
        route = "general"
    logger.info("Query classified as: %s", route)

    return {"route": route, "context": context}


def general_llm(state: State):
    """
    Fetch general common knowledge result from the LLM.

    Args:
        state (State): The current state of the graph.

    Returns:
        dict: Updated messages from LLM.
    """
    result = get_llm(state.get("model_id")).invoke(state["messages"])
    return {"messages": result}


def retriever_node(state: State):
    """
    Search the user's documents for the current query.

    The classifier has already decided this is a document question, so this
    searches directly instead of asking an LLM agent whether to search —
    saving two LLM calls per question. The classifier's results are reused
    on the first pass; after a rewrite the new query is searched.

    Args:
        state (State): The current state of the graph.

    Returns:
        dict: Retrieved context as a message, for grading and generation.
    """
    context = state.get("context") if state.get("rewrite_count", 0) == 0 else None
    if not context:
        retriever_tool = _user_retriever_tool(state)
        context = retriever_tool.invoke(state["latest_query"]) if retriever_tool else ""

    return {"messages": [AIMessage(content=context)], "context": context}


def grade(state: State):
    """
    Grade the results retrieved from vector stores.

    Args:
        state (State): The current state of the graph.

    Returns:
        dict: Updated state with binary_score.
    """
    grading_prompt = PromptTemplate(
        template=config.prompt("grading_prompt"),
        input_variables=["question", "context"],
    )
    context = state["messages"][-1].content
    question = state["latest_query"]

    llm_with_grade = get_llm(state.get("model_id")).with_structured_output(Grade)
    chain_graded = grading_prompt | llm_with_grade
    result = chain_graded.invoke({"question": question, "context": context})

    logger.debug("Grading result: %s", result.binary_score)
    return {"binary_score": result.binary_score}


def rewrite_query(state: State):
    """
    Rewrite the query to get better retrieval results.

    Args:
        state (State): State of the question.

    Returns:
        dict: Updated latest_query.
    """
    query = state["latest_query"]
    rewrite_prompt = PromptTemplate(
        template=config.prompt("rewrite_prompt"),
        input_variables=["query"],
    )
    chain = rewrite_prompt | get_llm(state.get("model_id"))
    result = chain.invoke({"query": query})

    logger.debug("Rewritten query: %s", result.content)
    return {"latest_query": result.content, "rewrite_count": state.get("rewrite_count", 0) + 1}


def generate(state: State):
    """
    Generate the final answer for the user.

    Args:
        state (State): State of the question.

    Returns:
        dict: Generated response.
    """
    context = state["messages"][-1].content
    generate_prompt = PromptTemplate(
        template=config.prompt("generate_prompt"),
        input_variables=["question", "context"],
    )
    generate_chain = generate_prompt | get_llm(state.get("model_id"))
    result = generate_chain.invoke({"question": state["latest_query"], "context": context})

    return {"messages": [AIMessage(content=result.content)]}


def web_search(state: State):
    """
    Search the web for the rewritten query.

    Args:
        state (State): The current state of the graph.

    Returns:
        dict: Search results as messages.
    """
    search_tool = TavilySearchResults()
    result = search_tool.invoke(state["latest_query"])

    contents = [item["content"] for item in result if "content" in item]

    return {"messages": [AIMessage(content="\n\n".join(contents))]}


# Build the graph
graph = StateGraph(State)

graph.add_node("contextualize", contextualize)
graph.add_node("query_analysis", query_classifier)
graph.add_node("retriever", retriever_node)
graph.add_node("grade", grade)
graph.add_node("generate", generate)
graph.add_node("rewrite", rewrite_query)
graph.add_node("web_search", web_search)
graph.add_node("general_llm", general_llm)

graph.add_edge(START, "contextualize")
graph.add_edge("contextualize", "query_analysis")
graph.add_edge("web_search", "generate")
graph.add_edge("retriever", "grade")
graph.add_edge("rewrite", "retriever")
graph.add_conditional_edges("query_analysis", routing_tool)
graph.add_conditional_edges("grade", doc_tool)
graph.add_edge("generate", END)
graph.add_edge("general_llm", END)

builder = graph.compile()
