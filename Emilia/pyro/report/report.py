from asyncio import sleep

from pyrogram import Client, enums, filters

from Emilia import custom_filter
from Emilia.helper.chat_status import isUserAdmin
from Emilia.mongo.report_mongo import get_report


async def report_(client, message):
    chat_id = message.chat.id

    if not (await get_report(chat_id)):
        return

    if await isUserAdmin(message, silent=True):
        return await message.reply(
            "You're an admin here, why'd you need to report someone?"
        )

    if not message.reply_to_message:
        return await message.reply("Which user you want to report?")

    if await isUserAdmin(message.reply_to_message, silent=True):
        return await message.reply("You can't report admin.")

    reported_user = message.reply_to_message.from_user

    admin_data = client.get_chat_members(
        chat_id=chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS
    )

    ADMINS_TAG = str()
    TAG = "\u200b"
    async for admin in admin_data:
        if not admin.user.is_bot:
            ADMINS_TAG = ADMINS_TAG + f"[{TAG}](tg://user?id={admin.user.id})"

    await message.reply(f"Reported {reported_user.mention} to admins.{ADMINS_TAG}")
    await sleep(10)


@Client.on_message(custom_filter.command(commands="report"))
async def report(client, message):
    await report_(client, message)


@Client.on_message(filters.regex(pattern=(r"(?i)@admin(s)?")))
async def regex_report(client, message):
    await report_(client, message)