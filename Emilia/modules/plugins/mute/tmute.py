import html
from datetime import datetime

from pyrogram import Client
from pyrogram.enums import MessageEntityType, ParseMode
from pyrogram.errors import BadRequest
from pyrogram.types import Chat, ChatPermissions, Message

from Emilia import BOT_ID, custom_filter
from Emilia.helper.chat_status import (
    _verified_user_id,
    can_restrict_member,
    isBotAdmin,
    isUserAdmin,
)
from Emilia.helper.telegram_api import restrict_member_no_reactions
from Emilia.helper.time_checker import time_converter
from Emilia.utils.decorators import (
    anonadmin_checker,
    exception,
    log_to_channel,
    rate_limit,
)

MUTE_PERMISSIONS = ChatPermissions(can_send_messages=False)


@Client.on_message(custom_filter.command(commands=["tmute", "tempmute"]))
@rate_limit()
@exception
@log_to_channel
@anonadmin_checker
async def mute(client: Client, message: Message):
    if not await isUserAdmin(message):
        return
    if not await isBotAdmin(message):
        return

    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities
    reply = message.reply_to_message

    target_user = None
    time_val = None
    reason = None

    # Check if there is an explicit user entity in the command arguments (offset > 0)
    user_entity = None
    if entities:
        for ent in entities:
            if ent.offset > 0 and ent.type in (
                MessageEntityType.TEXT_MENTION,
                MessageEntityType.MENTION,
                MessageEntityType.TEXT_LINK,
            ):
                user_entity = ent
                break

    if user_entity:
        if user_entity.type == MessageEntityType.TEXT_MENTION:
            target_user = user_entity.user
        elif user_entity.type == MessageEntityType.MENTION:
            user_token = text[user_entity.offset : user_entity.offset + user_entity.length]
            try:
                target_user = await client.get_users(user_token)
            except Exception:
                target_user = None
        elif user_entity.type == MessageEntityType.TEXT_LINK:
            if user_entity.url and user_entity.url.startswith("tg://user?id="):
                try:
                    target_user = await client.get_users(
                        int(user_entity.url.split("=")[1])
                    )
                except Exception:
                    target_user = None

        if target_user:
            rest_text = text[user_entity.offset + user_entity.length :].strip()
            parts = rest_text.split(None, 1)
            if len(parts) >= 1:
                time_val = parts[0]
                reason = parts[1] if len(parts) > 1 else ""

    # Check if explicit username / numeric ID is provided as argument
    if not target_user:
        parts = text.split()
        if len(parts) >= 2 and (parts[1].startswith("@") or parts[1].isdigit()):
            try:
                target_user = await client.get_users(
                    int(parts[1]) if parts[1].isdigit() else parts[1]
                )
                if len(parts) >= 3:
                    time_val = parts[2]
                    reason = " ".join(parts[3:]) if len(parts) > 3 else ""
            except Exception:
                pass

    # If still not resolved and reply exists, use reply
    if not target_user and reply:
        if reply.from_user:
            target_user = reply.from_user
        elif reply.sender_chat:
            target_user = reply.sender_chat

        parts = text.split(None, 2)
        if len(parts) >= 2:
            time_val = parts[1]
            reason = parts[2] if len(parts) > 2 else ""

    # If no reply and no user specified
    if not target_user and not reply:
        parts = text.split()
        if len(parts) < 2:
            await message.reply(
                "I don't know who you're talking about, you're going to need to specify a user...!"
            )
            return
        await message.reply("I can't find that user.")
        return

    if not target_user:
        await message.reply("I can't find that user.")
        return

    if isinstance(target_user, Chat) or getattr(target_user, "first_name", None) is None:
        await message.reply("Cannot perform this command on anonymous admins / channels!")
        return

    if target_user.id == BOT_ID:
        await message.reply("Yup! Let me just ban myself. Yay!")
        return

    if not await can_restrict_member(message, target_user.id):
        await message.reply("Surely I don't plan to mute an admin.")
        return

    if not time_val:
        await message.reply(
            "Please give me some time interval to mute the user for!\n**Example**: /tmute @user 1m <reason>"
        )
        return

    temp_mute = await time_converter(message, time_val)
    if not temp_mute or not isinstance(temp_mute, datetime):
        return

    actor_id = (
        _verified_user_id(message)
        or (message.from_user.id if message.from_user else None)
        or (message.sender_chat.id if message.sender_chat else None)
    )
    actor_name = (
        message.from_user.first_name
        if message.from_user
        else (message.sender_chat.title if message.sender_chat else "Anonymous")
    )
    if actor_id:
        actor_html = f"<a href='tg://user?id={actor_id}'>{html.escape(actor_name)}</a>"
    else:
        actor_html = html.escape(actor_name)

    target_first_name = target_user.first_name or "User"
    target_html = f"<a href='tg://user?id={target_user.id}'>{html.escape(target_first_name)}</a>"

    msg = f"Yep! {target_html} has been temporarily muted for {time_val} by {actor_html}!"
    if reason:
        msg += f"\n\n<blockquote expandable>{html.escape(reason)}</blockquote>"

    until_ts = (
        int(temp_mute.timestamp())
        if hasattr(temp_mute, "timestamp")
        else int(temp_mute)
    )

    try:
        if not await restrict_member_no_reactions(
            message.chat.id, target_user.id, until_date=until_ts
        ):
            await client.restrict_chat_member(
                message.chat.id,
                target_user.id,
                permissions=MUTE_PERMISSIONS,
                until_date=temp_mute,
            )
        await message.reply_text(msg, parse_mode=ParseMode.HTML)
    except BadRequest:
        await message.reply("Give me `ban_user` rights to perform this command!")
        return

    return "TEMP_MUTE", target_user.id, target_first_name
