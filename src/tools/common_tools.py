"""
Common tools for document and description processing.
"""

import logging

from src.llms.openai import get_llm

logger = logging.getLogger(__name__)


def enhance_description_with_llm(user_description: str) -> str:
    """
    Enhance user-provided document description using LLM.

    Rewrites the description to be suitable as a retriever tool instruction
    that clearly indicates the tool is only for answering questions about
    the uploaded content.

    Args:
        user_description: The original user-provided description.

    Returns:
        Enhanced description formatted as a tool instruction.
    """
    prompt = (
        "Rewrite the following user-provided document description to be used as a retriever tool instruction. "
        "It should clearly state that the tool is only for answering questions about the uploaded content.\n\n"
        f'Description: "{user_description}"\n\n'
        "Tool Instruction:"
    )

    response = get_llm().invoke(prompt)
    logger.info("Enhanced document description via LLM")
    return response.content.strip()