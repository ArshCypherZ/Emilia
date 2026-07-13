import asyncio
import os
import traceback
from datetime import datetime, timezone
from urllib.parse import urlparse

from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.errors import (
    ChatWriteForbidden,
    FloodWait,
    UserIsBlocked,
    UserNotParticipant,
)
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from pymongo.errors import DuplicateKeyError

from Emilia import (
    BOT_USERNAME,
    CLONE_LIMIT,
    CLONE_PREMIUM_ENABLED,
    CLONE_PREMIUM_STARS,
    CLONES_PER_USER,
    DEV_USERS,
    LOGGER,
    SUPPORT_CHAT,
    db,
)
from Emilia.custom_filter import auth, callbackquery, listen, register
from Emilia.modules.commands.clone_manager import (
    _remove_session_files,
    clone_manager,
)
from Emilia.utils import async_http
from Emilia.utils.net_guard import is_safe_url

clone_db = db.clone
startpic = db.startpic
clone_slots = db.clone_slots
clone_payments = db.clone_payments

# {owner_user_id: bot_id} — owners mid-way through setting a clone's start pic
# from the main bot via the /mybots panel. Consumed by the listener below.
_PENDING_STARTPIC = {}

# Cap start-pic uploads so a malicious/huge file can't fill server disk during
# the download+reupload hop. Telegram already compresses `photo` type, but we
# enforce our own ceiling and reject anything sent as a document.
_STARTPIC_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


async def get_clone_info_by_bot_id(bot_id):
    return await clone_db.find_one({"_id": bot_id})


async def get_extra_slots(user_id):
    doc = await clone_slots.find_one({"_id": user_id})
    return doc.get("extra", 0) if doc else 0


async def validate_token(token: str):
    """Returns (ok, status, me_json). status in {'ok','invalid','network'}."""
    try:
        resp = await async_http.get(
            f"https://api.telegram.org/bot{token}/getMe", timeout=15
        )
        data = resp.json()
    except Exception:
        return False, "network", None
    if data.get("ok"):
        return True, "ok", data["result"]
    return False, "invalid", None


@auth(pattern="stats")
async def stats_(client, message):
    users = await db.users.count_documents({})
    chats = await db.chats.count_documents({})
    bots = await clone_db.count_documents({})
    active_clones = len(clone_manager.clones)

    await message.reply_text(
        f"**Bot Statistics**\n\n"
        f"**Chats**: {chats}\n"
        f"**Users**: {users}\n"
        f"**Cloned Bots in Database**: {bots}\n"
        f"**Active Clone Clients**: {active_clones}\n\n"
    )


async def create_clone_client(owner_id, token, bot_id):
    # Validate token over the Bot API (no MTProto handshake).
    ok, status, _ = await validate_token(token)
    if not ok:
        if status == "invalid":
            return False, "invalid", None
        return False, None, None

    # Start clone via manager. start_clone already removes a stale session file
    # on failure, so a single retry recovers from SESSION_REVOKED left by a
    # revoked/regenerated token that is otherwise still valid over the Bot API.
    for attempt in (1, 2):
        try:
            success, bot_username, bot_name = await clone_manager.start_clone(
                owner_id, token, bot_id
            )
            if success:
                return True, bot_username, bot_name
        except Exception as e:
            LOGGER.error(
                f"Error starting clone {bot_id} for owner {owner_id} "
                f"(attempt {attempt}): {e}\n{traceback.format_exc()}"
            )
        if attempt == 1:
            continue
        # Start still failed after a clean-session retry. If the token no longer
        # passes getMe it was revoked -> "dead"; otherwise a transient "error".
        ok2, status2, _ = await validate_token(token)
        if not ok2 and status2 == "invalid":
            return False, "dead", None
        return False, None, None


async def delete_clone_by_bot_id(bot_id: int) -> bool:
    try:
        await db.users.update_many({"bot_ids": bot_id}, {"$pull": {"bot_ids": bot_id}})
        await db.chats.update_many({"bot_ids": bot_id}, {"$pull": {"bot_ids": bot_id}})
        await clone_manager.stop_clone(bot_id)
        _remove_session_files(bot_id)
        await startpic.delete_one({"bot_id": bot_id})
        await clone_db.delete_one({"_id": bot_id})
        LOGGER.info(f"Deleted clone {bot_id}")
        return True
    except Exception as e:
        LOGGER.error(f"Error deleting clone {bot_id}: {e}")
        return False


async def clone(owner_id, token, bot_id):
    success, bot_username, bot_name = await create_clone_client(owner_id, token, bot_id)

    if not success:
        if bot_username == "invalid":
            return "invalid", None, None
        if bot_username == "dead":
            return "dead", None, None
        return "error", None, None

    return "success", bot_username, bot_name


async def clone_start_up():
    LOGGER.info("Starting existing clones...")
    try:
        # Bounded in practice by CLONE_LIMIT; cap as a safety valve.
        all_clones = await clone_db.find({}).to_list(length=500)

        if not all_clones:
            LOGGER.info("No clones to start")
            return

        sem = asyncio.Semaphore(5)

        async def start_one(doc):
            async with sem:
                bot_id = doc["_id"]
                owner_id = doc.get("owner_id")
                token = doc.get("token")
                if not token or not owner_id:
                    return False
                try:
                    result, _, _ = await clone(owner_id, token, bot_id)
                    if result == "invalid":
                        await delete_clone_by_bot_id(bot_id)
                        return False
                    if result == "success":
                        await clone_db.update_one(
                            {"_id": bot_id}, {"$set": {"status": "running"}}
                        )
                        return True
                    await clone_db.update_one(
                        {"_id": bot_id}, {"$set": {"status": "stopped"}}
                    )
                    return False
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    LOGGER.error(f"Error starting clone {bot_id}: {e}")
                    return False

        results = await asyncio.gather(
            *(start_one(d) for d in all_clones), return_exceptions=True
        )
        started = sum(1 for r in results if r is True)
        LOGGER.info(f"Started {started} clones")
    except asyncio.CancelledError:
        LOGGER.info("Clone startup cancelled")
        raise
    except Exception as e:
        LOGGER.error(f"Error in clone_start_up: {e}")


async def clone_health_loop():
    """Every 10 min: restart crashed clones, mark revoked ones dead, notify owners once."""
    while True:
        await asyncio.sleep(600)
        try:
            docs = await clone_db.find({"status": {"$ne": "dead"}}).to_list(length=500)
            for doc in docs:
                bot_id = doc["_id"]
                # .get() (not `in` + index) so a concurrent stop_clone deleting
                # the entry between the check and the access can't KeyError.
                entry = clone_manager.clones.get(bot_id)
                if entry is not None:
                    client = entry["client"]
                    if client.is_connected:
                        continue
                # not running or disconnected -> validate, then restart or mark dead
                ok, status, _ = await validate_token(doc["token"])
                if status == "invalid":
                    await clone_manager.stop_clone(bot_id)
                    await clone_db.update_one(
                        {"_id": bot_id}, {"$set": {"status": "dead"}}
                    )
                    try:
                        from Emilia import pgram

                        await pgram.send_message(
                            doc["owner_id"],
                            f"Your clone @{doc.get('bot_username')} stopped working - "
                            f"its token looks revoked. Fix it in @BotFather, then "
                            f"/deleteclone and /clone again, or restart it from /mybots.",
                        )
                    except Exception:
                        pass
                    continue
                if status == "network":
                    continue  # transient; retry next cycle
                await clone_manager.stop_clone(bot_id)
                success, _, _ = await clone_manager.start_clone(
                    doc["owner_id"], doc["token"], bot_id
                )
                await clone_db.update_one(
                    {"_id": bot_id},
                    {"$set": {"status": "running" if success else "stopped"}},
                )
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            LOGGER.error(f"clone_health_loop error: {e}")


@register(pattern="clone")
async def clone_bot(client, message):
    if getattr(client, "is_clone", False):
        return await message.reply_text(
            "This feature is only available for the original bot."
        )
    if message.chat.type != ChatType.PRIVATE:
        return await message.reply_text("Please clone **Emilia** in your private chat.")

    user_id = message.from_user.id

    if len(message.text.split()) == 1:
        return await message.reply_text(
            "**Create your own bot in 3 steps:**\n\n"
            "1. Open @BotFather, send /newbot, pick a name and username.\n"
            "2. Copy the token it gives you (looks like `12345678:ABCdef...`).\n"
            "3. Send me: `/clone <that token>`\n\n"
            "Your bot goes live instantly with all of Emilia's features. "
            "Your token message is deleted right away for safety."
        )

    is_dev = user_id in DEV_USERS

    if not is_dev and await clone_db.count_documents({}) >= CLONE_LIMIT:
        return await message.reply_text(
            f"Clones have reached the default limit {CLONE_LIMIT} for this bot. "
            f"Please contact @{SUPPORT_CHAT} to clone this bot."
        )

    extra = await get_extra_slots(user_id)
    owned = await clone_db.count_documents({"owner_id": user_id})
    if not is_dev and owned >= CLONES_PER_USER + extra:
        text = (
            f"You already have {owned} clones (limit {CLONES_PER_USER + extra}). "
            f"Delete one with /deleteclone first."
        )
        if CLONE_PREMIUM_ENABLED:
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            f"Unlock another slot ({CLONE_PREMIUM_STARS} Stars)",
                            callback_data="clonepay",
                        )
                    ]
                ]
            )
            return await message.reply_text(text, reply_markup=keyboard)
        return await message.reply_text(text)

    token = message.text.split(None, 1)[1]
    try:
        bot_id = int(token.split(":")[0])
    except (ValueError, IndexError):
        return await message.reply_text("Invalid bot token provided.")

    existing = await clone_db.find_one({"_id": bot_id})
    if existing:
        if existing.get("owner_id") != user_id:
            return await message.reply_text(
                "This bot is already cloned by someone else. "
                "Please use a different bot token."
            )
        # Same owner re-cloning their own bot (e.g. with a regenerated token):
        # drop the old record + stale session so the fresh token starts clean.
        await delete_clone_by_bot_id(bot_id)

    # Token is now in-chat; delete it before doing anything else.
    try:
        await message.delete()
    except Exception:
        pass

    wait = await client.send_message(
        message.chat.id, "Validating token and starting your clone..."
    )

    try:
        result, bot_username, bot_name = await clone(user_id, token, bot_id)

        if result == "invalid":
            return await wait.edit_text(
                "The bot token you provided is invalid. Please provide the correct "
                "bot token. Perhaps you forgot to remove [] or <> around the token?"
            )
        elif result == "dead":
            return await wait.edit_text(
                "That token looks revoked - Telegram rejected the login. Open "
                "@BotFather, revoke and generate a fresh token, then send /clone "
                "with the new token."
            )
        elif result == "error":
            return await wait.edit_text(
                "An error occurred while creating your clone. Please try again or "
                "contact support @SpiralTechDivision."
            )
        elif result == "success":
            await clone_db.update_one(
                {"_id": bot_id},
                {
                    "$set": {
                        "owner_id": user_id,
                        "token": token,
                        "bot_username": bot_username,
                        "bot_name": bot_name,
                        "status": "running",
                    },
                    "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
                },
                upsert=True,
            )
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            f"Add @{bot_username} to a group",
                            url=f"https://t.me/{bot_username}?startgroup=true",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "Manage my bots", callback_data="mybots_list"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "Clone guide",
                            url=f"https://t.me/{BOT_USERNAME}?start=help_clone",
                        )
                    ],
                ]
            )
            await wait.edit_text(
                f"**@{bot_username} is live!**\n\n"
                f"Your bot has every Emilia feature, running under your name.",
                reply_markup=keyboard,
            )
    except Exception as e:
        LOGGER.error(f"Clone error: {e}")
        try:
            await wait.delete()
        except Exception:
            pass
        await message.reply_text(
            "An error occurred while cloning **Emilia**. Please try again or "
            "contact support @SpiralTechDivision."
        )


@register(pattern="deleteclone")
async def delete_cloned(client, message):
    if getattr(client, "is_clone", False):
        return await message.reply_text(
            "This feature is only available in the original bot."
        )
    if message.chat.type != ChatType.PRIVATE:
        return await message.reply_text(
            "Please delete Emilia's clone in your private chat."
        )

    user_id = message.from_user.id
    docs = await clone_db.find({"owner_id": user_id}).to_list(length=None)
    if not docs:
        return await message.reply_text(
            "You have no clones. Create one with /clone <bottoken>."
        )

    keyboard = [
        [
            InlineKeyboardButton(
                f"Delete @{d.get('bot_username')}",
                callback_data=f"delclone_{d['_id']}",
            )
        ]
        for d in docs
    ]
    keyboard.append(
        [InlineKeyboardButton("Cancel", callback_data="delclone_cancel")]
    )
    await message.reply_text(
        "Select the clone you want to delete:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


@callbackquery(pattern="delclone")
async def delclone_callback(client, query):
    if getattr(client, "is_clone", False):
        return await query.answer()
    data = query.data
    if data == "delclone_cancel":
        return await query.message.edit_text("Cancelled.")

    try:
        bot_id = int(data.split("_", 1)[1])
    except (ValueError, IndexError):
        return await query.answer("Invalid selection.", show_alert=True)

    doc = await clone_db.find_one({"_id": bot_id})
    if not doc or query.from_user.id != doc.get("owner_id"):
        return await query.answer("Not your button.", show_alert=True)

    username = doc.get("bot_username")
    await delete_clone_by_bot_id(bot_id)
    await query.message.edit_text(
        f"**Clone @{username} deleted.** Bot stopped and removed from our servers. "
        f"You can create a new one anytime with /clone."
    )


def render_mybots_list(docs):
    text = "**Your bots** - tap one to manage:"
    keyboard = [
        [
            InlineKeyboardButton(
                f"@{d.get('bot_username')}", callback_data=f"mybots_{d['_id']}"
            )
        ]
        for d in docs
    ]
    return text, InlineKeyboardMarkup(keyboard)


async def render_bot_panel(bot_id):
    doc = await clone_db.find_one({"_id": bot_id})
    if not doc:
        return None, None
    username = doc.get("bot_username")
    name = doc.get("bot_name")
    if bot_id in clone_manager.clones:
        status = "Running"
    else:
        status = {
            "running": "Running",
            "stopped": "Stopped",
            "dead": "Dead - token revoked?",
        }.get(doc.get("status"), "Stopped")
    users_count = await db.users.count_documents({"bot_ids": bot_id})
    chats_count = await db.chats.count_documents({"bot_ids": bot_id})
    text = (
        f"@{username} ({name})\n"
        f"Status: {status}\n"
        f"Users: {users_count} | Chats: {chats_count}"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Restart", callback_data=f"cbot_restart_{bot_id}"
                ),
                InlineKeyboardButton("Delete", callback_data=f"cbot_del_{bot_id}"),
            ],
            [
                InlineKeyboardButton(
                    "Start pic", callback_data=f"cbot_pic_{bot_id}"
                ),
                InlineKeyboardButton(
                    "Broadcast help", callback_data=f"cbot_bc_{bot_id}"
                ),
            ],
            [InlineKeyboardButton("All bots", callback_data="mybots_list")],
        ]
    )
    return text, keyboard


@register(pattern="mybots")
async def mybots(client, message):
    if getattr(client, "is_clone", False):
        return await message.reply_text(
            "This feature is only available for the original bot."
        )
    if message.chat.type != ChatType.PRIVATE:
        return await message.reply_text("Please use /mybots in your private chat.")

    docs = await clone_db.find({"owner_id": message.from_user.id}).to_list(length=None)
    if not docs:
        return await message.reply_text(
            "You have no bots yet. Create one in seconds: /clone <bottoken>"
        )
    text, keyboard = render_mybots_list(docs)
    await message.reply_text(text, reply_markup=keyboard)


@callbackquery(pattern="mybots")
async def mybots_callback(client, query):
    if getattr(client, "is_clone", False):
        return await query.answer()
    data = query.data
    if data == "mybots_list":
        docs = await clone_db.find({"owner_id": query.from_user.id}).to_list(
            length=None
        )
        if not docs:
            return await query.message.edit_text(
                "You have no bots yet. Create one in seconds: /clone <bottoken>"
            )
        text, keyboard = render_mybots_list(docs)
        await query.message.edit_text(text, reply_markup=keyboard)
        return await query.answer()

    try:
        bot_id = int(data.split("_", 1)[1])
    except (ValueError, IndexError):
        return await query.answer("Invalid selection.", show_alert=True)

    doc = await clone_db.find_one({"_id": bot_id})
    if not doc or query.from_user.id != doc.get("owner_id"):
        return await query.answer("Not your button.", show_alert=True)

    text, keyboard = await render_bot_panel(bot_id)
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()


@callbackquery(pattern="cbot")
async def cbot_callback(client, query):
    if getattr(client, "is_clone", False):
        return await query.answer()
    parts = query.data.split("_")
    action = parts[1]
    try:
        bot_id = int(parts[2])
    except (ValueError, IndexError):
        return await query.answer("Invalid selection.", show_alert=True)

    doc = await clone_db.find_one({"_id": bot_id})
    if not doc or query.from_user.id != doc.get("owner_id"):
        return await query.answer("Not your button.", show_alert=True)

    username = doc.get("bot_username")

    if action == "restart":
        await query.answer("Restarting...")
        await clone_manager.stop_clone(bot_id)
        result, _, _ = await clone(doc["owner_id"], doc["token"], bot_id)
        if result == "success":
            await clone_db.update_one(
                {"_id": bot_id}, {"$set": {"status": "running"}}
            )
        elif result in ("invalid", "dead"):
            # Token no longer works; flag the clone dead so the owner knows to
            # re-create it with a fresh @BotFather token instead of retrying.
            await clone_db.update_one(
                {"_id": bot_id}, {"$set": {"status": "dead"}}
            )
        else:
            await clone_db.update_one(
                {"_id": bot_id}, {"$set": {"status": "stopped"}}
            )
        text, keyboard = await render_bot_panel(bot_id)
        return await query.message.edit_text(text, reply_markup=keyboard)

    if action == "del":
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Yes", callback_data=f"delclone_{bot_id}"
                    ),
                    InlineKeyboardButton(
                        "Back", callback_data=f"mybots_{bot_id}"
                    ),
                ]
            ]
        )
        await query.message.edit_text(
            f"Delete @{username}? This stops the bot permanently.",
            reply_markup=keyboard,
        )
        return await query.answer()

    if action == "pic":
        # Start a short conversation: the owner's next message to THIS (main)
        # bot becomes the clone's start picture. Photos are re-uploaded through
        # the clone client (file_ids are bot-scoped), URLs are stored directly.
        _PENDING_STARTPIC[query.from_user.id] = bot_id
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Cancel", callback_data=f"cbot_piccancel_{bot_id}")]]
        )
        await query.message.edit_text(
            f"Send a photo or an image URL now and I'll set it as @{username}'s "
            f"start picture. Send /cancel to abort.",
            reply_markup=keyboard,
        )
        return await query.answer()

    if action == "piccancel":
        _PENDING_STARTPIC.pop(query.from_user.id, None)
        text, keyboard = await render_bot_panel(bot_id)
        await query.message.edit_text(text, reply_markup=keyboard)
        return await query.answer("Cancelled.")

    if action == "bc":
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Back", callback_data=f"mybots_{bot_id}")]]
        )
        await query.message.edit_text(
            f"Send /broadcast in a chat with @{username}, replying to the message "
            f"you want to send. Modes: -all, -users, -chats.",
            reply_markup=keyboard,
        )
        return await query.answer()

    await query.answer()


@register(pattern="setstartpic")
async def set_startpic(client, message):
    if not getattr(client, "is_clone", False):
        return await message.reply_text(
            "This feature is only available in cloned bots. Learn more about "
            "cloning Emilia by using `/help Clone`."
        )

    me = client.me or await client.get_me()
    clone_info = await get_clone_info_by_bot_id(me.id)

    if not clone_info or message.from_user.id != clone_info.get("owner_id"):
        return await message.reply_text(
            "You are not authorized to set the start picture for this bot."
        )

    reply_message = message.reply_to_message
    if reply_message and reply_message.photo:
        await startpic.update_one(
            {"bot_id": me.id},
            {
                "$set": {
                    "file_id": reply_message.photo.file_id,
                    "user_id": clone_info["owner_id"],
                    "token": clone_info["token"],
                }
            },
            upsert=True,
        )
        await message.reply_text(
            "**Start picture updated successfully!**\n\n"
            "The new start picture will be used immediately for your clone bot."
        )
    else:
        args = message.text.split(None, 1)
        if len(args) < 2:
            return await message.reply_text(
                "Please provide a valid image URL. Example: `/setstartpic <image_url>`"
            )

        url = args[1]
        path = urlparse(url).path.lower()
        if not path.endswith((".jpg", ".jpeg", ".png", ".webp")):
            return await message.reply_text(
                "The url you provided is not an image url. Please provide a valid "
                "image url. It should end with `.jpg`, `.jpeg`, `.png`, or `.webp`."
            )
        if not await asyncio.to_thread(is_safe_url, url):
            return await message.reply_text(
                "That URL isn't allowed. Use a public http(s) image URL."
            )

        await startpic.update_one(
            {"bot_id": me.id},
            {
                "$set": {
                    "url": url,
                    "user_id": clone_info["owner_id"],
                    "token": clone_info["token"],
                }
            },
            upsert=True,
        )
        await message.reply_text(
            f"**Start picture updated successfully!**\n\n"
            f"The new start picture will be used immediately for your clone bot.\n"
            f"**Preview URL:** {url}"
        )


async def _save_clone_startpic(bot_id, owner_id, field, value):
    doc = await clone_db.find_one({"_id": bot_id})
    token = doc.get("token") if doc else None
    await startpic.update_one(
        {"bot_id": bot_id},
        {"$set": {field: value, "user_id": owner_id, "token": token}},
        upsert=True,
    )


@listen(filters=filters.private & filters.incoming)
async def startpic_conversation(client, message):
    """Capture the next photo/URL after an owner tapped 'Start pic' in /mybots.

    Registered on the main bot only (listeners aren't replayed to clones). No-op
    unless the sender has a pending start-pic request.
    """
    if getattr(client, "is_clone", False):
        return
    user_id = message.from_user.id if message.from_user else None
    if user_id not in _PENDING_STARTPIC:
        return

    text = (message.text or message.caption or "").strip()
    if text.lower() in ("/cancel", "cancel"):
        _PENDING_STARTPIC.pop(user_id, None)
        return await message.reply_text("Cancelled.")

    bot_id = _PENDING_STARTPIC[user_id]

    if message.photo:
        # file_ids are bot-scoped: a main-bot file_id won't resolve on the
        # clone. Re-upload the photo through the clone client to mint a valid
        # file_id. Requires the clone to be running.
        if bot_id not in clone_manager.clones:
            _PENDING_STARTPIC.pop(user_id, None)
            return await message.reply_text(
                "That clone isn't running right now, so I can't set a photo. "
                "Restart it from /mybots, or send an image URL instead."
            )
        file_size = getattr(message.photo, "file_size", 0) or 0
        if file_size > _STARTPIC_MAX_BYTES:
            _PENDING_STARTPIC.pop(user_id, None)
            return await message.reply_text(
                f"That image is too large (max "
                f"{_STARTPIC_MAX_BYTES // (1024 * 1024)} MB). "
                f"Send a smaller photo or an image URL."
            )

        clone_client = clone_manager.clones[bot_id]["client"]
        path = None
        try:
            path = await client.download_media(
                message.photo.file_id, in_memory=False
            )
            # A bot can't send to itself (USER_IS_BOT), so re-upload the photo
            # to the owner's chat with the clone to mint a clone-valid file_id,
            # then delete that throwaway message.
            sent = await clone_client.send_photo(user_id, path)
            await _save_clone_startpic(
                bot_id, user_id, "file_id", sent.photo.file_id
            )
            try:
                await sent.delete()
            except Exception:
                pass
        except Exception as e:
            LOGGER.error(f"startpic photo transfer failed for {bot_id}: {e}")
            _PENDING_STARTPIC.pop(user_id, None)
            return await message.reply_text(
                f"Couldn't set that photo - make sure you've started @"
                f"{clone_manager.clones[bot_id]['bot_username']} in PM first, "
                f"then try again, or send an image URL instead."
            )
        finally:
            if path:
                try:
                    os.remove(path)
                except Exception:
                    pass
        _PENDING_STARTPIC.pop(user_id, None)
        return await message.reply_text(
            "Start picture updated. It's live on your clone now."
        )

    # Reject files sent as documents/video/etc — only compressed photos and
    # URLs are accepted, so we never download arbitrary large attachments.
    if message.document or message.video or message.animation or message.sticker:
        return await message.reply_text(
            "Please send the image as a **photo** (not a file), or paste an "
            "image URL. Or /cancel."
        )

    if text:
        url = text.split()[0]
        path = urlparse(url).path.lower()
        if not path.endswith((".jpg", ".jpeg", ".png", ".webp")):
            return await message.reply_text(
                "That doesn't look like an image URL (needs .jpg/.jpeg/.png/.webp). "
                "Send a photo or a valid URL, or /cancel."
            )
        if not await asyncio.to_thread(is_safe_url, url):
            return await message.reply_text(
                "That URL isn't allowed. Use a public http(s) image URL, or /cancel."
            )
        await _save_clone_startpic(bot_id, user_id, "url", url)
        _PENDING_STARTPIC.pop(user_id, None)
        return await message.reply_text(
            "Start picture updated. It's live on your clone now."
        )

    return await message.reply_text(
        "Send a photo or an image URL, or /cancel."
    )


@register(pattern="broadcast")
async def broadcast(client, message):
    if not getattr(client, "is_clone", False):
        return await message.reply_text(
            "**Broadcast is only available on cloned bots**\n\n"
            "Please use your cloned bot to broadcast messages."
        )

    if not message.reply_to_message:
        return await message.reply_text("Please reply to a message to broadcast it!")

    me = client.me or await client.get_me()
    bot_id = me.id
    clone_info = await get_clone_info_by_bot_id(bot_id)

    if not clone_info or message.from_user.id != clone_info.get("owner_id"):
        return await message.reply_text("You are not authorized to use this command.")

    args = message.text.split(None, 1)
    if len(args) < 2 or args[1].lower() not in ["-all", "-users", "-chats"]:
        user_count = await db.users.count_documents({"bot_ids": bot_id})
        chat_count = await db.chats.count_documents({"bot_ids": bot_id})
        return await message.reply_text(
            f"Please provide a mode: `/broadcast -all`, `/broadcast -users`, or "
            f"`/broadcast -chats`\n\n"
            f"**Users**: {user_count}\n"
            f"**Chats**: {chat_count}"
        )

    mode = args[1].lower()
    reply = message.reply_to_message

    if mode == "-all":
        n = await db.users.count_documents(
            {"bot_ids": bot_id}
        ) + await db.chats.count_documents({"bot_ids": bot_id})
    elif mode == "-users":
        n = await db.users.count_documents({"bot_ids": bot_id})
    else:
        n = await db.chats.count_documents({"bot_ids": bot_id})

    wait = await message.reply_text(
        f"Broadcasting to {n} targets... this may take a while."
    )

    try:
        if mode == "-all":
            us, uf = await broadcast_to_users(bot_id, reply, wait)
            cs, cf = await broadcast_to_chats(bot_id, reply, wait)
            await wait.edit_text(
                f"**Broadcast Complete**\n\n"
                f"Users: {us} success, {uf} failed\n"
                f"Chats: {cs} success, {cf} failed"
            )
        elif mode == "-users":
            s, f = await broadcast_to_users(bot_id, reply, wait)
            await wait.edit_text(
                f"**User Broadcast Complete**\n\nUsers: {s} success, {f} failed"
            )
        else:
            s, f = await broadcast_to_chats(bot_id, reply, wait)
            await wait.edit_text(
                f"**Chat Broadcast Complete**\n\nChats: {s} success, {f} failed"
            )
    except Exception as e:
        LOGGER.error(f"Broadcast error: {e}")
        await wait.edit_text(f"Broadcast failed: {str(e)}")


async def broadcast_to_users(bot_id, message, wait):
    cursor = db.users.find({"bot_ids": bot_id}, {"user_id": 1})
    success, failed = 0, 0

    async for doc in cursor:
        uid = doc["user_id"]
        try:
            await message.copy(uid)
            success += 1
            await asyncio.sleep(0.05)
        except UserIsBlocked:
            await db.users.update_one({"user_id": uid}, {"$pull": {"bot_ids": bot_id}})
            failed += 1
        except FloodWait as e:
            await asyncio.sleep(min(e.value, 60))
            try:
                await message.copy(uid)
                success += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1

        if (success + failed) % 200 == 0:
            try:
                await wait.edit_text(f"Broadcasting... {success + failed} done")
            except Exception:
                pass

    return success, failed


async def broadcast_to_chats(bot_id, message, wait):
    cursor = db.chats.find({"bot_ids": bot_id}, {"chat_id": 1})
    success, failed = 0, 0

    async for doc in cursor:
        cid = doc["chat_id"]
        try:
            await message.copy(cid)
            success += 1
            await asyncio.sleep(0.05)
        except (ChatWriteForbidden, UserNotParticipant):
            await db.chats.update_one({"chat_id": cid}, {"$pull": {"bot_ids": bot_id}})
            failed += 1
        except FloodWait as e:
            await asyncio.sleep(min(e.value, 60))
            try:
                await message.copy(cid)
                success += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1

        if (success + failed) % 200 == 0:
            try:
                await wait.edit_text(f"Broadcasting... {success + failed} done")
            except Exception:
                pass

    return success, failed


@register(pattern="clonestats")
async def clone_stats(client, message):
    if not getattr(client, "is_clone", False):
        return await message.reply_text("Use this command in your cloned bot.")
    me = client.me or await client.get_me()
    clone_info = await get_clone_info_by_bot_id(me.id)
    if not clone_info or message.from_user.id != clone_info.get("owner_id"):
        return await message.reply_text("Only the clone owner can use this.")
    users = await db.users.count_documents({"bot_ids": me.id})
    chats = await db.chats.count_documents({"bot_ids": me.id})
    await message.reply_text(f"**@{me.username} stats**\n\nUsers: {users}\nChats: {chats}")


@auth(pattern="clonestatus")
async def clone_status(client, message):
    if not clone_manager.clones:
        return await message.reply_text("No active clone clients running.")

    status_msg = "**Active Clone Clients Status**\n\n"
    for bot_id, info in clone_manager.clones.items():
        status_msg += f"**Bot ID**: `{bot_id}`\n"
        status_msg += (
            f"**Bot**: @{info.get('bot_username', 'Unknown')} "
            f"({info.get('bot_name', 'Unknown')})\n"
        )
        status_msg += f"**Owner**: `{info.get('owner_id', 'Unknown')}`\n"
        status_msg += "**Status**: Online\n\n"

    status_msg += f"**Total Active Clones**: {len(clone_manager.clones)}"
    await message.reply_text(status_msg)


@callbackquery(pattern="clonepay")
async def clone_pay_callback(client, query):
    if getattr(client, "is_clone", False):
        return await query.answer()
    await client.send_invoice(
        chat_id=query.from_user.id,
        title="Extra clone slot",
        description="Permanently unlock one additional Emilia clone slot.",
        payload=f"cloneslot_{query.from_user.id}",
        currency="XTR",
        prices=[LabeledPrice(label="1 slot", amount=CLONE_PREMIUM_STARS)],
    )
    await query.answer()


@Client.on_pre_checkout_query()
async def clone_pre_checkout(client, pre_checkout_query):
    if getattr(client, "is_clone", False):
        return
    await pre_checkout_query.answer(ok=True)


@Client.on_message(filters.successful_payment)
async def clone_successful_payment(client, message):
    if getattr(client, "is_clone", False):
        return
    sp = message.successful_payment
    payload = sp.invoice_payload
    if not payload or not payload.startswith("cloneslot_"):
        return

    user_id = message.from_user.id
    charge_id = sp.telegram_payment_charge_id

    # Idempotency across Telegram redeliveries. The charge record is the source
    # of truth and is written in two steps so a mid-way crash can't leave the
    # user paid-but-slotless OR double-credited:
    #   1. insert the record with granted=False (unique _id=charge_id blocks a
    #      duplicate insert -> a redelivery of an already-processed charge is a
    #      no-op unless step 2 never completed).
    #   2. $inc the slot, then flip granted=True.
    # A redelivery whose record exists but granted is still False means step 2
    # was interrupted, so we complete the grant exactly once.
    try:
        await clone_payments.insert_one(
            {
                "_id": charge_id,
                "user_id": user_id,
                "stars": sp.total_amount,
                "payload": payload,
                "created_at": datetime.now(timezone.utc),
                "granted": False,
                "refunded": False,
            }
        )
    except DuplicateKeyError:
        existing = await clone_payments.find_one({"_id": charge_id})
        if existing and existing.get("granted"):
            LOGGER.info(f"Duplicate payment delivery ignored: {charge_id}")
            return
        # else: prior attempt didn't finish granting — fall through to complete.
    except Exception as e:
        LOGGER.error(f"Failed to record payment {charge_id}: {e}")
        return await message.reply_text(
            "Payment received but we hit a snag recording it. Contact "
            f"@{SUPPORT_CHAT} with this id: `{charge_id}`"
        )

    await clone_slots.update_one(
        {"_id": user_id}, {"$inc": {"extra": 1}}, upsert=True
    )
    await clone_payments.update_one(
        {"_id": charge_id}, {"$set": {"granted": True}}
    )
    await message.reply_text(
        "Payment received. One extra clone slot unlocked - use /clone to create it."
    )


@auth(pattern="refundstar")
async def refund_star(client, message):
    if getattr(client, "is_clone", False):
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.reply_text(
            "Usage: `/refundstar <charge_id>`\n"
            "Find charge_ids with `/clonepayments`."
        )
    charge_id = args[1]
    record = await clone_payments.find_one({"_id": charge_id})
    if not record:
        return await message.reply_text("No payment found with that charge id.")
    if record.get("refunded"):
        return await message.reply_text("That payment was already refunded.")

    try:
        ok = await client.refund_star_payment(
            user_id=record["user_id"], telegram_payment_charge_id=charge_id
        )
    except Exception as e:
        LOGGER.error(f"Refund failed for {charge_id}: {e}")
        return await message.reply_text(f"Refund failed: {e}")

    if not ok:
        return await message.reply_text("Telegram rejected the refund.")

    # Roll back the slot that this payment granted (floor at 0).
    await clone_slots.update_one(
        {"_id": record["user_id"], "extra": {"$gt": 0}}, {"$inc": {"extra": -1}}
    )
    await clone_payments.update_one(
        {"_id": charge_id}, {"$set": {"refunded": True}}
    )
    await message.reply_text(
        f"Refunded {record.get('stars')} Stars to `{record['user_id']}` and "
        f"removed the extra slot."
    )


@auth(pattern="clonepayments")
async def clone_payments_list(client, message):
    if getattr(client, "is_clone", False):
        return
    docs = (
        await clone_payments.find({})
        .sort("created_at", -1)
        .to_list(length=20)
    )
    if not docs:
        return await message.reply_text("No clone payments recorded.")
    lines = ["**Recent clone payments**\n"]
    for d in docs:
        flag = " (refunded)" if d.get("refunded") else ""
        lines.append(
            f"`{d['_id']}` - user `{d['user_id']}`, {d.get('stars')}*{flag}"
        )
    await message.reply_text("\n".join(lines))


async def shutdown_all_clones():
    await clone_manager.stop_all_clones()
