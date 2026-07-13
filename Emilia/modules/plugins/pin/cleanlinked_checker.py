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


async def GetLinkedChannel(client, chat_id: int) -> str:
    chat_data = await client.get_chat(chat_id=chat_id)
    if chat_data.linked_chat:
        return chat_data.linked_chat.id
    else:
        return None
