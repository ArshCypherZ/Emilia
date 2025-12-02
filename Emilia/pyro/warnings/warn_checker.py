import asyncio
import time

from pyrogram.types import ChatPermissions


from Emilia.mongo.warnings_mongo import (
    count_user_warn,
    get_all_warn_reason,
    get_warn_mode,
    reset_user_warns,
    warn_limit,
)


async def warn_checker(client, message, user_id, silent=False):
    chat_id = message.chat.id
    log_msg = ""

    countuser_warn = await count_user_warn(chat_id, user_id)
    warnlimit = await warn_limit(chat_id)

    if countuser_warn >= warnlimit:
        warn_mode, warn_mode_time = await get_warn_mode(chat_id)

        if warn_mode == 1:
            await client.ban_chat_member(chat_id, user_id)

            if not silent:
                user_info = await client.get_users(user_ids=user_id)
                REASONS = await get_all_warn_reason(chat_id, user_id)

                text = f"That's {countuser_warn}/{warnlimit} warnings; {user_info.mention} is banned!\n"
                for reason in REASONS:
                    text += reason
                await message.reply(text)
                await reset_user_warns(chat_id, user_id)
                log_msg = "WARN_BAN"
            return True, log_msg

        elif warn_mode == 2:
            await client.ban_chat_member(
                chat_id,
                user_id,
                # wait 60 seconds in case of server goes down at unbanning time
                int(time.time()) + 60,
            )
            await client.unban_chat_member(chat_id, user_id)

            if not silent:
                user_info = await client.get_users(user_ids=user_id)
                REASONS = await get_all_warn_reason(chat_id, user_id)

                text = f"That's {countuser_warn}/{warnlimit} warnings; {user_info.mention} is kicked!\n"
                for reason in REASONS:
                    text += reason
                await message.reply(text)
                await reset_user_warns(chat_id, user_id)
                log_msg = "WARN_KICK"

            # Unbanning proceess and wait 5 sec to give server to kick user
            # first
            await asyncio.sleep(5)
            await client.unban_chat_member(chat_id, user_id)

            return True, log_msg

        elif warn_mode == 3:
            await client.restrict_chat_member(
                chat_id, user_id, ChatPermissions(can_send_messages=False)
            )

            if not silent:
                user_info = await client.get_users(user_ids=user_id)
                REASONS = await get_all_warn_reason(chat_id, user_id)

                text = f"That's {countuser_warn}/{warnlimit} warnings; {user_info.mention} is muted!\n"
                for reason in REASONS:
                    text += reason
                await message.reply(text)
                await reset_user_warns(chat_id, user_id)
                log_msg = "WARN_MUTE"
            return True, log_msg

        elif warn_mode == 4:
            until_time = int(time.time() + int(warn_mode_time))
            await client.restrict_chat_member(chat_id, user_id, until_date=until_time)

            if not silent:
                user_info = await client.get_users(user_ids=user_id)
                REASONS = await get_all_warn_reason(chat_id, user_id)

                text = f"That's {countuser_warn}/{warnlimit} warnings; {user_info.mention} is temporarily banned!\n"
                for reason in REASONS:
                    text += reason
                await message.reply(text)
                await reset_user_warns(chat_id, user_id)
                log_msg = "WARN_TEMP_BAN"
            return True, log_msg

        elif warn_mode == 5:
            until_time = int(time.time() + int(warn_mode_time))
            await client.restrict_chat_member(
                chat_id,
                user_id,
                ChatPermissions(can_send_messages=False),
                until_date=until_time,
            )

            if not silent:
                user_info = await client.get_users(user_ids=user_id)
                REASONS = await get_all_warn_reason(chat_id, user_id)

                text = f"That's {countuser_warn}/{warnlimit} warnings; {user_info.mention} is temporarily muted!\n"
                for reason in REASONS:
                    text += reason
                await message.reply(text)
                await reset_user_warns(chat_id, user_id)
                log_msg = "WARN_TEMP_MUTE"
            return True, log_msg
    else:
        return False, "WARN"