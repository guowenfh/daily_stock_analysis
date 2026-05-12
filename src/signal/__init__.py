"""Unified Signal System V1.

Bilibili content → structured signals → single-asset events.
"""
from src.signal.models import (
    ContentCreator,
    Content,
    ContentMedia,
    ContentTranscript,
    SignalMention,
    SignalEvent,
    ensure_signal_tables,
)


def init_signal_db():
    """Call during app startup to ensure signal tables exist."""
    from src.storage import DatabaseManager
    try:
        db = DatabaseManager.get_instance()
        ensure_signal_tables(db._engine)
    except Exception:
        pass


__all__ = [
    "ContentCreator",
    "Content",
    "ContentMedia",
    "ContentTranscript",
    "SignalMention",
    "SignalEvent",
    "ensure_signal_tables",
    "init_signal_db",
]
