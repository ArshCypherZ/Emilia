import re

from pyrogram import Client, filters

from Emilia.helper.filters_helper.send_filter_message import SendFilterMessage
from Emilia.mongo.filters_mongo import get_filter, get_filters_list


@Client.on_message(filters.all & ~filters.user(777000), group=8)
async def FilterCheckker(client, message):
    trigger_texts = _filter_trigger_texts(message)
    if not trigger_texts:
        return
    if not message.from_user:
        return
    chat_id = message.chat.id

    # If 'chat_id' has no filters then simply return
    if len((await get_filters_list(chat_id))) == 0:
        return

    ALL_FILTERS = await get_filters_list(chat_id)
    for filter_ in ALL_FILTERS:
        if (
            message.text
            and message.text.split()
            and message.text.split()[0] == "filter"
            and len(message.text.split()) >= 2
            and message.text.split()[1] == filter_
        ):
            return

        pattern = r"( |^|[^\w])" + re.escape(filter_) + r"( |$|[^\w])"
        if any(re.search(pattern, text, flags=re.IGNORECASE) for text in trigger_texts):
            filter_name, content, text, data_type, reply_to_sender = await get_filter(
                chat_id, filter_
            )
            await SendFilterMessage(
                client,
                message,
                filter_name=filter_name,
                content=content,
                text=text,
                data_type=data_type,
                reply_to_sender=reply_to_sender,
            )


def _filter_trigger_texts(message):
    texts = []
    if message.text:
        texts.append(message.text)
    if message.caption:
        texts.append(message.caption)
    if message.dice:
        dice_emoji = getattr(message.dice, "emoji", None)
        dice_value = getattr(message.dice, "value", None)
        if dice_emoji:
            texts.extend([dice_emoji, f"dice:{dice_emoji}"])
        if dice_value is not None:
            texts.append(f"dice:{dice_value}")
        if dice_emoji and dice_value is not None:
            texts.append(f"{dice_emoji}:{dice_value}")
    return texts
