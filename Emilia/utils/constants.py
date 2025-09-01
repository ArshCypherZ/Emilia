# Centralized collection names, key fields, and filter helpers
from types import SimpleNamespace
from typing import Dict, Any

COLL = SimpleNamespace(
    admincache="admincache",
    chatlevels="chatlevels",
    users="users",
    chats="chats",
    flood_msgs="flood_msgs",
    locks="locks",
    blocklists="blocklists",
    warnings="warnings",
    notes="notes",
    filters="filters",
    welcome="welcome",
)

KEY_FIELDS = {"user_id", "chat_id", "message_id", "fed_id"}


def _to_int_safe(v):
    try:
        # Accept numeric strings
        if isinstance(v, str) and v.strip().lstrip("-+").isdigit():
            return int(v)
        if isinstance(v, bool):
            # avoid treating True/False as 1/0
            return v
        return int(v) if isinstance(v, (int,)) else v
    except Exception:
        return v


def normalize_filter(f: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce common id fields to consistent types for queries.
    - chat_id/user_id/message_id -> int when possible
    - fed_id -> str
    Leaves other fields untouched.
    """
    nf: Dict[str, Any] = dict(f)
    for k, v in list(nf.items()):
        if k in ("chat_id", "user_id", "message_id"):
            nf[k] = _to_int_safe(v)
        elif k == "fed_id" and v is not None:
            nf[k] = str(v)
    return nf
