from pyrogram import Client, enums, filters

from Emilia.helper.chat_status import isBotCan
from Emilia.helper.forward_origin import fwd_chat
from Emilia.mongo.pin_mongo import get_cleanlinked


@Client.on_message(filters.all & filters.group, group=6)
async def cleanlinkedChecker(client, message):
    chat_id = message.chat.id
    if not (await get_cleanlinked(chat_id)):
        return

    channel_id = await GetLinkedChannel(client, chat_id)
    if channel_id is not None:
        fwd_chat_ = fwd_chat(message)
        if (
            fwd_chat_
            and fwd_chat_.type == enums.ChatType.CHANNEL
            and fwd_chat_.id == channel_id
        ):
            if await isBotCan(message, privileges="can_delete_messages", silent=True):
                await message.delete()
            else:
                await message.reply(
                    "I don't have the right to delete messages in the linked channel.\nError: `not_enough_permissions`"
                )


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
