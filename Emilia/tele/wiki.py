# DONE: Wikipedia

import wikipedia
from wikipedia.exceptions import DisambiguationError, PageError

from Emilia import telethn as meow, LOGGER
from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.utils.decorators import *


class AsyncWikipedia:
    def __init__(self, title):
        self.title = title

    def summary(self):
        try:
            page = wikipedia.page(self.title)
            return page.summary
        except DisambiguationError as e:
            raise e
        except PageError as e:
            raise e


async def get_wikipedia_summary(search):
    wiki = AsyncWikipedia(search)
    summary = wiki.summary()
    return summary


@register(pattern="wiki", disable=True)
@disable
@rate_limit(RATE_LIMIT_HEAVY)
async def wiki(event):
    if event.is_reply:
        search_query = (await event.get_reply_message()).text.strip()
    else:
        input_args = event.text.split(None, 1)
        if len(input_args) < 2:
            await event.reply("Provide some query to search!")
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
        with open("result.txt", "w") as f:
            f.write(f"{result}\n\nUwU OwO OmO UmU")
        with open("result.txt", "rb") as f:
            await meow.send_file(
                event.chat_id,
                file=f,
                file_name=f.name,
                parse_mode="html",
                force_document=True,
            )
    else:
        await event.reply(result, parse_mode="html", link_preview=False)