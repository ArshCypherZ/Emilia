"""One way to say "this broke": log it, and put it in the log channel.

Background handlers — voice-chat stream events, prefetch tasks, anything not
driven by a command — never pass through the `exception` decorator, so an
`except Exception` in one of them used to be where the traceback died. The user
saw a polite message and nobody ever learned why.

`str(exc)` is deliberately not trusted here: `FileNotFoundError` and a few
pytgcalls errors stringify to the empty string, which is how a real playback bug
once reached the logs as `Failed to auto-play next track in -100…: `. The type
name is always included.
"""

import html
import logging
import traceback

from Emilia import EVENT_LOGS, pgram

LOGGER = logging.getLogger(__name__)


async def report_error(scope: str, exc: BaseException, **context) -> None:
    """Log `exc` with its traceback and forward it to the log channel."""
    detail = " ".join(f"{k}={v}" for k, v in context.items())
    LOGGER.error(
        "[%s] %s: %s %s", scope, type(exc).__name__, exc, detail, exc_info=exc
    )
    await forward_traceback(
        scope,
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        detail,
    )


async def forward_traceback(scope: str, tb: str, detail: str = "") -> None:
    """Send a formatted traceback to the log channel, never raising."""
    body = html.escape(tb[-3500:])
    header = f"#ERROR #{scope.upper().replace('.', '_')}"
    if detail:
        header += f"\n{html.escape(detail)}"
    try:
        await pgram.send_message(EVENT_LOGS, f"{header}\n\n<pre>{body}</pre>")
    except Exception as e:
        LOGGER.warning("[%s] could not reach the log channel: %s", scope, e)
