import re
from asyncio import sleep

from pyrogram import Client, filters, errors

from Emilia.helper.filters_helper.send_filter_message import SendFilterMessage
from Emilia.mongo.filters_mongo import get_filter, get_filters_list


@Client.on_message(filters.all & ~filters.user(777000), group=8)
async def FilterCheckker(client, message):
    if not message.text:
        return
    if not message.from_user:
        return
    text = message.text
    chat_id = message.chat.id

    # If 'chat_id' has no filters then simply return
    if len((await get_filters_list(chat_id))) == 0:
        return

    ALL_FILTERS = await get_filters_list(chat_id)
    for filter_ in ALL_FILTERS:
        if (
            message.text.split()
            and message.text.split()[0] == "filter"
            and len(message.text.split()) >= 2
            and message.text.split()[1] == filter_
        ):
            return

        pattern = r"( |^|[^\w])" + re.escape(filter_) + r"( |$|[^\w])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            filter_name, content, text, data_type, reply_to_sender = await get_filter(chat_id, filter_)
            await SendFilterMessage(
                client,
                message,
                filter_name=filter_name,
                content=content,
                text=text,
                data_type=data_type,
                reply_to_sender=reply_to_sender,
            )
