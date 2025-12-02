from pyrogram import Client, enums, filters


from Emilia.helper.chat_status import isBotCan
from Emilia.mongo.pin_mongo import get_antichannelpin


@Client.on_message(filters.all & filters.group, group=7)
async def cleanlinkedChecker(client, message):
    chat_id = message.chat.id
    message_id = message.id
    if not (await get_antichannelpin(chat_id)):
        return

    channel_id = await GetLinkedChannel(client, chat_id)
    if channel_id is not None:
        if (
            message.forward_from_chat
            and message.forward_from_chat.type == enums.ChatType.CHANNEL
            and message.forward_from_chat.id == channel_id
        ):
            if not await isBotCan(message, privileges="can_pin_messages", silent=True):
                return await message.reply(
                    "I don't have the right to pin or unpin messages in this chat.\nError: `could_not_unpin`"
                )

            await client.unpin_chat_message(chat_id=chat_id, message_id=message_id)


async def GetLinkedChannel(client, chat_id: int) -> str:
    chat_data = await client.get_chat(chat_id=chat_id)
    if chat_data.linked_chat:
        return chat_data.linked_chat.id
    else:
        return None
