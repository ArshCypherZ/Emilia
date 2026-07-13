import html

from pyrogram import Client
from pyrogram.enums import ChatType

from Emilia import BOT_ID, custom_filter
from Emilia.helper.chat_status import isUserCreator
from Emilia.helper.forward_origin import fwd_chat
from Emilia.helper.get_data import GetChat
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.log_channels_mongo import set_log_db
from Emilia.utils.decorators import anonadmin_checker


@Client.on_message(custom_filter.command(commands=("setlog")))
@anonadmin_checker(owner_only=True)
async def set_log(client, message):

    if message.chat.type == ChatType.CHANNEL:
        await message.reply(
            "Now, forward the previous message (your /setlog command) to the chat you wish to log here."
        )
        return

    if await connection(message) is not None:
        chat_id = await connection(message)
        chat_title = await GetChat(chat_id, client)
    else:
        chat_id = message.chat.id
        chat_title = message.chat.title

    if message.chat.type == ChatType.PRIVATE:
        await message.reply(
            "This command can only be used in groups and channels, not in PMs.",
            )
        return

    if not await isUserCreator(message, chat_id=chat_id):
        await message.reply("Only the group owner can set the log channel.")
        return

    fwd_chat_ = fwd_chat(message)
    if not (fwd_chat_ and fwd_chat_.type == ChatType.CHANNEL):
        await message.reply(
            "You need to forward the /setlog message from a channel to set that channel as this chat's log channel. More info in /help.",
            )
        return

    try:
        GetChannelData = await client.get_chat_member(
            chat_id=fwd_chat_.id, user_id=BOT_ID
        )

    except BaseException:
        await message.reply(
            "I'm not in the channel, make me an admin there and then repeat the command.",
            )
        return

    if GetChannelData:
        if (GetChannelData.privileges).can_post_messages:
            channel_id = fwd_chat_.id
            channel_title = fwd_chat_.title
            await set_log_db(chat_id, channel_id, channel_title)
            await message.reply(
                f"Successfully set log channel to {html.escape(channel_title)}. Further admin actions will be logged there.",
                )

            await client.send_message(
                chat_id=channel_id,
                text=(
                    f"This channel has been set as the log channel for {html.escape(chat_title)}. All new admin actions will be logged here."
                ),
            )

        else:
            await message.reply(
                "I don't have rights to `can_post_messages` in the channel, make sure I have admin rights.",
                )
