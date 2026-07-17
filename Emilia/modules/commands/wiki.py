# DONE: Wikipedia

import asyncio

import wikipedia
from pyrogram.enums import ParseMode
from wikipedia.exceptions import DisambiguationError, PageError

from Emilia import LOGGER
from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.utils.decorators import *
from pyrogram.types import LinkPreviewOptions


def _wikipedia_summary_sync(search):
    return wikipedia.page(search).summary


async def get_wikipedia_summary(search):
    # wikipedia lib is fully synchronous (urllib under the hood); keep it
    # off the event loop.
    return await asyncio.to_thread(_wikipedia_summary_sync, search)


@register(pattern="wiki", disable=True)
@disable
@rate_limit(RATE_LIMIT_HEAVY)
async def wiki(client, message):
    if message.reply_to_message:
        search_query = (message.reply_to_message.text or "").strip()
    else:
        input_args = (message.text or "").split(None, 1)
        if len(input_args) < 2:
            await message.reply_text("Provide some query to search!")
            return
        search_query = input_args[1].strip()

    try:
        wikipedia.set_lang("en")
        wikipedia.set_rate_limiting(True)
        summary = await get_wikipedia_summary(search_query)
        result = f"<b>{search_query}</b>\n\n"
        result += f"<i>{summary}</i>\n"
        result += f"""<a href="https://en.wikipedia.org/wiki/{search_query.replace(" ", "%20")}">Read more...</a>"""
    except DisambiguationError as e:
        result = (
            f"Disambiguated pages found! Adjust your query accordingly.\n\n<i>{e}</i>"
        )
    except PageError as e:
        result = f"<code>{e}</code>"
    except Exception as e:
        LOGGER.error(f"Error: {e}")
        result = "An error occurred while processing your request."

    if len(result) > 4000:
        import os
        import uuid
        filename = f"wiki_{uuid.uuid4().hex}.txt"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"{result}\n\nUwU OwO OmO UmU")
            await client.send_document(
                message.chat.id,
                filename,
                file_name="wiki_result.txt",
            )
        finally:
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except Exception:
                    pass
    else:
        await message.reply_text(
            result, parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
