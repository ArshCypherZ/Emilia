import os
from asyncio import sleep

from pyrogram import Client, enums, filters
from pyrogram.errors import BadRequest, FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from vanitaspy import User

from Emilia import DEV_USERS, LOGGER, OWNER_ID, custom_filter, db
from Emilia.helper.disable import disable
from Emilia.mongo.afk_mongo import is_afk
from Emilia.mongo.karma_mongo import user_global_karma
from Emilia.mongo.user_info import *
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *
from Emilia.utils.auth import is_owner, is_dev

db_ = db.users

btn = InlineKeyboardMarkup(
    [[InlineKeyboardButton("Close", callback_data="close_info")]]
)


@Client.on_callback_query(filters.regex(pattern=r"close_info"))
async def close_info(_, cb):
    await cb.message.delete()


async def get_user_id(message, text: str):
    def is_int(text: str):
        try:
            int(text)
        except ValueError:
            return False
        return True

    text = text.strip()
    if is_int(text):
        return int(text)

    entities = message.entities
    app = message._client

    if len(entities) < 2:
        try:
            return (await app.get_users(text)).id
        except FloodWait as e:
            LOGGER.error(f"FloodWait for {e} seconds.")
            await sleep(e.value)

    entity = entities[1]

    if entity.type == enums.MessageEntityType.MENTION:
        m = await db_.find_one({"user_name": text.replace("@", "")})
        if m and m["user_id"]:
            return m["user_id"]
        try:
            return (await app.get_users(text)).id
        except FloodWait as e:
            LOGGER.error(f"FloodWait for {e} seconds.")
            await sleep(e.value)

    elif entity.type == enums.MessageEntityType.URL:
        m = await db_.find_one({"user_name": text.split("/")[-1]})
        if m and m["user_id"]:
            return m["user_id"]
        try:
            return (await app.get_users(text.split("/")[-1])).id
        except FloodWait as e:
            LOGGER.error(f"FloodWait for {e} seconds.")
            await sleep(e.value)

    elif entity.type == enums.MessageEntityType.TEXT_MENTION:
        return entity.user.id

    return None


async def get_id_reason(message, sender_chat=False):
    args = message.text.strip().split()
    text = message.text
    user = None
    reason = None
    replied = message.reply_to_message
    if replied:
        if not replied.from_user:
            if (
                replied.sender_chat
                and replied.sender_chat != message.chat.id
                and sender_chat
            ):
                id_ = replied.sender_chat.id
            else:
                return None, None
        else:
            id_ = replied.from_user.id

        if len(args) < 2:
            reason = None
        else:
            reason = text.split(None, 1)[1]
        return id_, reason

    if len(args) == 2:
        user = text.split(None, 1)[1]
        return await get_user_id(message, user), None

    if len(args) > 2:
        user, reason = text.split(None, 2)[1:]
        return await get_user_id(message, user), reason

    return user, reason


async def extract_user_id(message):
    return (await get_id_reason(message))[0]


us = User()


async def banned(user):
    chk = us.get_info(user)

    if chk["blacklisted"]:
        return True
    if not chk["blacklisted"]:
        return False


@Client.on_message(custom_filter.command(commands="info", disable=True))
@disable
async def _info(_, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id
    user_id = await extract_user_id(message)
    if not user_id:
        user_id = message.from_user.id
    try:
        user = await _.get_users(user_id)
    except Exception as e:
        return await message.reply_text(e)

    text = "**Info found**:\n\n"
    text += f"**User ID**: `{user_id}`\n"
    text += f"**DC ID**: `{user.dc_id}`\n\n"
    text += f"**First Name**: `{user.first_name}`\n"
    if user.last_name:
        text += f"**Last Name**: `{user.last_name}`\n"
    if user.username:
        text += f"**Username**: @{user.username}\n"
    text += f"**Link**: {user.mention}\n\n"
    try:
        karma = await user_global_karma(user_id)
        text += f"**Global Karma Points**: `{karma}`\n\n"
    except IndexError:
        pass
    text += f"**Premium User? {user.is_premium}**\n"
    if str(chat_id).startswith("-100"):
        ptext = "**Presence {}**"
        if await is_afk(user_id):
            text += ptext.format("AFK")
        else:
            try:
                member = await _.get_chat_member(chat_id, user_id)
                if member.status in [
                    enums.ChatMemberStatus.LEFT,
                    enums.ChatMemberStatus.BANNED,
                ]:
                    text += ptext.format("No")
                if member.status == enums.ChatMemberStatus.MEMBER:
                    text += ptext.format("Member")
                if member.status in [
                    enums.ChatMemberStatus.ADMINISTRATOR,
                    enums.ChatMemberStatus.OWNER,
                ]:
                    text += ptext.format("Admin")
            except BadRequest:
                text += ptext.format("No")

        try:
            mm = await _.get_chat_member(chat_id, user_id)
            if (
                member.status
                in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]
                and mm.custom_title
            ):
                text += f"\n\nThis user holds the title **{mm.custom_title}** here."

        except BadRequest:
            pass

    if is_owner(user_id):
        text += "\n\nHe is my cute neko Arshhhhhhhhh <3"

    elif is_dev(user_id):
        text += "\n\nOne of my developers, respect ++"

    if await banned(user_id):
        chec = us.get_info(user_id)
        text += "<b>\n\nVanitas:\n</b>"
        text += "<b>This person is banned in @SpamWatchingBot!</b>"
        text += f"\nReason: <pre>{chec['reason']}</pre>"
        text += "\nAppeal at @VanitasSupport"
    else:
        text += "<b>\n\n@SpamWatchingBot:</b> Not banned"

    if user.photo:
        pic = await _.download_media(user.photo.big_file_id)
        await _.send_photo(message.chat.id, photo=pic, caption=text, reply_markup=btn)
        os.remove(pic)
    else:
        await message.reply(text, reply_markup=btn)


@usage("/ginfo [chat id/username]")
@example("/ginfo @SpiralTechDivision")
@description(
    "This will fetch a group chat's information. It may not work if the bot is banned or have not seen the particular chat."
)
@Client.on_message(custom_filter.command(commands="ginfo", disable=True))
@disable
async def _ginfo(_, message):
    if len(message.text.split()) < 2:
        await usage_string(message, _ginfo)
        return
    arg = message.text.split()[1]
    chat_id = int(arg) if arg.isdigit() else str(arg)
    try:
        chat = await _.get_chat(chat_id)
        administrators = []
        async for m in _.get_chat_members(
            chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS
        ):
            administrators.append(m)
    except BaseException:
        return await message.reply_text(
            "Chat ID or Username is invalid, or else it is private. Add me there and try /ginfo again!"
        )
    text = f"**ID**: `{chat.id}`\n\n"
    text += f"**Title**: `{chat.title}`\n"
    text += f"**Chat Type**: `{str(chat.type)[9:]}`\n"
    text += f"**DC ID**: `{chat.dc_id}`\n"
    text += f"**Restricted**: `{chat.is_restricted}`\n"
    text += f"**Scam**: `{chat.is_scam}`\n"
    if chat.username:
        text += f"**Username**: @{chat.username}\n\n"
    text += "**Member Stats**:\n"
    text += f"**Admins**: `{len(administrators)}`\n"
    text += f"**Users**: `{chat.members_count}`\n\n"
    text += "**Admin List**"
    for i in administrators:
        if i.user.is_bot or i.user.is_deleted:
            pass
        text += f"\n• {i.user.mention}"
    await message.reply_text(text, reply_markup=btn)
    await sleep(10)


@usage("/gifid [reply to GIF media]")
@example("/gifid [reply to GIF media]")
@description("This will fetch integer ID for replied GIF media.")
@Client.on_message(custom_filter.command(commands="gifid", disable=True))
@disable
async def _ginfo0(_, message):
    replied = message.reply_to_message
    if replied and replied.animation:
        return await message.reply_text(f"**GIF ID**: `{replied.animation.file_id}`")
    await usage_string(message, _ginfo0)
    return


@Client.on_message(
    custom_filter.command(commands="setme", disable=True) & filters.group
)
@disable
async def _setme(_, message):
    user_id = message.from_user.id
    replied = message.reply_to_message
    if replied:
        user_id = replied.from_user.id
    if user_id in [777000, 1087968824]:
        return await message.reply_text("Some error occured!")
    try:
        info = message.text.split(None, 1)[1]
    except IndexError:
        return await message.reply_text("Give me something to update your information!")
    if len(info) > 70:
        return await message.reply_text(
            f"The info needs to be under 70 characters, you have {len(info)}!"
        )
    await set_me(user_id, info)
    return await message.reply_text("**Information Updated!**")


@Client.on_message(custom_filter.command(commands="me", disable=True))
@disable
async def _me(_, message):
    user_id = await extract_user_id(message)
    if not user_id:
        user_id = message.from_user.id
    mention = (await _.get_users(user_id)).mention
    info = await get_me(user_id)
    if not info:
        return await message.reply_text(
            f"{mention} hasn't set an info message about themself yet!"
        )
    return await message.reply_text(f"**{mention}**:\n{info}")


@Client.on_message(
    custom_filter.command(commands="setbio", disable=True) & filters.group
)
@disable
async def _setme(_, message):
    user_id = message.from_user.id
    replied = message.reply_to_message
    if replied:
        user_id = replied.from_user.id
    if user_id in [777000, 1087968824]:
        return await message.reply_text("Some error occured!")
    try:
        bio = message.text.split(None, 1)[1]
    except IndexError:
        return await message.reply_text("Give me something to update information!")
    if len(bio) > 70:
        return await message.reply_text(
            f"The info needs to be under 70 characters, you gave {len(bio)}"
        )
    await set_bio(user_id, bio)
    return await message.reply_text("**Information Updated!**")


@Client.on_message(custom_filter.command(commands="bio", disable=True))
@disable
async def _me(_, message):
    user_id = await extract_user_id(message)
    if not user_id:
        user_id = message.from_user.id
    mention = (await _.get_users(user_id)).mention
    bio = await get_bio(user_id)
    if not bio:
        return await message.reply_text(
            f"{mention} hasn't set an info message about themself yet!"
        )
    return await message.reply_text(f"**{mention}**:\n{bio}")
