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
chatlevels = db.chatlevels

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
        return await message.reply_text(str(e))

    text = "**Info found**:\n\n"
    text += f"**User ID**: `{user_id}`\n"
    text += f"**First Name**: `{user.first_name}`\n"
    if user.last_name:
        text += f"**Last Name**: `{user.last_name}`\n"
    if user.username:
        text += f"**Username**: @{user.username}\n"
    text += f"**Link**: {user.mention}\n"
    try:
        karma = await user_global_karma(user_id)
        text += f"**Global Karma Points**: `{karma}`\n"
    except (IndexError, Exception):
        pass

    text += f"**Premium User?** {'Yes' if user.is_premium else 'No'}\n"
    if str(chat_id).startswith("-100"):
        text += "\n**Presence**: "
        member = None
        try:
            member = await _.get_chat_member(chat_id, user_id)
            status_map = {
                enums.ChatMemberStatus.OWNER: "Owner",
                enums.ChatMemberStatus.ADMINISTRATOR: "Administrator",
                enums.ChatMemberStatus.MEMBER: "Member",
                enums.ChatMemberStatus.LEFT: "Left",
                enums.ChatMemberStatus.BANNED: "Banned",
                enums.ChatMemberStatus.RESTRICTED: "Restricted"
            }
            status_str = status_map.get(member.status, "Unknown")
            text += f"{status_str}\n"
            
            if member.custom_title:
                text += f"This user holds the title **{member.custom_title}** here.\n"
                
        except BadRequest:
            text += "Not in Chat\n"
        
        # AFK Check
        if await is_afk(user_id):
            text += "Status: AFK\n"

    if is_owner(user_id):
        text += "\nHe is my cute neko Arsshhhhhhhhhh <3\n"
    elif is_dev(user_id):
        text += "\nOne of my developers, respect +++\n"

    try:
        if await banned(user_id):
            chec = us.get_info(user_id)
            text += "\n**Safety Status**:\n"
            text += "SpamWatch: BANNED\n"
            text += f"Reason: {chec['reason']}\n"
        else:
            # clean output: don't show "Not banned" if clean, or show minimal
            pass
    except Exception:
        pass

    # Chat Levels Info (Prestige & Rep)
    # DB Call - Fast
    try:
        level_doc = await chatlevels.find_one({"user_id": user_id, "chat_id": chat_id})
        if level_doc:
            prestige = level_doc.get("prestige", 0)
            rep = level_doc.get("reputation", 0)
            current_xp = level_doc.get("points", 0)
            
            if prestige > 0 or rep > 0 or current_xp > 0:
                text += "\n**Activity Stats**:\n"
                if prestige > 0:
                    text += f"**Prestige Level**: {prestige}\n"
                if rep > 0:
                    text += f"**Reputation**: {rep}\n"
                text += f"**XP**: {current_xp}\n"
    except Exception:
        pass

    # Media Dispatch
    # download_media is IO heavy.
    if user.photo:
        try:
            pic = await _.download_media(user.photo.big_file_id)
            await _.send_photo(message.chat.id, photo=pic, caption=text, reply_markup=btn)
            os.remove(pic)
        except Exception:
            # Fallback if download fails
            await message.reply(text, reply_markup=btn)
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
