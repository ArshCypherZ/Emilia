# uses jikanpy (Jikan API)
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from Emilia import custom_filter
from Emilia.utils.data_parser import get_scheduled
from Emilia.utils.db import get_collection
from Emilia.utils.helper import control_user, get_btns

DC = get_collection("DISABLED_CMDS")


@Client.on_message(custom_filter.command(commands="schedule"))
@control_user
async def get_schuled(client: Client, message: Message, mdata: dict):
    """Get List of Scheduled Anime"""
    gid = mdata["chat"]["id"]
    find_gc = await DC.find_one({"_id": gid})
    if find_gc is not None and "schedule" in find_gc["cmd_list"].split():
        return
    x = await client.send_message(gid, "<code>Fetching Scheduled Animes</code>")
    try:
        user = mdata["from_user"]["id"]
    except KeyError:
        user = mdata["sender_chat"]["id"]
    msg = await get_scheduled()
    buttons = get_btns("SCHEDULED", result=[msg[1]], user=user)
    await x.edit_text(msg[0], reply_markup=buttons)


@Client.on_callback_query(filters.regex(pattern=r"sched_(.*)"))
async def ns_(client: Client, cq: CallbackQuery):
    kek, day, user = cq.data.split("_")
    msg = await get_scheduled(int(day))
    buttons = get_btns("SCHEDULED", result=[int(day)], user=user)
    await cq.edit_message_text(msg[0], reply_markup=buttons)
