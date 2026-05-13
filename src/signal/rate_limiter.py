"""Concurrency guards for LLM and Whisper calls in signal pipeline.

Rules:
- LLM: At most MAX_LLM_CONCURRENCY calls active simultaneously.
- Whisper: Only ONE call active at any time.
"""
import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

MAX_LLM_CONCURRENCY = int(os.environ.get("MAX_WORKERS", "2"))

_llm_semaphore = threading.Semaphore(MAX_LLM_CONCURRENCY)
_whisper_lock = threading.Lock()


def rate_limited_completion(*args, **kwargs):
    """Drop-in replacement for litellm.completion() with concurrency control.

    At most MAX_LLM_CONCURRENCY LLM requests can be in-flight simultaneously.
    """
    import litellm

    model = kwargs.get("model") or (args[0] if args else "unknown")
    logger.debug("LLM call queued [model=%s, max_concurrent=%d]", model, MAX_LLM_CONCURRENCY)

    with _llm_semaphore:
        logger.debug("LLM call started [model=%s]", model)
        return litellm.completion(*args, **_with_channel_params(kwargs))


def _with_channel_params(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Inject channel api_base/api_key for direct LiteLLM calls."""
    if kwargs.get("api_base") or kwargs.get("base_url"):
        return kwargs

    model = kwargs.get("model")
    if not model:
        return kwargs

    try:
        from src.config import get_config

        config = get_config()
    except Exception:
        return kwargs

    for entry in getattr(config, "llm_model_list", None) or []:
        params = dict(entry.get("litellm_params") or {})
        if entry.get("model_name") != model and params.get("model") != model:
            continue

        merged = dict(kwargs)
        for key in ("api_key", "api_base", "base_url", "extra_headers"):
            if params.get(key) and not merged.get(key):
                merged[key] = params[key]
        return merged

    return kwargs


def acquire_whisper():
    """Acquire whisper lock (blocking). Returns True when acquired."""
    _whisper_lock.acquire()
    return True


def release_whisper():
    """Release whisper lock."""
    try:
        _whisper_lock.release()
    except RuntimeError:
        pass
