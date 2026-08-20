import base64
import random

from pyrogram.enums import ChatType, MessageEntityType
from pyrogram.file_id import FileId, FileType
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultCachedSticker,
)


import Emilia.strings as strings
from Emilia import db
from Emilia.custom_filter import InlineQuery
from Emilia.custom_filter import callbackquery as Callback
from Emilia.custom_filter import register as command
from Emilia.helper.admins import can_change_info
from Emilia.utils.async_http import post

qr = {}
quotly = db.quotly


async def set_qrate(chat_id, mode: bool):
    await quotly.update_one(
        {"chat_id": chat_id}, {"$set": {"qrate": mode}}, upsert=True
    )


async def get_qrate(chat_id):
    q = await quotly.find_one({"chat_id": chat_id})
    if q:
        return q.get("qrate") or False
    return False


async def add_quote(chat_id, quote):
    await quotly.update_one(
        {"chat_id": chat_id}, {"$push": {"quotes": quote}}, upsert=True
    )


async def get_quotes(chat_id):
    q = await quotly.find_one({"chat_id": chat_id})
    if q:
        return q["quotes"]
    return False


def _quote_file_id(entry):
    # new quotes store a pyrogram file_id string; legacy Telethon
    # entries stored [id, access_hash, file_reference]. dc_id is not used when
    # re-sending media by file_id, so a placeholder value works for those.
    if isinstance(entry, str):
        return entry
    return FileId(
        file_type=FileType.STICKER,
        dc_id=4,
        media_id=int(entry[0]),
        access_hash=int(entry[1]),
        file_reference=bytes(entry[2]) if entry[2] else b"",
    ).encode()


def _rate_buttons(cd):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👍", callback_data=f"upq_{cd}"),
                InlineKeyboardButton("👎", callback_data=f"doq_{cd}"),
            ]
        ]
    )


import re

from webcolors import name_to_hex


@command(pattern="q")
async def _quotly_api_(client, e):
    if not e.reply_to_message_id:
        return await e.reply_text("This has to be send while replying to a message.")
    r = e.reply_to_message
    try:
        d = e.text.split(maxsplit=1)[1]
    except IndexError:
        d = ""

    color = "#1b1429"
    # Find Hex Colors
    hex_match = re.search(r"#(?:[0-9a-fA-F]{3}){1,2}\b", d)
    if hex_match:
        color = hex_match.group(0)
        d = d.replace(color, "")
    else:
        # Find Named Colors
        for word in d.split():
            try:
                color = name_to_hex(word.lower())
                d = d.replace(word, "")
                break
            except ValueError:
                pass

    photo = True if "p" in d.split() else False
    messages = []

    num_match = re.search(r"\b\d+\b", d)
    num = int(num_match.group(0)) if num_match else None
    if num:
        num = min(num, 25)  # Clamp to prevent API abuse

    msgs = (
        [
            i
            for i in await client.get_messages(
                e.chat.id,
                list(range(e.reply_to_message_id, e.reply_to_message_id + num)),
            )
            if i and not i.empty
        ]
        if num
        else [r]
    )
    c = [1]
    for _x in msgs:
        if _x:
            if _x.sender_chat:
                _name = _x.chat.title
                _first_name = _last_name = _username = ""
                _id = _x.chat.id
                _title = "Admin"
            elif _x.from_user:
                _name = _x.from_user.first_name
                _name = (
                    _name + _x.from_user.last_name if _x.from_user.last_name else _name
                )
                fwd_name = getattr(_x.forward_origin, "sender_user_name", None)
                if fwd_name:
                    _name = fwd_name
                _first_name = _x.from_user.first_name
                _last_name = _x.from_user.last_name
                _username = _x.from_user.username
                _id = _x.from_user.id
                _title = "Admin"
            else:
                _name = _x.chat.title
                _first_name = _last_name = _x.chat.title
                _username = ""
                _id = _x.chat.id
                _title = "Anon"
            _text = _x.text or _x.caption or ""
            _from = {
                "id": _id,
                # "first_name": _first_name,
                # "last_name": _last_name,
                "username": _username,
                "language_code": "en",
                "title": _title,
                "type": "group",
                "name": _name if c[-1] != _id else "",
            }
            if len(msgs) == 1:
                if _x.reply_to_message_id and "r" in d:
                    reply = _x.reply_to_message or await client.get_messages(
                        e.chat.id, _x.reply_to_message_id
                    )
                    if reply.sender_chat:
                        _r = {
                            "chatId": e.chat.id,
                            "username": reply.chat.username,
                            "text": reply.text or reply.caption or "",
                            "name": reply.chat.title,
                            "entities": get_entites(reply),
                        }
                    elif reply.from_user:
                        name = reply.from_user.first_name
                        name = (
                            name + " " + reply.from_user.last_name
                            if reply.from_user.last_name
                            else name
                        )
                        fwd_name = getattr(
                            reply.forward_origin, "sender_user_name", None
                        )
                        if fwd_name:
                            _name = fwd_name
                        _r = {
                            "chatId": e.chat.id,
                            "username": reply.from_user.username,
                            "text": reply.text or reply.caption or "",
                            "name": name,
                            "entities": get_entites(reply),
                        }
                    else:
                        _r = {}
                else:
                    _r = {}
            else:
                _r = {}
            if _x.sticker:
                mediaType = "sticker"
                media = [
                    {
                        "file_id": _x.sticker.file_id,
                        "file_size": _x.sticker.file_size,
                        "height": _x.sticker.height,
                        "width": _x.sticker.width,
                    }
                ]
            elif _x.photo:
                mediaType = "photo"
                media = [
                    {
                        "file_id": _x.photo.file_id,
                        "file_size": _x.photo.file_size,
                        "height": _x.photo.height,
                        "width": _x.photo.width,
                    }
                ]
            else:
                media = None
            voice = None
            if _x.voice:
                mediaType = "voice"
                voice = {
                    "waveform": list(_x.voice.waveform) if _x.voice.waveform else []
                }
            avatar = True
            if c[-1] == _id:
                avatar = False
            c.append(_id)
            msg_payload = {
                "chatId": e.chat.id,
                "avatar": avatar,
                "from": _from,
                "replyMessage": _r,
            }
            if media:
                msg_payload["media"] = media
                msg_payload["mediaType"] = mediaType
            if voice:
                msg_payload["voice"] = voice
                msg_payload["mediaType"] = mediaType
            if not media and not voice:
                msg_payload["entities"] = get_entites(_x)
                msg_payload["text"] = _text
            messages.append(msg_payload)
    post_data = {
        "type": "quote",
        "backgroundColor": color,
        "width": 512,
        "height": 768,
        "scale": 3,
        "messages": messages,
        "botToken": client.bot_token,
    }
    req = await post(
        "http://127.0.0.1:8432/generate",
        json=post_data,
        timeout=60,
    )
    if await get_qrate(e.chat.id):
        cd = str(e.id) + "|" + str(0) + "|" + str(0)
        buttons = _rate_buttons(cd)
        qr[e.id] = [[], []]
    else:
        buttons = None
    try:
        json_resp = req.json()
        if "result" in json_resp:
            fq = json_resp["result"]["image"]
        else:
            fq = json_resp["image"]
        buffer = base64.b64decode(fq.encode("utf-8"))
        from Emilia.utils.executors import run_in_thread

        def write_file_sync(path, data):
            with open(path, "wb") as f:
                f.write(data)

        if photo:
            await run_in_thread(write_file_sync, "gay.png", buffer)
        else:
            await run_in_thread(write_file_sync, "gay.webp", buffer)

        if photo:
            qs = await e.reply_document(
                "gay.png", reply_parameters=None, reply_markup=buttons
            )
        else:
            qs = await e.reply_sticker(
                "gay.webp", reply_parameters=None, reply_markup=buttons
            )
        await add_quote(
            e.chat.id,
            qs.sticker.file_id if qs.sticker else qs.document.file_id,
        )
    except Exception as ep:
        await e.reply_text("error: " + str(ep))


ENTITY_MAP = {
    MessageEntityType.CODE: "code",
    MessageEntityType.BOLD: "bold",
    MessageEntityType.ITALIC: "italic",
    MessageEntityType.BOT_COMMAND: "bot_command",
    MessageEntityType.URL: "url",
    MessageEntityType.EMAIL: "email",
    MessageEntityType.PHONE_NUMBER: "phone_number",
    MessageEntityType.UNDERLINE: "underline",
    MessageEntityType.MENTION: "mention",
    MessageEntityType.CUSTOM_EMOJI: "custom_emoji",
}


def get_entites(x):
    q = []
    for y in x.entities or x.caption_entities or []:
        type = ENTITY_MAP.get(y.type)
        if type is None:
            continue
        entity_obj = {"type": type, "offset": y.offset, "length": y.length}
        if type == "custom_emoji" and y.custom_emoji_id:
            entity_obj["custom_emoji_id"] = str(y.custom_emoji_id)
        q.append(entity_obj)
    return q


@command(pattern="qrate")
async def e_q_rating(client, e):
    if e.chat.type == ChatType.PRIVATE:
        return await e.reply_text("This command is made to be used in group chats.")
    if not e.from_user:
        return
    if not await can_change_info(e, e.from_user.id):
        return
    try:
        d = e.text.split(maxsplit=1)[1]
    except IndexError:
        if await get_qrate(e.chat.id):
            await e.reply_text("Quotes rating is on.")
        else:
            await e.reply_text("Rating for quotes is off.")
        return
    if d in ["True", "yes", "on", "y"]:
        await e.reply_text("Quotes rating has been turned on.")
        await set_qrate(e.chat.id, True)
    elif d in ["False", "no", "off", "n"]:
        await e.reply_text("Rating for quotes has been turned off.")
        await set_qrate(e.chat.id, False)
    else:
        await e.reply_text(strings.YES_NO_ON_OFF)


@Callback(pattern="upq_(.*)")
async def quotly_upvote(client, e):
    d = e.pattern_match.group(1)
    x, y, z = d.split("|")
    x, y, z = int(x), int(y), int(z)
    try:
        ya = qr[x]
    except KeyError:
        # vote data lost (e.g. restart) — drop the buttons
        return await e.edit_message_reply_markup(None)
    if e.from_user.id in ya[0]:
        y -= 1
        qr[x][0].remove(e.from_user.id)
        await e.answer("you got your vote back")
    elif e.from_user.id in ya[1]:
        y += 1
        z -= 1
        qr[x][1].remove(e.from_user.id)
        qr[x][0].append(e.from_user.id)
        await e.answer("you 👍 this")
    elif e.from_user.id not in ya[0]:
        y += 1
        qr[x][0].append(e.from_user.id)
        await e.answer("you 👍 this")
    cd = "{}|{}|{}".format(x, y, z)
    if y == 0:
        y = ""
    if z == 0:
        z = ""
    await e.edit_message_reply_markup(
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(f"👍 {y}", callback_data=f"upq_{cd}"),
                    InlineKeyboardButton(f"👎 {z}", callback_data=f"doq_{cd}"),
                ]
            ]
        )
    )


@Callback(pattern="doq_(.*)")
async def quotly_downvote(client, e):
    d = e.pattern_match.group(1)
    x, y, z = d.split("|")
    x, y, z = int(x), int(y), int(z)
    try:
        ya = qr[x]
    except KeyError:
        # vote data lost (e.g. restart) — drop the buttons
        return await e.edit_message_reply_markup(None)
    if e.from_user.id in ya[1]:
        z -= 1
        qr[x][1].remove(e.from_user.id)
        await e.answer("you got your vote back")
    elif e.from_user.id in ya[0]:
        z += 1
        y -= 1
        qr[x][0].remove(e.from_user.id)
        qr[x][1].append(e.from_user.id)
        await e.answer("you 👎 this")
    elif e.from_user.id not in ya[1]:
        z += 1
        qr[x][1].append(e.from_user.id)
        await e.answer("you 👎 this")
    cd = "{}|{}|{}".format(x, y, z)
    if y == 0:
        y = ""
    if z == 0:
        z = ""
    await e.edit_message_reply_markup(
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(f"👍 {y}", callback_data=f"upq_{cd}"),
                    InlineKeyboardButton(f"👎 {z}", callback_data=f"doq_{cd}"),
                ]
            ]
        )
    )


@command(pattern="qtop")
async def qtop_q(client, e):
    await e.reply_text(
        "**Top group quotes:**",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Open top",
                        switch_inline_query_current_chat="top:{}".format(e.chat.id),
                    )
                ]
            ]
        ),
    )


@InlineQuery(pattern="top:(.*)")
async def qtop_cb_(client, inline_query):
    x = inline_query.pattern_match.group(1)
    q = await get_quotes(int(x))
    if not q:
        return
    c = []
    xe = False
    n = 0
    # inline queries carry no chat id; use the group id from the query
    if await get_qrate(int(x)):
        qr[int(inline_query.id)] = [[], []]
        cd = str(inline_query.id) + "|" + str(0) + "|" + str(0)
        xe = True
    for _x in q:
        n += 1
        c.append(
            InlineQueryResultCachedSticker(
                sticker_file_id=_quote_file_id(_x),
                id=str(n),
                reply_markup=(_rate_buttons(cd) if xe else None),
            )
        )
    await inline_query.answer(c, is_gallery=True)


@command(pattern="qrand")
async def qrand_s_(client, e):
    q = await get_quotes(e.chat.id)
    if not q:
        return
    c, xe = random.choice(q), False
    if await get_qrate(e.chat.id):
        qr[e.id] = [[], []]
        cd = str(e.id) + "|" + str(0) + "|" + str(0)
        xe = True
    await e.reply_sticker(
        _quote_file_id(c),
        reply_markup=(_rate_buttons(cd) if xe else None),
    )
