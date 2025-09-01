import html

from pyrogram import Client, enums
from urlextract import URLExtract

import Emilia.strings as strings
from Emilia import custom_filter
from Emilia.helper.chat_status import check_user
from Emilia.helper.get_data import GetChat
from Emilia.mongo.locks_mongo import allowlist_db, get_allowlist
from Emilia.pyro.connection.connection import connection


@Client.on_message(custom_filter.command(commands="allowlist"))
async def allowlist(client, message):
    conn_chat_id = await connection(message)
    if conn_chat_id is not None:
        chat_id = conn_chat_id
        chat_title = await GetChat(chat_id)
    else:
        chat_id = message.chat.id
        chat_title = message.chat.title

    if (
        not str(chat_id).startswith("-100")
        and message.chat.type == enums.ChatType.PRIVATE
    ):
        return await message.reply(strings.is_pvt)

    if not await check_user(message, privileges="can_change_info"):
        return

    if len(message.text.split()) >= 2:
        ARG_LIST = message.text.split()[1:]
        INCORRECT_ITEMS = []
        CORRECT_ITEMS = []
        for arg in ARG_LIST:
            extractor = URLExtract()
            URLs_list = extractor.find_urls(arg)
            if arg.startswith("-100"):
                CORRECT_ITEMS.append(int(arg))

            elif arg.startswith("@"):
                CORRECT_ITEMS.append(arg)

            elif len(URLs_list) != 0:
                for url in URLs_list:
                    if url.startswith("https://"):
                        url = url.replace("https://", "")
                    elif url.startswith("http://"):
                        url = url.replace("http://", "")
                    elif url.startswith("www."):
                        url = url.replace("www.", "")
                    elif url.startswith("https://www."):
                        url = url.replace("https://www.", "")
                    elif url.startswith("http://www."):
                        url = url.replace("http://www.", "")
                CORRECT_ITEMS.append(url)

            else:
                INCORRECT_ITEMS.append(arg)

        if len(INCORRECT_ITEMS) != 0:
            text = "I have rejected these args to be added in the `allowlist` due to wrong format of the provided data.\n"
            for item in INCORRECT_ITEMS:
                text += f"• {item}\n"

            return await message.reply(text)

        for item in CORRECT_ITEMS:
            await allowlist_db(chat_id, item)

        text = "These are added to the allowlist.\n"
        for item in CORRECT_ITEMS:
            if len(CORRECT_ITEMS) == 1:
                text = f"'{item}' added to the allowlist."
            else:
                text += f"• {item}\n"

        await message.reply(text)

    else:
        ALLOW_LIST = await get_allowlist(chat_id)
        if len(ALLOW_LIST) != 0:
            text = f"The following items are allowlisted in {html.escape(chat_title)}\n"
            for item in ALLOW_LIST:
                text += f"• {item}\n"

            await message.reply(text)
        else:
            await message.reply(
                f"There are no allowlisted items in {html.escape(chat_title)}!"
            )
