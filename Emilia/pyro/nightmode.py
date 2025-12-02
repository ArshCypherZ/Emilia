from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from Emilia import LOGGER, custom_filter
from Emilia.helper.chat_status import check_user, isUserAdmin
from Emilia.mongo.nightmode_mongo import (
    get_nightchats,
    nightdb,
    nightmode_off,
    nightmode_on,
)

CLOSE_CHAT = ChatPermissions(
    can_send_messages=False,
    can_send_media_messages=False,
    can_send_other_messages=False,
    can_send_polls=False,
    can_change_info=False,
    can_add_web_page_previews=False,
    can_pin_messages=False,
    can_invite_users=False,
)


OPEN_CHAT = ChatPermissions(
    can_send_messages=True,
    can_send_media_messages=True,
    can_send_other_messages=True,
    can_send_polls=True,
    can_change_info=True,
    can_add_web_page_previews=True,
    can_pin_messages=True,
    can_invite_users=True,
)


buttons = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("Enable Nightmode", callback_data="add_night"),
            InlineKeyboardButton("Disable Nightmode", callback_data="rm_night"),
        ]
    ]
)


@Client.on_message(custom_filter.command(commands="nightmode") & filters.group)
async def _nightmode(_, message):
    if not await check_user(message, privileges="can_change_info"):
        return
    return await message.reply(
        text="Choose one option from below buttons", reply_markup=buttons
    )


@Client.on_callback_query(filters.regex("^(add_night|rm_night)$"))
async def nightcb(app: Client, query: CallbackQuery):
    data = query.data
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    check_night = await nightdb.find_one({"chat_id": chat_id})
    if not await isUserAdmin(
        query.message, chat_id=chat_id, user_id=user_id, silent=True, pm_mode=True
    ):
        return await query.answer(text="Be an admin first.", show_alert=True)
    if data == "add_night":
        if check_night:
            await query.answer(
                text="Nightmode has been already enabled here!", show_alert=True
            )
        await nightmode_on(chat_id)
        await query.message.reply("Enabled nightmode for this chat!")
        await query.message.delete()
    if data == "rm_night":
        if check_night:
            await nightmode_off(chat_id)
            await query.message.reply("Disabled nightmode for this chat!")
            await query.message.delete()
        await query.answer(
            text="Nightmode has been already disabled here!", show_alert=True
        )


async def start_nightmode(client):
    chats = []
    schats = await get_nightchats()

    for chat in schats:
        chats.append(int(chat["chat_id"]))

    if len(chats) == 0:
        return

    for add_chat in chats:
        try:
            await client.set_chat_permissions(add_chat, CLOSE_CHAT)
            await client.send_message(
                add_chat,
                text="Nightmode [12 AM] has been started! Closing this group...come back later <3",
            )

        except Exception as e:
            LOGGER.error(f"Unable To close group {add_chat} - {e}")


async def close_nightmode(client):
    chats = []
    schats = await get_nightchats()
    for chat in schats:
        chats.append(int(chat["chat_id"]))
    if len(chats) == 0:
        return
    for rm_chat in chats:
        try:
            await client.set_chat_permissions(rm_chat, OPEN_CHAT)
            await client.send_message(
                rm_chat,
                text="Nightmode [6 AM] has been closed! Opening this group...good morning everyone <3",
            )
        except Exception as e:
            LOGGER.error(f"Unable To open group {rm_chat} - {e}")


scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


def start_nightmode_scheduler(client):
    scheduler.add_job(start_nightmode, trigger="cron", hour=23, minute=59, args=[client])
    scheduler.add_job(close_nightmode, trigger="cron", hour=6, minute=1, args=[client])
    scheduler.start()