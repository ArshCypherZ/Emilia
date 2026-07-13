from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from Emilia import custom_filter
from Emilia.utils.cb_token import stash, unstash
from Emilia.utils.data_parser import get_wo, get_wols
from Emilia.utils.db import get_collection
from Emilia.utils.helper import check_user, control_user

DC = get_collection("DISABLED_CMDS")


@Client.on_message(custom_filter.command(commands="watch"))
@control_user
async def get_watch_order(client: Client, message: Message, mdata: dict):
    """Get List of Scheduled Anime"""
    gid = mdata["chat"]["id"]
    find_gc = await DC.find_one({"_id": gid})
    if find_gc is not None and "watch" in find_gc["cmd_list"].split():
        return
    x = message.text.split(" ", 1)
    if len(x) == 1:
        await message.reply_text("Nothing given to search for!!!")
        return
    try:
        user = mdata["from_user"]["id"]
    except KeyError:
        user = mdata["sender_chat"]["id"]
    data = await get_wols(x[1])
    msg = f"Found related animes for the query {x[1]}"
    buttons = []
    if data == []:
        await client.send_message(gid, "No results found!!!")
        return
    # The raw query can be long; stash it in Redis and route via a short token
    # (kept as the LAST segment so token_urlsafe underscores don't break parsing).
    token = await stash({"qry": x[1]})
    for i in data:
        buttons.append(
            [
                InlineKeyboardButton(
                    str(i[1]), callback_data=f"watch_{i[0]}_0_{user}_{token}"
                )
            ]
        )
    await client.send_message(gid, msg, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex(pattern=r"watch_(.*)"))
@check_user
async def watch_(client: Client, cq: CallbackQuery, cdata: dict):
    kek, id_, req, user, token = cdata["data"].split("_", 4)
    payload = await unstash(token)
    if payload is None:
        return await cq.answer(
            "This button expired — run the command again.", show_alert=True
        )
    payload["qry"]
    msg, total = await get_wo(int(id_), int(req))
    totalpg, lol = divmod(total, 50)
    button = []
    if lol != 0:
        totalpg + 1
    if total > 50:
        # Reuse the same token (qry unchanged); only the page (req) varies.
        if int(req) == 0:
            button.append(
                [
                    InlineKeyboardButton(
                        text="》",
                        callback_data=f"{kek}_{id_}_{int(req)+1}_{user}_{token}",
                    )
                ]
            )
        elif int(req) == totalpg:
            button.append(
                [
                    InlineKeyboardButton(
                        text="《",
                        callback_data=f"{kek}_{id_}_{int(req)-1}_{user}_{token}",
                    )
                ]
            )
        else:
            button.append(
                [
                    InlineKeyboardButton(
                        text="《",
                        callback_data=f"{kek}_{id_}_{int(req)-1}_{user}_{token}",
                    ),
                    InlineKeyboardButton(
                        text="》",
                        callback_data=f"{kek}_{id_}_{int(req)+1}_{user}_{token}",
                    ),
                ]
            )
    button.append([InlineKeyboardButton("Back", callback_data=f"wol_{user}_{token}")])
    await cq.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(button))


@Client.on_callback_query(filters.regex(pattern=r"wol_(.*)"))
async def wls(client: Client, cq: CallbackQuery):
    kek, user, token = cq.data.split("_", 2)
    payload = await unstash(token)
    if payload is None:
        return await cq.answer(
            "This button expired — run the command again.", show_alert=True
        )
    qry = payload["qry"]
    data = await get_wols(qry)
    msg = f"Found related animes for the query {qry}"
    buttons = []
    for i in data:
        buttons.append(
            [
                InlineKeyboardButton(
                    str(i[1]), callback_data=f"watch_{i[0]}_0_{user}_{token}"
                )
            ]
        )
    await cq.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons))
