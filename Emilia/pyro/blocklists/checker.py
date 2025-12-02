import time
from asyncio import sleep

from pyrogram.types import ChatPermissions


from Emilia.mongo.blocklists_mongo import (
    get_blocklist_reason,
    getblocklistMessageDelete,
    getblocklistmode,
)
from Emilia.pyro.warnings.warn import warn
from Emilia.utils.decorators import logging


@logging
async def blocklist_action(client, message, blocklist_word):
    chat_id = message.chat.id
    user_id = message.from_user.id

    reason = await get_blocklist_reason(chat_id, blocklist_word)

    blocklist_mode, blocklist_time, dreason = await getblocklistmode(chat_id)
    if reason is None:
        if dreason is None:
            reason = f"Automated blocklist action, due to a match on: {blocklist_word}"
        else:
            reason = dreason

    if blocklist_mode == 1:
        if await getblocklistMessageDelete(chat_id):
            await message.delete()
        return

    elif blocklist_mode == 2:
        await client.ban_chat_member(chat_id, user_id)
        await message.reply(
            (f"User {message.from_user.mention} was banned.\n" f"**Reason:**\n{reason}")
        )

        if await getblocklistMessageDelete(chat_id):
            await message.delete()

        return "BLOCKLIST_BAN", user_id, message.from_user.first_name

    elif blocklist_mode == 3:
        await client.restrict_chat_member(
            chat_id, user_id, ChatPermissions(can_send_messages=False)
        )
        await message.reply(
            (
                f"User {message.from_user.mention} is muted now.\n"
                f"**Reason:**\n{reason}"
            )
        )

        if await getblocklistMessageDelete(chat_id):
            await message.delete()

        return "BLOCKLIST_MUTE", user_id, message.from_user.first_name

    elif blocklist_mode == 4:
        await client.ban_chat_member(
            chat_id,
            user_id,
            # wait 60 seconds in case of server goes down at unbanning time
            int(time.time()) + 60,
        )
        await message.reply(
            (
                f"User {message.from_user.mention} has been kicked.\n"
                f"**Reason:**\n{reason}"
            )
        )

        if await getblocklistMessageDelete(chat_id):
            await message.delete()

        # Unbanning proceess and wait 5 sec to give server to kick user first
        await sleep(5)
        await client.unban_chat_member(chat_id, user_id)
        return "BLOCKLIST_KICK", user_id, message.from_user.first_name

    elif blocklist_mode == 5:
        await warn(client, message, reason, warn_user=message)

        if await getblocklistMessageDelete(chat_id):
            await message.delete()

    elif blocklist_mode == 6:
        until_time = int(time.time() + int(blocklist_time))
        await client.ban_chat_member(
            chat_id=chat_id, user_id=user_id, until_date=until_time
        )
        await message.reply(
            (
                f"User {message.from_user.mention} was temporarily banned.\n"
                f"**Reason:**\n{reason}"
            )
        )

        if await getblocklistMessageDelete(chat_id):
            await message.delete()
        return "BLOCKLIST_TEMPBAN", user_id, message.from_user.first_name

    elif blocklist_mode == 7:
        until_time = int(time.time() + int(blocklist_time))
        await client.restrict_chat_member(
            chat_id,
            user_id,
            ChatPermissions(can_send_messages=False),
            until_date=until_time,
        )
        await message.reply(
            (
                f"User {message.from_user.mention} was temporarily muted.\n"
                f"**Reason:**\n{reason}"
            )
        )

        if await getblocklistMessageDelete(chat_id):
            await message.delete()
        return "BLOCKLIST_TEMPMUTE", user_id, message.from_user.first_name
