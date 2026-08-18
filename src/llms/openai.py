"""
LLM initialization — supports Groq and Google Gemini (2.5 Flash).

The active LLM can be switched at runtime via `set_active_llm()`.
"""

import os
import re
import logging
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)

load_dotenv()
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "")

# ── Available LLMs ──────────────────────────────────────────────────────────

# Use currently supported active Groq model
_groq_llm = ChatGroq(model="qwen/qwen3.6-27b", temperature=0)
_gemini_llm = None  # Lazy-loaded to avoid import error if key missing

AVAILABLE_MODELS = {
    "groq": {"name": "Qwen 2.5 27B · Groq", "provider": "Groq"},
    "gemini": {"name": "Gemini 2.5 Flash", "provider": "Google"},
}


def _get_gemini():
    """Lazy-load Gemini LLM on first use."""
    global _gemini_llm
    if _gemini_llm is None:
        api_key = os.getenv("GOOGLE_API_KEY", "")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set in .env")
        from langchain_google_genai import ChatGoogleGenerativeAI
        _gemini_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=api_key,
            temperature=0,
            max_retries=1,
        )
    return _gemini_llm


from langchain_core.runnables import Runnable

# ── Active LLM management ──────────────────────────────────────────────────

_active_model: str = "groq"


def _parse_schema_from_text(schema, text):
    """Fallback extractor for structured Pydantic models from raw text."""
    cleaned = re.sub(r'<think>.*?</think>', '', str(text), flags=re.DOTALL).strip()
    fields = getattr(schema, 'model_fields', {})
    if 'route' in fields:
        for choice in ['index', 'general', 'search']:
            if choice in cleaned.lower():
                return schema(route=choice)
        return schema(route='general')
    if 'binary_score' in fields:
        if 'yes' in cleaned.lower():
            return schema(binary_score='yes')
        return schema(binary_score='no')
    try:
        return schema.model_validate_json(cleaned)
    except Exception:
        pass
    return schema()


class ResilientStructured(Runnable):
    """Runnable wrapper for structured output with automatic fallback and text extraction."""

    def __init__(self, primary, fallback, schema, raw_llm):
        self.primary = primary
        self.fallback = fallback
        self.schema = schema
        self.raw_llm = raw_llm

    def invoke(self, input, config=None, **kwargs):
        # 1. Try primary structured invoke
        if self.primary is not None:
            try:
                return self.primary.invoke(input, config, **kwargs)
            except Exception as ex:
                err_str = str(ex)
                if 'failed_generation' in err_str:
                    return _parse_schema_from_text(self.schema, err_str)
                logger.warning("Primary structured LLM call failed (%s), trying fallback", ex)

        # 2. Try fallback structured invoke
        if self.fallback is not None:
            try:
                return self.fallback.invoke(input, config, **kwargs)
            except Exception as ex:
                err_str = str(ex)
                if 'failed_generation' in err_str:
                    return _parse_schema_from_text(self.schema, err_str)
                logger.warning("Fallback structured LLM call failed (%s), using direct text parser", ex)

        # 3. Direct raw LLM invoke with regex/text schema parser
        try:
            res = self.raw_llm.invoke(input, config, **kwargs)
            content = getattr(res, 'content', str(res))
            return _parse_schema_from_text(self.schema, content)
        except Exception as ex:
            logger.error("All structured LLM strategies failed (%s), returning default schema", ex)
            return _parse_schema_from_text(self.schema, 'general')


class ResilientLLM(Runnable):
    """Runnable wrapper that delegates to the active LLM with seamless fallback to Groq."""

    def __init__(self, primary_fn, fallback_llm):
        self._primary_fn = primary_fn
        self._fallback_llm = fallback_llm

    def _get_primary(self):
        return self._primary_fn()

    def invoke(self, input, config=None, **kwargs):
        try:
            res = self._get_primary().invoke(input, config, **kwargs)
            if hasattr(res, 'content') and isinstance(res.content, str):
                res.content = re.sub(r'<think>.*?</think>', '', res.content, flags=re.DOTALL).strip()
            return res
        except Exception as e:
            logger.warning("Primary LLM invocation failed (%s), falling back to Groq", e)
            res = self._fallback_llm.invoke(input, config, **kwargs)
            if hasattr(res, 'content') and isinstance(res.content, str):
                res.content = re.sub(r'<think>.*?</think>', '', res.content, flags=re.DOTALL).strip()
            return res

    def with_structured_output(self, schema, **kwargs):
        fallback_struct = None
        try:
            fallback_struct = self._fallback_llm.with_structured_output(schema, **kwargs)
        except Exception:
            pass

        primary_struct = None
        try:
            primary_struct = self._get_primary().with_structured_output(schema, **kwargs)
        except Exception as e:
            logger.warning("Primary structured output init failed (%s), using Groq fallback", e)

        return ResilientStructured(primary_struct, fallback_struct, schema, self._fallback_llm)




def get_llm():
    """Return the currently active LLM instance (with fallback if primary fails)."""
    if _active_model == "gemini":
        return ResilientLLM(_get_gemini, _groq_llm)
    return ResilientLLM(lambda: _groq_llm, _groq_llm)


def set_active_llm(model_id: str):
    """Switch the active LLM. Returns the model info dict."""
    global _active_model
    if model_id not in AVAILABLE_MODELS:
        raise ValueError(f"Unknown model: {model_id}")
    _active_model = model_id
    return AVAILABLE_MODELS[model_id]


def get_active_model_id() -> str:
    """Return the current model ID string."""
    return _active_model


# Default export for backward compatibility
llm = _groq_llm