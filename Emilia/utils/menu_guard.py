"""Guards for inline menus: who may drive one, and how fast.

Two problems show up on every inline menu the bot sends into a group.

1. *Ownership.* A menu pages through one person's library and acts on their
   account. Everyone in the chat can see it, so without a check anyone can drive
   someone else's open menu. Ownership is recorded against the message rather
   than packed into callback_data, which Telegram caps at 64 bytes and which is
   usually already full of verb + id + argument.

2. *Impatience.* A button whose handler takes a second invites a second tap, and
   a handler that sends a message then sends it twice. `claim_tap` is a one-shot
   lock per (scope, button) that expires on its own, so a slow handler can never
   wedge a button permanently shut.
"""

from Emilia import redis_client

MENU_TTL = 86400  # a day-old menu is scrollback, not a live workspace
TAP_TTL = 5  # long enough to cover a slow handler, short enough to not annoy


def _menu_key(chat_id: int, message_id: int) -> str:
    return f"menu_owner:{chat_id}:{message_id}"


async def remember_menu(message, user_id: int, ttl: int = MENU_TTL) -> None:
    """Record that `user_id` owns the menu in `message`."""
    await redis_client.setex(_menu_key(message.chat.id, message.id), ttl, str(user_id))


async def menu_owner_ok(query) -> bool:
    """
    True if this tapper may drive this menu.

    Private chats have exactly one participant, so the question only arises in
    groups. An expired menu — one older than MENU_TTL, or sent before a restart
    that cleared Redis — is allowed through: silently bricking someone's buttons
    is worse than the nuisance this prevents.
    """
    if not query.message or query.message.chat.type.name == "PRIVATE":
        return True
    owner = await redis_client.get(_menu_key(query.message.chat.id, query.message.id))
    if not owner:
        return True
    if isinstance(owner, bytes):
        owner = owner.decode()
    return str(query.from_user.id) == owner


async def claim_tap(scope: int, key: str, ttl: int = TAP_TTL) -> bool:
    """
    True for the first tap of a button, False for repeats while it's still busy.

    Use around handlers that *produce* something (an upload, a new message, a
    queue insert). In-place menu edits are idempotent and don't need it.

    `scope` is whatever the button belongs to: a user id for a personal menu, a
    chat id for a shared control panel where two people hammering Skip should
    still only skip once.
    """
    return bool(await redis_client.set(f"menu_tap:{scope}:{key}", "1", ex=ttl, nx=True))
