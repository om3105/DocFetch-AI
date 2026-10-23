"""
LLM initialization — a pool of free-tier models on NVIDIA and Groq.

Free tiers are rate-limited per model (NVIDIA allows roughly 10 requests/minute
per model; Groq ~7,000 input tokens/minute), so each request walks a chain of
models: the user's preferred one first, then the others. A rate-limited model
is skipped until its cooldown passes, and if every model is cooling down the
request waits for the first one to free up instead of failing.

The user chooses a provider ("nvidia" or "groq") via `get_llm(model_id)`.
"""

import os
import re
import time
import logging
from dotenv import load_dotenv
from langchain_core.runnables import Runnable

logger = logging.getLogger(__name__)

load_dotenv()

# ── Available LLMs ──────────────────────────────────────────────────────────

AVAILABLE_MODELS = {
    "nvidia": {"name": "MiniMax M3.1 Flash · NVIDIA", "provider": "NVIDIA"},
    "groq": {"name": "Qwen 3.8 27B · Groq", "provider": "Groq"},
}

DEFAULT_MODEL: str = "nvidia"

# Pool members: name -> (provider, provider model id). Ordered fastest first.
_POOL = {
    "minimax": ("nvidia", "minimaxai/minimax-m3.1-flash"),
    "glm": ("nvidia", "z-ai/glm-5.3-flash"),
    "qwen": ("groq", "qwen/qwen3.8-27b"),
    # Correct but ~8s per call, so only used when the faster models are busy
    "nemotron": ("nvidia", "nvidia/nemotron-3.5-lightning-30b-a3b"),
}

# Order in which pool members are tried for each user-selectable choice
_CHAINS = {
    "nvidia": ["minimax", "glm", "qwen", "nemotron"],
    "groq": ["qwen", "minimax", "glm", "nemotron"],
}

# NVIDIA-hosted models reject tool/JSON-schema requests, so structured
# output is parsed from their plain-text answers instead
_SUPPORTS_STRUCTURED = {"nvidia": False, "groq": True}

# Per-call limit: free-tier calls occasionally queue for 30-50s; past this,
# give up on that model and let the pool try the next one
_CALL_TIMEOUT_SECONDS = 25

_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

_instances: dict = {}


def _get_model(name: str):
    """Lazy-create a pool member's chat model (fails if its API key is missing)."""
    if name not in _instances:
        provider, model = _POOL[name]
        if provider == "nvidia":
            api_key = os.getenv("NVIDIA_API_KEY", "")
            if not api_key:
                raise ValueError("NVIDIA_API_KEY not set in .env")
            # NVIDIA's API is OpenAI-compatible; this client (unlike ChatNVIDIA)
            # supports a request timeout. These are reasoning models: low effort
            # cuts hidden "thinking" from ~1-2k tokens to near zero, and the higher
            # cap keeps any remaining reasoning from crowding out the answer.
            from langchain_openai import ChatOpenAI
            _instances[name] = ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=_NVIDIA_BASE_URL,
                temperature=0,
                max_tokens=4096,
                reasoning_effort="low",
                timeout=_CALL_TIMEOUT_SECONDS,
                max_retries=0,
            )
        else:
            api_key = os.getenv("GROQ_API_KEY", "")
            if not api_key:
                raise ValueError("GROQ_API_KEY not set in .env")
            from langchain_groq import ChatGroq
            # max_retries=0: fail fast on rate limits and move to the next model
            _instances[name] = ChatGroq(
                model=model, api_key=api_key, temperature=0,
                timeout=_CALL_TIMEOUT_SECONDS, max_retries=0,
            )
    return _instances[name]


# ── Rate-limit cooldown ─────────────────────────────────────────────────────

_DEFAULT_COOLDOWN_SECONDS = 20.0
# Longest a request waits for a model to free up when the whole pool is busy
_MAX_POOL_WAIT_SECONDS = 20.0
_cooldown_until: dict[str, float] = {}


def _is_rate_limit(ex: Exception) -> bool:
    err = str(ex)
    return "429" in err or "Too Many Requests" in err or "RESOURCE_EXHAUSTED" in err


def _cooling_down(name: str) -> bool:
    return time.monotonic() < _cooldown_until.get(name, 0.0)


def _note_failure(name: str, ex: Exception) -> None:
    """Skip a rate-limited model for the delay its error asks for (default 20s)."""
    if not _is_rate_limit(ex):
        return
    match = re.search(r"(?:retry|try again) in ([\d.]+)s", str(ex))
    seconds = float(match.group(1)) if match else _DEFAULT_COOLDOWN_SECONDS
    _cooldown_until[name] = time.monotonic() + seconds
    logger.warning("%s rate-limited; skipping it for %.0fs", name, seconds)


def _run_with_pool(chain: list[str], call):
    """
    Run call(name) on the first model in chain that succeeds, skipping
    models in cooldown. While every model is rate-limited, keep waiting for
    the first to free up, for at most _MAX_POOL_WAIT_SECONDS in total.
    """
    deadline = time.monotonic() + _MAX_POOL_WAIT_SECONDS
    while True:
        ready = [n for n in chain if not _cooling_down(n)]
        if not ready:
            wait = min(_cooldown_until[n] for n in chain) - time.monotonic()
            wait = max(0.0, min(wait, deadline - time.monotonic()))
            logger.warning("All models rate-limited; waiting %.1fs", wait)
            time.sleep(wait)
            ready = chain
        last_error = None
        for name in ready:
            try:
                return call(name)
            except Exception as ex:
                _note_failure(name, ex)
                logger.warning("%s failed (%s), trying next model", name, ex)
                last_error = ex
        # Only rate limits are worth waiting out; other errors fail immediately
        if not _is_rate_limit(last_error) or time.monotonic() >= deadline:
            raise last_error


# ── Output helpers ──────────────────────────────────────────────────────────

def _strip_think(res):
    """
    Remove <think>…</think> reasoning blocks some models include in content.
    Raises on an empty answer so the pool moves on to the next model.
    """
    if hasattr(res, 'content') and isinstance(res.content, str):
        res.content = re.sub(r'<think>.*?</think>', '', res.content, flags=re.DOTALL).strip()
        if not res.content:
            raise ValueError("Model returned an empty response")
    return res


def _first_word_match(text: str, choices: list[str]) -> str | None:
    """Return whichever choice appears first in text as a whole word."""
    hits = [(m.start(), c) for c in choices if (m := re.search(rf"\b{c}\b", text))]
    return min(hits)[1] if hits else None


def _parse_schema_from_text(schema, text):
    """Extract a structured Pydantic model from a raw text answer."""
    cleaned = re.sub(r'<think>.*?</think>', '', str(text), flags=re.DOTALL).strip().lower()
    fields = getattr(schema, 'model_fields', {})
    if 'route' in fields:
        return schema(route=_first_word_match(cleaned, ['index', 'general', 'search']) or 'general')
    if 'binary_score' in fields:
        return schema(binary_score=_first_word_match(cleaned, ['yes', 'no']) or 'no')
    try:
        return schema.model_validate_json(cleaned)
    except Exception:
        pass
    return schema()


# ── Resilient wrappers ──────────────────────────────────────────────────────

class ResilientStructured(Runnable):
    """Structured output over the model pool, parsing plain text where needed."""

    def __init__(self, chain: list[str], schema):
        self.chain = chain
        self.schema = schema

    def _invoke_one(self, name, input, config, **kwargs):
        model = _get_model(name)
        if _SUPPORTS_STRUCTURED[_POOL[name][0]]:
            try:
                return model.with_structured_output(self.schema).invoke(input, config, **kwargs)
            except Exception as ex:
                # Groq reports schema-validation failures with the raw generation attached
                if 'failed_generation' in str(ex):
                    return _parse_schema_from_text(self.schema, str(ex))
                if _is_rate_limit(ex):
                    raise
                logger.warning("Structured output from %s failed (%s), parsing plain text", name, ex)
        res = _strip_think(model.invoke(input, config, **kwargs))
        return _parse_schema_from_text(self.schema, getattr(res, 'content', str(res)))

    def invoke(self, input, config=None, **kwargs):
        try:
            return _run_with_pool(self.chain, lambda name: self._invoke_one(name, input, config, **kwargs))
        except Exception as ex:
            logger.error("All structured LLM strategies failed (%s), returning default schema", ex)
            return _parse_schema_from_text(self.schema, 'general')


class ResilientLLM(Runnable):
    """Runnable that calls the first available model in the pool chain."""

    def __init__(self, chain: list[str]):
        self.chain = chain

    def invoke(self, input, config=None, **kwargs):
        return _run_with_pool(
            self.chain,
            lambda name: _strip_think(_get_model(name).invoke(input, config, **kwargs)),
        )

    def with_structured_output(self, schema, **kwargs):
        return ResilientStructured(self.chain, schema)


def get_llm(model_id: str | None = None):
    """
    Return an LLM that prefers the given provider and falls back across the pool.

    Model choice is per-user and passed in by the caller; unknown or missing
    ids use DEFAULT_MODEL.
    """
    if model_id not in AVAILABLE_MODELS:
        model_id = DEFAULT_MODEL
    return ResilientLLM(_CHAINS[model_id])
