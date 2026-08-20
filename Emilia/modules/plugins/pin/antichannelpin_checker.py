from pyrogram import Client, enums, filters

from Emilia.helper.chat_status import isBotCan
from Emilia.helper.forward_origin import fwd_chat
from Emilia.mongo.pin_mongo import get_antichannelpin


@Client.on_message(filters.all & filters.group, group=7)
async def cleanlinkedChecker(client, message):
    chat_id = message.chat.id
    message_id = message.id
    if not (await get_antichannelpin(chat_id)):
        return

    channel_id = await GetLinkedChannel(client, chat_id)
    if channel_id is not None:
        fwd_chat_ = fwd_chat(message)
        if (
            fwd_chat_
            and fwd_chat_.type == enums.ChatType.CHANNEL
            and fwd_chat_.id == channel_id
        ):
            if not await isBotCan(message, privileges="can_pin_messages", silent=True):
                return await message.reply(
                    "I don't have the right to pin or unpin messages in this chat.\nError: `could_not_unpin`"
                )

            await client.unpin_chat_message(chat_id=chat_id, message_id=message_id)


from Emilia.utils.cache import linked_chat_cache

async def GetLinkedChannel(client, chat_id: int) -> str:
    cache_key = f"{chat_id}"
    cached = await linked_chat_cache.get(cache_key)
    if cached is not None:
        return cached if cached != "None" else None

    chat_data = await client.get_chat(chat_id=chat_id)
    linked_id = chat_data.linked_chat.id if chat_data.linked_chat else "None"
    await linked_chat_cache.set(cache_key, linked_id)
    return chat_data.linked_chat.id if chat_data.linked_chat else None
