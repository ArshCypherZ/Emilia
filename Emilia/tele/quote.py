import base64
import random

from Emilia.utils.async_http import post
from telethon import Button, types
from webcolors import hex_to_name, name_to_hex

from Emilia import LOGGER, db
from Emilia.custom_filter import InlineQuery
from Emilia.custom_filter import callbackquery as Callback
from Emilia.custom_filter import register as command
from Emilia.functions.admins import can_change_info

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


@command(pattern="q")
async def _quotly_api_(e):
    if not e.reply_to:
        return await e.reply("This has to be send while replying to a message.")
    r = await e.get_reply_message()
    try:
        d = e.text.split(maxsplit=1)[1]
    except IndexError:
        d = ""
    color = None
    for y in d.split():
        try:
            color, g = name_to_hex(y), "hex"
        except ValueError:
            try:
                color, g = hex_to_name(y), "name"
            except ValueError:
                continue
    if color:
        d = d.replace(hex_to_name(color) if g == "hex" else color, "")
    else:
        color = "#1b1429"
    photo = True if "p" in d else False
    messages = []
    num = [int(x) for x in d.split() if x.isdigit()]
    num = num[0] if num else None
    msgs = (
        [
            i
            async for i in e.client.iter_messages(
                e.chat_id,
                ids=list(range(e.reply_to_msg_id, e.reply_to_msg_id + num)),
            )
            if i
        ]
        if num
        else [r]
    )
    c = [1]
    for _x in msgs:
        if _x:
            if _x.sender and isinstance(_x.sender, types.Channel):
                _name = _x.chat.title
                _first_name = _last_name = _username = ""
                _id = _x.chat_id
                _title = "Admin"
            elif _x.sender and isinstance(_x.sender, types.User):
                _name = _x.sender.first_name
                _name = _name + _x.sender.last_name if _x.sender.last_name else _name
                if _x.fwd_from and _x.fwd_from.from_name:
                    _name = _x.fwd_from.from_name
                _first_name = _x.sender.first_name
                _last_name = _x.sender.last_name
                _username = _x.sender.username
                _id = _x.sender_id
                _title = "Admin"
            elif not _x.sender:
                _name = _x.chat.title
                _first_name = _last_name = _x.chat.title
                _username = ""
                _id = _x.chat_id
                _title = "Anon"
            _text = _x.raw_text or ""
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
                if _x.reply_to and "r" in d:
                    reply = await _x.get_reply_message()
                    if isinstance(reply.sender, types.Channel):
                        _r = {
                            "chatId": e.chat_id,
                            # "first_name": reply.chat.title,
                            # "last_name": "",
                            "username": reply.chat.username,
                            "text": reply.text,
                            "name": reply.chat.title,
                        }
                    elif reply.sender:
                        name = reply.sender.first_name
                        name = (
                            name + " " + reply.sender.last_name
                            if reply.sender.last_name
                            else name
                        )
                        if reply.fwd_from and reply.fwd_from.from_name:
                            _name = reply.fwd_from.from_name
                        _r = {
                            "chatId": e.chat_id,
                            # "first_name": reply.sender.first_name,
                            # "last_name": reply.sender.last_name,
                            "username": reply.sender.username,
                            "text": reply.text,
                            "name": name,
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
                        "file_id": _x.file.id,
                        "file_size": _x.file.size,
                        "height": _x.file.height,
                        "width": _x.file.width,
                    }
                ]
            elif _x.photo:
                mediaType = "photo"
                media = [
                    {
                        "file_id": _x.file.id,
                        "file_size": _x.file.size,
                        "height": _x.file.height,
                        "width": _x.file.width,
                    }
                ]
            else:
                media = None
            avatar = True
            if c[-1] == _id:
                avatar = False
            c.append(_id)
            if not media:
                messages.append(
                    {
                        "entities": get_entites(_x),
                        "chatId": e.chat_id,
                        "avatar": avatar,
                        "from": _from,
                        "text": _text,
                        "replyMessage": _r,
                    }
                )
            elif media:
                messages.append(
                    {
                        "chatId": e.chat_id,
                        "avatar": avatar,
                        "media": media,
                        "mediaType": mediaType,
                        "from": _from,
                        "replyMessage": {},
                    }
                )
    post_data = {
        "type": "quote",
        "backgroundColor": color,
        "width": 512,
        "height": 768,
        "scale": 2,
        "messages": messages,
    }
    req = await post(
        "https://quoteapi-aqac.onrender.com/generate",
        json=post_data,
    )
    if await get_qrate(e.chat_id):
        cd = str(e.id) + "|" + str(0) + "|" + str(0)
        buttons = buttons = Button.inline("👍", data=f"upq_{cd}"), Button.inline(
            "👎", data=f"doq_{cd}"
        )
        qr[e.id] = [[], []]
    else:
        buttons = None
    try:
        fq = req.json()["result"]["image"]
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
            qs = await e.respond(file="gay.png", force_document=photo, buttons=buttons)
        else:
            qs = await e.respond(file="gay.webp", force_document=photo, buttons=buttons)
        await add_quote(
            e.chat_id,
            [
                qs.media.document.id,
                qs.media.document.access_hash,
                qs.media.document.file_reference,
            ],
        )
    except Exception as ep:
        await e.reply("error: " + str(ep))


def get_entites(x):
    q = []
    for y in x.entities or []:
        if isinstance(y, types.MessageEntityCode):
            type = "code"
        elif isinstance(y, types.MessageEntityBold):
            type = "bold"
        elif isinstance(y, types.MessageEntityItalic):
            type = "italic"
        elif isinstance(y, types.MessageEntityBotCommand):
            type = "bot_command"
        elif isinstance(y, types.MessageEntityUrl):
            type = "url"
        elif isinstance(y, types.MessageEntityEmail):
            type = "email"
        elif isinstance(y, types.MessageEntityPhone):
            type = "phone_number"
        elif isinstance(y, types.MessageEntityUnderline):
            type = "underline"
        elif isinstance(y, types.MessageEntityMention):
            type = "mention"
        else:
            continue
        q.append({"type": type, "offset": y.offset, "length": y.length})
    return q


@command(pattern="qrate")
async def e_q_rating(e):
    if e.is_private:
        return await e.reply("This command is made to be used in group chats.")
    if not e.from_id:
        return
    if not await can_change_info(e, e.sender_id):
        return
    try:
        d = e.text.split(maxsplit=1)[1]
    except IndexError:
        if await get_qrate(e.chat_id):
            await e.reply("Quotes rating is on.")
        else:
            await e.reply("Rating for quotes is off.")
        return
    if d in ["True", "yes", "on", "y"]:
        await e.reply("Quotes rating has been turned on.")
        await set_qrate(e.chat_id, True)
    elif d in ["False", "no", "off", "n"]:
        await e.reply("Rating for quotes has been turned off.")
        await set_qrate(e.chat_id, False)
    else:
        await e.reply("Your input was not recognised as one of: yes/no/on/off")


@Callback(pattern="upq_(.*)")
async def quotly_upvote(e):
    d = e.pattern_match.group(1).decode()
    x, y, z = d.split("|")
    x, y, z = int(x), int(y), int(z)
    try:
        ya = qr[x]
    except IndexError:
        await e.edit(buttons=None)
    if e.sender_id in ya[0]:
        y -= 1
        qr[x][0].remove(e.sender_id)
        await e.answer("you got your vote back")
    elif e.sender_id in ya[1]:
        y += 1
        z -= 1
        qr[x][1].remove(e.sender_id)
        qr[x][0].append(e.sender_id)
        await e.answer("you 👍 this")
    elif e.sender_id not in ya[0]:
        y += 1
        qr[x][0].append(e.sender_id)
        await e.answer("you 👍 this")
    cd = "{}|{}|{}".format(x, y, z)
    if y == 0:
        y = ""
    if z == 0:
        z = ""
    await e.edit(
        buttons=[
            Button.inline(f"👍 {y}", data=f"upq_{cd}"),
            Button.inline(f"👎 {z}", data=f"doq_{cd}"),
        ]
    )


@Callback(pattern="doq_(.*)")
async def quotly_downvote(e):
    d = e.pattern_match.group(1).decode()
    x, y, z = d.split("|")
    x, y, z = int(x), int(y), int(z)
    try:
        ya = qr[x]
    except IndexError:
        await e.edit(buttons=None)
    if e.sender_id in ya[1]:
        z -= 1
        qr[x][1].remove(e.sender_id)
        await e.answer("you got your vote back")
    elif e.sender_id in ya[0]:
        z += 1
        y -= 1
        qr[x][0].remove(e.sender_id)
        qr[x][1].append(e.sender_id)
        await e.answer("you 👎 this")
    elif e.sender_id not in ya[1]:
        z += 1
        qr[x][1].append(e.sender_id)
        await e.answer("you 👎 this")
    cd = "{}|{}|{}".format(x, y, z)
    if y == 0:
        y = ""
    if z == 0:
        z = ""
    await e.edit(
        buttons=[
            Button.inline(f"👍 {y}", data=f"upq_{cd}"),
            Button.inline(f"👎 {z}", data=f"doq_{cd}"),
        ]
    )


@command(pattern="qtop")
async def qtop_q(e):
    await e.reply(
        "**Top group quotes:**",
        buttons=Button.switch_inline(
            "Open top", "top:{}".format(e.chat_id), same_peer=True
        ),
    )


@InlineQuery(pattern="top:(.*)")
async def qtop_cb_(e):
    x = e.pattern_match.group(1)
    q = await get_quotes(int(x))
    if not q:
        return
    c = []
    xe = False
    n = 0
    if await get_qrate(e.chat_id):
        qr[e.id] = [[], []]
        cd = str(e.id) + "|" + str(0) + "|" + str(0)
        xe = True
    for _x in q:
        n += 1
        c.append(
            await e.builder.document(
                title=str(n),
                description=str(n),
                text=str(n),
                file=types.InputDocument(
                    id=_x[0], access_hash=_x[1], file_reference=_x[2]
                ),
                buttons=(
                    [
                        Button.inline("👍", data=f"upq_{cd}"),
                        Button.inline("👎", data=f"doq_{cd}"),
                    ]
                    if xe
                    else None
                ),
            )
        )
    await e.answer(c, gallery=True)


@command(pattern="qrand")
async def qrand_s_(e):
    q = await get_quotes(e.chat_id)
    if not q:
        return
    c, xe = random.choice(q), False
    if await get_qrate(e.chat_id):
        qr[e.id] = [[], []]
        cd = str(e.id) + "|" + str(0) + "|" + str(0)
        xe = True
    await e.reply(
        file=types.InputDocument(c[0], c[1], c[2]),
        buttons=(
            [
                Button.inline("👍", data=f"upq_{cd}"),
                Button.inline("👎", data=f"doq_{cd}"),
            ]
            if xe
            else None
        ),
    )