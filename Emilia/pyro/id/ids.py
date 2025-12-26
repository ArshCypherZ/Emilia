from pyrogram import Client
from pyrogram.enums import MessageEntityType

from Emilia import LOGGER, custom_filter, db
from Emilia.helper.disable import disable

user_ = db.users


from Emilia.helper.get_user import get_user_id

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

    text = f"**[Message ID:]({message.link})** `{message_id}`\n"
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
                text += f"**[User ID:](tg://user?id={user_id})** `{user_id}`\n"

        except IndexError:
            pass

        except Exception as e:
            LOGGER.error(e)
            return await message.reply_text(
                "Could not find a user by this name; are you sure I've seen them before?",
                quote=True,
            )

    text += f"**[Chat ID:](https://t.me/{chat.username})** `{chat.id}`\n\n"

    if (
        not getattr(reply, "empty", True)
        and not message.forward_from_chat
        and not reply.sender_chat
        and not message.reply_to_message.new_chat_members
    ):
        text += (
            f"**[Replied Message ID:]({reply.link})** `{message.reply_to_message.id}`\n"
        )
        text += f"**[Replied User ID:](tg://user?id={reply.from_user.id})** `{reply.from_user.id}`\n\n"

    if reply and reply.forward_from_chat:
        text += f"The forwarded channel, {reply.forward_from_chat.title}, has an id of `{reply.forward_from_chat.id}`\n\n"

    if reply and reply.sender_chat:
        text += f"ID of the replied chat/channel, is `{reply.sender_chat.id}`"

    if reply and message.reply_to_message.new_chat_members:
        for x in message.reply_to_message.new_chat_members:
            meow = x.id
        text += f"Added user has an ID of `{meow}`"

    if reply and reply.sticker:
        text += f"\n\n**Sticker ID**: `{reply.sticker.file_id}`"

    if reply and reply.animation:
        text += f"\n**GIF ID**: `{reply.animation.file_id}`"

    await message.reply_text(text, disable_web_page_preview=True)
