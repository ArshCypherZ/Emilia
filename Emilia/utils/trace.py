"""Per-update correlation id.

Set around each handled update in custom_filter.unified_wrapper so all log lines
a single update produces (command log, cache errors, flush errors it triggers)
can be correlated. Deterministic ("{chat_id}:{message_id}") — no uuid cost.
"""

from contextvars import ContextVar
from typing import Optional

TRACE_ID: ContextVar[Optional[str]] = ContextVar("emilia_trace_id", default=None)
