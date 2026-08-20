import asyncio
import re
from typing import Any

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import FloodWait, PeerIdInvalid, RPCError, UserIsBlocked
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from Emilia import BOT_USERNAME, LOGGER, custom_filter
from Emilia.helper.chat_status import isUserAdmin
from Emilia.helper.disable import disable
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo import requests_mongo as rdb
from Emilia.strings import (
    REQ_ADMIN_ONLY,
    REQ_CHANNEL_NOT_SET,
    REQ_DISABLED,
    REQ_LIMIT_EXCEEDED,
    REQ_NO_QUERY,
    REQ_NOT_CONFIGURED,
)
from Emilia.utils.decorators import RATE_LIMIT_GENERAL, RATE_LIMIT_HEAVY, anonadmin_checker, exception, rate_limit
from Emilia.utils.errors import report_error

G_VIEW, G_OPEN, G_ADD, G_DONE, G_REJECT, G_PENDING, G_BULLET, G_SUB = "▷", "⇱", "＋", "✓", "✕", "◷", "•", "›"

SEARCH_SEMAPHORE = asyncio.Semaphore(50)
_BROADCAST_SEMAPHORE = asyncio.Semaphore(10)
_MAX_FLOOD_SLEEP = 30


def _clean_markdown(text: str) -> str:
    if not text:
        return ""
    sanitized = re.sub(r"[\[\]`*_]", " ", str(text))
    return " ".join(sanitized.split()).strip()


def _post_url(channel_id: int, message_id: int, username: str | None = None) -> str:
    if username:
        return f"https://t.me/{username.lstrip('@')}/{message_id}"
    s_cid = str(channel_id)
    cid = s_cid[4:] if s_cid.startswith("-100") else s_cid.lstrip("-")
    return f"https://t.me/c/{cid}/{message_id}"


async def _search_channels(client: Client, channels: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    async def _search_one(ch: dict[str, Any]):
        cid = ch.get("id")
        title = _clean_markdown(ch.get("title", "Channel"))
        uname = ch.get("username")
        if not cid:
            return

        async with SEARCH_SEMAPHORE:
            try:
                async for msg in client.search_messages(chat_id=cid, query=query, limit=4):
                    media = msg.document or msg.video or msg.audio or msg.photo or msg.animation
                    fname = getattr(media, "file_name", None) or getattr(media, "title", None)
                    if not fname:
                        fname = (msg.caption or msg.text or f"Post #{msg.id}").split("\n")[0][:50]
                    cleaned_name = _clean_markdown(fname) or f"Post #{msg.id}"
                    results.append({"name": cleaned_name, "title": title, "url": _post_url(cid, msg.id, uname)})
            except Exception as e:
                LOGGER.debug(f"Channel search failed for {cid}: {e}")

    await asyncio.gather(*[_search_one(c) for c in channels], return_exceptions=True)
    return results


def _render_search_results(query: str, results: list[dict[str, Any]]) -> tuple[str, InlineKeyboardMarkup]:
    clean_q = _clean_markdown(query)
    lines = [f"> **Search Results**\n> Found **{len(results)}** matches for `{clean_q}`:\n"]
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for idx, item in enumerate(results[:6], 1):
        lines.append(f"{G_BULLET} **{idx}. {item['name']}**\n  {G_SUB} [{G_VIEW} Open in {item['title']}]({item['url']})")
        row.append(InlineKeyboardButton(f"{G_VIEW} Post #{idx}", url=item["url"]))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def _render_req_card(doc: dict[str, Any], is_admin: bool = False) -> tuple[str, InlineKeyboardMarkup | None]:
    num, query, status = doc["num"], _clean_markdown(doc["query"]), doc.get("status", "pending")
    subs = len(doc.get("subscribers", []))
    req_id = doc["_id"]

    if is_admin:
        stat_label = f"{G_DONE} Uploaded" if status == "completed" else f"{G_REJECT} Rejected" if status == "rejected" else f"{G_PENDING} Pending ({subs})"
        text = f"> **Content Request** • `#REQ-{num}`\n\n{G_BULLET} **Query:** `{query}`\n{G_BULLET} **Status:** `{stat_label}`"
        if doc.get("post_url"):
            text += f"\n{G_BULLET} **Post:** [View Uploaded File]({doc['post_url']})"
        if status == "pending":
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton(f"{G_DONE} Done", callback_data=f"req:done:{req_id}"),
                InlineKeyboardButton(f"{G_REJECT} Reject", callback_data=f"req:reject:{req_id}"),
            ]])
            return text, markup
        return text, None

    text = (
        f"> **No matches found for** `{query}`\n"
        f"> Request **#REQ-{num}** queued for uploaders!\n\n"
        f"{G_BULLET} **Status:** `{G_PENDING} Pending`\n"
        f"{G_BULLET} **Subscribers:** `{subs}`\n\n"
        f"> You will receive a PM alert once uploaded."
    )
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"{G_ADD}1 Me Too ({subs})", callback_data=f"req:metoo:{req_id}"),
        InlineKeyboardButton(f"{G_OPEN} Enable PM Alerts", url=f"https://t.me/{BOT_USERNAME}?start={req_id}"),
    ]])
    return text, markup


async def _safe_send_pm(client: Client, user_id: int, text: str, markup: InlineKeyboardMarkup | None):
    try:
        await client.send_message(user_id, text, reply_markup=markup, disable_web_page_preview=False)
    except FloodWait as e:
        if e.value > _MAX_FLOOD_SLEEP:
            LOGGER.warning("[Requests] FloodWait %ds for PM to %s — skipping", e.value, user_id)
            return
        await asyncio.sleep(e.value)
        try:
            await client.send_message(user_id, text, reply_markup=markup, disable_web_page_preview=False)
        except Exception:
            pass
    except (UserIsBlocked, PeerIdInvalid, RPCError):
        pass


def _broadcast_update(client: Client, doc: dict[str, Any]):
    num, query, status = doc["num"], _clean_markdown(doc["query"]), doc.get("status")
    post_url, reason = doc.get("post_url"), doc.get("reason")

    if status == "completed":
        if post_url:
            text = f"> **Request Completed** • `#REQ-{num}`\n> `{query}` is now available!\n\n{G_SUB} [Open Post in Channel]({post_url})"
            markup = InlineKeyboardMarkup([[InlineKeyboardButton(f"{G_VIEW} Open Post", url=post_url)]])
        else:
            text = f"> **Request Completed** • `#REQ-{num}`\n> `{query}` has been uploaded by the channel admins!"
            markup = None
    else:
        text = f"> **Request Rejected** • `#REQ-{num}`\n> `{query}` was rejected.\n{G_BULLET} Reason: `{_clean_markdown(reason or 'Unavailable')}`"
        markup = None

    subscribers = doc.get("subscribers") or []

    async def _runner():
        async def _dispatch(uid: int):
            async with _BROADCAST_SEMAPHORE:
                await _safe_send_pm(client, uid, text, markup)

        tasks = [asyncio.create_task(_dispatch(uid)) for uid in subscribers]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for uid, result in zip(subscribers, results):
                if isinstance(result, Exception):
                    LOGGER.warning("[Requests] Broadcast PM to %s failed: %s", uid, result)

    asyncio.create_task(_runner())


async def _check_admin(message: Message) -> int | None:
    cid = (await connection(message)) or message.chat.id
    if not await isUserAdmin(message, chat_id=cid, pm_mode=True):
        await message.reply(REQ_ADMIN_ONLY)
        return None
    return cid


async def request_redirect(client: Client, message: Message):
    raw_id = message.text.split()[1].replace("req_", "").replace("req-", "").strip()
    if not raw_id:
        await message.reply("Invalid request link — no request ID provided.")
        return
    doc = await rdb.get_request(raw_id)
    if not doc:
        await message.reply(f"No request found with ID `#{raw_id}`.")
        return
    if message.from_user:
        await rdb.add_subscriber(doc["_id"], message.from_user.id)
    clean_q = _clean_markdown(doc['query'])
    text = (
        f"> **Subscribed to PM Alerts!** • `#REQ-{doc['num']}`\n\n"
        f"{G_BULLET} **Content:** `{clean_q}`\n"
        f"{G_BULLET} **Status:** `{G_PENDING if doc['status'] == 'pending' else G_DONE} {doc['status'].title()}`\n\n"
        f"> You will receive a direct notification here once uploaded."
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(f"{G_VIEW} View Post", url=doc["post_url"])]]) if doc.get("post_url") else None
    await message.reply(text, reply_markup=markup)


async def _handle_req(client: Client, message: Message, query: str):
    user = message.from_user
    clean_q = query.strip()[:120]
    if not user or not clean_q:
        return

    chat_id = message.chat.id
    if message.chat.type == ChatType.PRIVATE:
        conn = await connection(message)
        if conn is None:
            await message.reply("> **PM Mode**\n• Connect to your group using `/connect <group_id>` or send `#req <name>` directly in your group!")
            return
        chat_id = conn

    settings = await rdb.get_settings(chat_id)
    if not settings.get("is_enabled", True):
        await message.reply(REQ_DISABLED)
        return

    channels = settings.get("channels", [])
    req_ch = settings.get("req_channel")

    if not channels and not req_ch:
        await message.reply(REQ_NOT_CONFIGURED)
        return

    if channels:
        matches = await _search_channels(client, channels, clean_q)
        if matches:
            text, markup = _render_search_results(clean_q, matches)
            await message.reply(text, reply_markup=markup, disable_web_page_preview=True)
            return

    if not req_ch:
        await message.reply(f"> **No matches found for** `{_clean_markdown(clean_q)}`\n• {REQ_CHANNEL_NOT_SET}")
        return

    existing = await rdb.find_active_request(clean_q, chat_id=chat_id)
    if existing:
        await rdb.add_subscriber(existing["_id"], user.id)
        doc = await rdb.get_request(existing["_id"]) or existing
        text, markup = _render_req_card(doc)
        await message.reply(f"> **Request already active!** (#REQ-{doc['num']})\n> Added you to subscribers.", reply_markup=markup)
        return

    max_limit = int(settings.get("daily_limit", 0))
    allowed, _ = await rdb.check_and_increment_daily_limit(chat_id, user.id, max_limit)
    if not allowed:
        await message.reply(REQ_LIMIT_EXCEEDED.format(max_limit))
        return

    doc = await rdb.create_request(chat_id, user.id, user.first_name or "User", clean_q, req_channel=req_ch)
    try:
        adm_text, adm_markup = _render_req_card(doc, is_admin=True)
        await client.send_message(req_ch, adm_text, reply_markup=adm_markup, disable_web_page_preview=True)
    except Exception as e:
        LOGGER.warning(f"Failed to post to request channel {req_ch}: {e}")
        await report_error("requests.post_card", e, chat_id=chat_id, req_channel=req_ch, req_id=doc.get("_id"))

    user_text, user_markup = _render_req_card(doc)
    await message.reply(user_text, reply_markup=user_markup)


@Client.on_message(custom_filter.command(commands=["req", "request", "searchreq"], disable=True))
@disable
@rate_limit(limit_config=RATE_LIMIT_GENERAL)
@exception
async def req_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        reply = message.reply_to_message
        query = (reply.text or reply.caption) if reply else None
        if not query:
            await message.reply(REQ_NO_QUERY)
            return
    else:
        query = message.text.split(None, 1)[1]
    await _handle_req(client, message, query)


@Client.on_message(filters.regex(r"(?i)^#(?:req|request)(?:[\s\n]+([\s\S]+))?$"))
@disable
@rate_limit(limit_config=RATE_LIMIT_GENERAL)
@exception
async def req_hashtag(client: Client, message: Message):
    match = message.matches[0] if message.matches else None
    query = match.group(1) if match else None
    if not query:
        reply = message.reply_to_message
        query = (reply.text or reply.caption) if reply else None
    if query:
        await _handle_req(client, message, query.strip())


@Client.on_message(custom_filter.command(commands=["reqs", "myrequests", "requests"], disable=True))
@disable
@rate_limit(limit_config=RATE_LIMIT_GENERAL)
@exception
async def my_reqs_cmd(client: Client, message: Message):
    if not message.from_user:
        return
    reqs = await rdb.get_user_requests(message.from_user.id)
    if not reqs:
        await message.reply("> **My Requests**\nYou have no active or completed requests.")
        return
    lines = ["> **My Requests**\n"]
    for r in reqs:
        icon = G_DONE if r.get("status") == "completed" else G_REJECT if r.get("status") == "rejected" else G_PENDING
        link = f" › [Post]({r['post_url']})" if r.get("post_url") else ""
        clean_q = _clean_markdown(r.get("query", ""))
        lines.append(f"{G_BULLET} `#REQ-{r['num']}` `{icon} {r['status'].title()}`: **{clean_q}**{link}")
    await message.reply("\n".join(lines), disable_web_page_preview=True)


@Client.on_message(custom_filter.command(commands=["reqstatus", "requeststatus"], disable=True))
@disable
@rate_limit(limit_config=RATE_LIMIT_GENERAL)
@exception
async def req_status_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("Usage: `/reqstatus <id>`\nExample: `/reqstatus 8831`")
        return
    raw_id = message.command[1]
    doc = await rdb.get_request(raw_id)
    if not doc:
        await message.reply(f"No request found with ID `#{raw_id}`.")
        return
    clean_q = _clean_markdown(doc['query'])
    text = f"> **Request Status** • `#REQ-{doc['num']}`\n\n{G_BULLET} **Query:** `{clean_q}`\n{G_BULLET} **Status:** `{doc['status'].title()}`"
    if doc.get("post_url"):
        text += f"\n{G_BULLET} **Link:** [Open File]({doc['post_url']})"
    await message.reply(text, disable_web_page_preview=True)


@Client.on_message(custom_filter.command(commands=["setreq", "setrequest", "setreqchannel"]))
@anonadmin_checker
@rate_limit(limit_config=RATE_LIMIT_HEAVY)
@exception
async def set_req_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    if len(message.command) < 2:
        await message.reply("Usage: `/setreq <channel_id or @username>`")
        return
    try:
        target = await client.get_chat(int(message.command[1]) if message.command[1].lstrip("-").isdigit() else message.command[1])
        await rdb.update_settings(cid, {"req_channel": target.id, "req_title": target.title})
        await message.reply(f"Set **{target.title}** (`{target.id}`) as request channel.")
    except Exception as e:
        await message.reply(f"Could not access channel: {e}")


@Client.on_message(custom_filter.command(commands=["unsetreq", "unsetrequest"]))
@anonadmin_checker
@rate_limit(limit_config=RATE_LIMIT_HEAVY)
@exception
async def unset_req_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    await rdb.update_settings(cid, {"req_channel": None, "req_title": None})
    await message.reply("Request channel disconnected.")


@Client.on_message(custom_filter.command(commands=["addchannel", "addcontentchannel"]))
@anonadmin_checker
@rate_limit(limit_config=RATE_LIMIT_HEAVY)
@exception
async def add_channel_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    if len(message.command) < 2:
        await message.reply("Usage: `/addchannel <channel_id or @username>`")
        return
    try:
        target = await client.get_chat(int(message.command[1]) if message.command[1].lstrip("-").isdigit() else message.command[1])
        await rdb.add_channel(cid, target.id, target.title or "Channel", target.username)
        await message.reply(f"Added **{target.title}** (`{target.id}`) to search pool.")
    except Exception as e:
        await message.reply(f"Could not add channel: {e}")


@Client.on_message(custom_filter.command(commands=["rmchannel", "delchannel", "removechannel"]))
@anonadmin_checker
@rate_limit(limit_config=RATE_LIMIT_HEAVY)
@exception
async def rm_channel_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    if len(message.command) < 2:
        await message.reply("Usage: `/rmchannel <channel_id or @username>`")
        return
    removed = await rdb.remove_channel(cid, message.command[1])
    await message.reply("Removed channel." if removed else "Channel not found in search pool.")


@Client.on_message(custom_filter.command(commands=["channels", "reqchannels", "reqsettings"]))
@anonadmin_checker
@rate_limit(limit_config=RATE_LIMIT_HEAVY)
@exception
async def channels_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    s = await rdb.get_settings(cid)
    req_t = s.get("req_title") or s.get("req_channel") or "Not configured"
    daily_lim = s.get("daily_limit", 0)
    lim_str = f"{daily_lim}/day" if daily_lim > 0 else "Unlimited"

    lines = [
        f"> **Request Settings**\n\n"
        f"{G_BULLET} **Request Channel:** `{req_t}`\n"
        f"{G_BULLET} **Status:** `{'Enabled' if s.get('is_enabled', True) else 'Disabled'}`\n"
        f"{G_BULLET} **Daily Limit:** `{lim_str}`\n\n"
        f"**Search Channels:**"
    ]
    for idx, c in enumerate(s.get("channels", []), 1):
        lines.append(f"{G_BULLET} **{idx}. {c.get('title')}** — `{c.get('id')}`")
    if not s.get("channels"):
        lines.append("• `None. Use /addchannel <id>`")
    await message.reply("\n".join(lines))


@Client.on_message(custom_filter.command(commands=["reqmode", "requestmode"]))
@anonadmin_checker
@rate_limit(limit_config=RATE_LIMIT_HEAVY)
@exception
async def req_mode_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    if len(message.command) < 2:
        await message.reply("Usage: `/reqmode on` or `/reqmode off`")
        return
    enable = message.command[1].lower() in ("on", "enable", "yes", "true")
    await rdb.update_settings(cid, {"is_enabled": enable})
    await message.reply(f"Content requests are now **{'enabled' if enable else 'disabled'}**.")


@Client.on_message(custom_filter.command(commands=["reqlimit", "requestlimit"]))
@anonadmin_checker
@rate_limit(limit_config=RATE_LIMIT_HEAVY)
@exception
async def req_limit_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    if len(message.command) < 2:
        curr = await rdb.get_req_limit(cid)
        curr_str = f"**{curr} requests/day**" if curr > 0 else "**Disabled (Unlimited)**"
        await message.reply(f"> **Daily Request Limit**\n• Current limit: {curr_str}\n\n**Usage:** `/reqlimit <number>` (set to `0` or `off` to disable)")
        return
    arg = message.command[1].strip().lower()
    limit = 0 if arg in ("0", "off", "disable", "none") else int(arg) if arg.isdigit() else None
    if limit is None or limit < 0:
        await message.reply("Please specify a valid positive number for the daily limit, or `0` to disable.")
        return
    await rdb.set_req_limit(cid, limit)
    limit_str = f"**{limit} requests/day**" if limit > 0 else "**Disabled (Unlimited)**"
    await message.reply(f"Daily request limit has been set to {limit_str}.")


@Client.on_message(custom_filter.command(commands=["reqdone", "fulfillreq", "requestdone"]))
@anonadmin_checker
@rate_limit(limit_config=RATE_LIMIT_HEAVY)
@exception
async def req_done_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    if len(message.command) < 2:
        await message.reply("Usage: `/reqdone <req_id> [post_url]` (or reply to uploaded media with `/reqdone <req_id>`)")
        return

    raw_id = message.command[1]
    doc = await rdb.get_request(raw_id)
    if not doc:
        await message.reply(f"No request found with ID `#{raw_id}`.")
        return

    post_url = None
    if len(message.command) > 2:
        post_url = message.command[2].strip()
    else:
        reply = message.reply_to_message
        if reply and (reply.document or reply.video or reply.audio or reply.photo):
            post_url = reply.link or _post_url(message.chat.id, reply.id, message.chat.username)
        elif message.chat.username:
            post_url = f"https://t.me/{message.chat.username}"

    upd = await rdb.update_request_status(doc["_id"], "completed", post_url=post_url)
    if upd:
        _broadcast_update(client, upd)
        subs = len(upd.get("subscribers", []))
        clean_q = _clean_markdown(upd.get("query", ""))
        link_str = f"\n• Post: [Open Link]({post_url})" if post_url else ""
        await message.reply(f"> **Request Completed** • `#REQ-{upd['num']}`\n• Content: `{clean_q}`{link_str}\n• Notified **{subs}** subscriber(s) in PM.")


@Client.on_message(custom_filter.command(commands=["reqreject", "requestreject", "delreq"]))
@anonadmin_checker
@rate_limit(limit_config=RATE_LIMIT_HEAVY)
@exception
async def req_reject_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    if len(message.command) < 2:
        await message.reply("Usage: `/reqreject <req_id> [reason]`")
        return

    raw_id = message.command[1]
    reason = " ".join(message.command[2:]) if len(message.command) > 2 else "Unavailable or rejected by admin."
    doc = await rdb.get_request(raw_id)
    if not doc:
        await message.reply(f"No request found with ID `#{raw_id}`.")
        return

    upd = await rdb.update_request_status(doc["_id"], "rejected", reason=reason)
    if upd:
        _broadcast_update(client, upd)
        subs = len(upd.get("subscribers", []))
        clean_q = _clean_markdown(upd.get("query", ""))
        await message.reply(f"> **Request Rejected** • `#REQ-{upd['num']}`\n• Content: `{clean_q}`\n• Reason: `{reason}`\n• Notified **{subs}** subscriber(s) in PM.")


@Client.on_callback_query(filters.regex(r"^req:metoo:(req_\d+|\d+)"))
async def cb_metoo(client: Client, query: CallbackQuery):
    req_id = query.data.split(":")[2]
    doc = await rdb.get_request(req_id)
    if not doc:
        await query.answer("Request not found.", show_alert=True)
        return
    if query.from_user.id in doc.get("subscribers", []):
        await query.answer("You are already subscribed to this request!", show_alert=False)
        return
    await rdb.add_subscriber(doc["_id"], query.from_user.id)
    upd = await rdb.get_request(doc["_id"]) or doc
    await query.answer(f"Subscribed to #REQ-{doc['num']} alerts!", show_alert=True)
    try:
        _, markup = _render_req_card(upd)
        await query.message.edit_reply_markup(reply_markup=markup)
    except Exception:
        pass


@Client.on_callback_query(filters.regex(r"^req:(done|reject):(req_\d+|\d+)"))
async def cb_admin_action(client: Client, query: CallbackQuery):
    act, req_id = query.data.split(":")[1], query.data.split(":")[2]
    doc = await rdb.get_request(req_id)
    if not doc or doc.get("status") != "pending":
        await query.answer(f"Request is already {doc.get('status') if doc else 'not found'}.", show_alert=True)
        return

    try:
        member = await client.get_chat_member(query.message.chat.id, query.from_user.id)
        if member.status not in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            await query.answer("This action is only allowed for channel administrators.", show_alert=True)
            return
    except Exception as e:
        LOGGER.debug(f"Admin verification failed: {e}")
        await query.answer("Could not verify admin rights.", show_alert=True)
        return

    if act == "done":
        reply = query.message.reply_to_message
        post_url = None
        if reply and (reply.document or reply.video or reply.audio or reply.photo or reply.text):
            post_url = reply.link or _post_url(query.message.chat.id, reply.id, query.message.chat.username)
        elif query.message.chat.username:
            post_url = f"https://t.me/{query.message.chat.username}"

        upd = await rdb.update_request_status(doc["_id"], "completed", post_url=post_url)
        await query.answer("Marked completed! Notifying subscribers in PM...", show_alert=False)
    else:
        upd = await rdb.update_request_status(doc["_id"], "rejected", reason="Rejected by admin.")
        await query.answer("Request rejected.", show_alert=False)

    if upd:
        text, _ = _render_req_card(upd, is_admin=True)
        try:
            await query.message.edit_text(text, disable_web_page_preview=True)
        except Exception:
            pass
        _broadcast_update(client, upd)
