from pyrogram import Client

from Emilia import custom_filter, db
from Emilia.helper.chat_status import CheckAllAdminsStuffs
from Emilia.helper.custom_emoji import (
    emojipack_token,
    extract_emojipack_tokens_from_command_target,
    is_emojipack_token,
    normalize_emojipack_name,
)
from Emilia.helper.get_data import get_text_reason
from Emilia.modules.plugins.connection.connection import connection
from Emilia.mongo.blocklists_mongo import add_blocklist_db
from Emilia.utils.decorators import *

blocklist = db.blocklists


@usage('/addblacklist ["trigger" reason]')
@example('/addblacklist "the admins suck" Respect your admins!')
@description(
    "Use this command to add some trigger as a blacklist in your chat along with reason."
)
@Client.on_message(custom_filter.command(commands=["addblocklist", "addblacklist"]))
@anonadmin_checker
async def add_blocklist(client, message):
    if await connection(message) is not None:
        chat_id = await connection(message)
    else:
        chat_id = message.chat.id

    if not await CheckAllAdminsStuffs(
        message, privileges="can_restrict_members", chat_id=chat_id
    ):
        return

    command = message.text.split(" ")
    if len(command) == 1:
        await usage_string(message, add_blocklist)
        return

    count = await blocklist.count_documents({"chat_id": chat_id})
    if count > 69:
        await message.reply("You can't have more than 69 blocklist filters in a chat!")
        return

    text, reason = await get_text_reason(message)
    if is_emojipack_token(text):
        normalized = normalize_emojipack_name(text)
        tokens = set()
        if not normalized:
            tokens = await extract_emojipack_tokens_from_command_target(client, message)
            if not tokens:
                await message.reply(
                    "Reply to a message containing custom emoji to blocklist its emoji pack.",
                    )
                return
        else:
            token = emojipack_token(normalized)
            if token:
                tokens.add(token)

        for token in tokens:
            await add_blocklist_db(chat_id, token, reason)
        await message.reply(
            "I have added custom emoji pack blocklist filter{}: {}.".format(
                "s" if len(tokens) != 1 else "",
                ", ".join(f"`{token}`" for token in sorted(tokens)),
            ),
            )
        return

    await add_blocklist_db(chat_id, text, reason)
    await message.reply(f"I have added blocklist filter '`{text}`'!")
