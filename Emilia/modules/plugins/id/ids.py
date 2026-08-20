from pyrogram import Client
from pyrogram.enums import MessageEntityType
from pyrogram.types import LinkPreviewOptions

from Emilia import LOGGER, custom_filter, db
from Emilia.helper.disable import disable
from Emilia.helper.forward_origin import fwd_chat
from Emilia.helper.get_user import get_user_id

user_ = db.users


@Client.on_message(custom_filter.command(commands="id", disable=True))
@disable
async def getid(client, message):
    chat = message.chat

    if message.sender_chat:
        your_id = message.sender_chat.id
    else:
        your_id = message.from_user.id

    message_id = message.id
    reply = message.reply_to_message

    if message.link:
        text = f"**[Message ID:]({message.link})** `{message_id}`\n"
    else:
        text = f"**Message ID:** `{message_id}`\n"

    text += f"**[Your ID:](tg://user?id={your_id})** `{your_id}`\n"

    # Check if there are arguments to resolve a specific user
    text_content = message.text or ""
    has_args = len(text_content.split()) >= 2
    if not has_args and message.entities:
        for ent in message.entities:
            if ent.offset > 0:
                has_args = True
                break

    if has_args:
        try:
            user_info = await get_user_id(message)
            if user_info:
                user_id = user_info.id
                u_name = getattr(user_info, "username", None) or getattr(user_info, "first_name", None) or getattr(user_info, "title", "")
                text += f"**[User ID:](tg://user?id={user_id})** `{user_id}`"
                if u_name:
                    text += f" ({u_name})"
                text += "\n"

        except IndexError:
            pass

        except Exception as e:
            LOGGER.error(e)
            return await message.reply_text(
                "Could not find a user by this name; are you sure I've seen them before?",
            )

    chat_name = chat.title or chat.first_name or ""
    if chat.username:
        text += f"**[Chat ID:](https://t.me/{chat.username})** `{chat.id}`"
    else:
        text += f"**Chat ID:** `{chat.id}`"
    if chat_name:
        text += f" ({chat_name})"
    text += "\n\n"

    if (
        not getattr(reply, "empty", True)
        and not fwd_chat(message)
        and not reply.sender_chat
        and not message.reply_to_message.new_chat_members
    ):
        if reply.link:
            text += f"**[Replied Message ID:]({reply.link})** `{reply.id}`\n"
        else:
            text += f"**Replied Message ID:** `{reply.id}`\n"
            
        reply_user = reply.from_user
        if reply_user:
            ru_name = reply_user.username or reply_user.first_name or ""
            text += f"**[Replied User ID:](tg://user?id={reply_user.id})** `{reply_user.id}`"
            if ru_name:
                text += f" ({ru_name})"
            text += "\n\n"

    reply_fwd_chat = reply and fwd_chat(reply)
    if reply_fwd_chat:
        fwd_name = reply_fwd_chat.title or reply_fwd_chat.first_name or ""
        text += f"The forwarded channel/chat, {fwd_name}, has an id of `{reply_fwd_chat.id}`\n\n"

    if reply and reply.sender_chat:
        sender_name = reply.sender_chat.title or reply.sender_chat.first_name or ""
        text += f"ID of the replied chat/channel, is `{reply.sender_chat.id}`"
        if sender_name:
            text += f" ({sender_name})"
        text += "\n"

    if reply and message.reply_to_message.new_chat_members:
        for x in message.reply_to_message.new_chat_members:
            meow = x.id
            meow_name = x.username or x.first_name or getattr(x, "title", "")
            text += f"Added user has an ID of `{meow}`"
            if meow_name:
                text += f" ({meow_name})"
            text += "\n"

    if reply and reply.sticker:
        text += f"\n**Sticker ID**: `{reply.sticker.file_id}`"

    if reply and reply.animation:
        text += f"\n**GIF ID**: `{reply.animation.file_id}`"
        
    if reply and reply.audio:
        text += f"\n**Audio ID**: `{reply.audio.file_id}`"
        
    if reply and reply.document:
        text += f"\n**Document ID**: `{reply.document.file_id}`"
        
    if reply and reply.photo:
        text += f"\n**Photo ID**: `{reply.photo.file_id}`"
        
    if reply and reply.video:
        text += f"\n**Video ID**: `{reply.video.file_id}`"
        
    if reply and reply.voice:
        text += f"\n**Voice ID**: `{reply.voice.file_id}`"
        
    if reply and getattr(reply, "video_note", None):
        text += f"\n**Video Note ID**: `{reply.video_note.file_id}`"

    await message.reply_text(
        text, link_preview_options=LinkPreviewOptions(is_disabled=True)
    )
