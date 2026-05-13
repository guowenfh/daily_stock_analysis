"""Concurrency guards for LLM and Whisper calls in signal pipeline.

Rules:
- LLM: At most MAX_LLM_CONCURRENCY calls active simultaneously.
- Whisper: Only ONE call active at any time.
"""
import logging
import os
import threading

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
        return litellm.completion(*args, **kwargs)


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
