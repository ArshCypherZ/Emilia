from pyrogram import Client

from Emilia import custom_filter, db
from Emilia.helper.chat_status import isUserAdmin
from Emilia.helper.filters_helper.get_filters_message import GetFIlterMessage
from Emilia.helper.get_data import get_text_reason
from Emilia.mongo.filters_mongo import add_filter_db
from Emilia.pyro.connection.connection import connection
from Emilia.utils.decorators import *

filters = db.filters

@usage("/filter [trigger/reply to content] or [trigger content]")
@example("/filter meow nya")
@description("Bot will reply with content when someone mentions 'trigger' in a chat")
@Client.on_message(custom_filter.command(commands="filter"))
async def filter(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if not await isUserAdmin(message):
        return

    if message.reply_to_message and len(message.text.split()) < 2:
        await usage_string(message, filter)
        return
    

    count = await filters.count_documents({"chat_id": chat_id})
    if count > 69:
        await message.reply("You can't have more than 69 filters in a chat!")
        return

    try:
        filter_name, filter_reason = await get_text_reason(message)
    except IndexError:
        await usage_string(message, filter)
        return

    command = message.text.split(" ")
    if len(command) == 2 and not message.reply_to_message:
        await usage_string(message, filter)
        return

    await message.reply(f"Saved filter '`{filter_name}`'")
    content, text, data_type = await GetFIlterMessage(message)
    reply_to_sender = "{replytag}" in text
    if reply_to_sender:
        text = text.replace("{replytag}", "")
    await add_filter_db(
        chat_id,
        filter_name=filter_name,
        content=content,
        text=text,
        data_type=data_type,
        reply_to_sender=reply_to_sender,
    )
