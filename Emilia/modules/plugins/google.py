import re
import urllib.parse

from bs4 import BeautifulSoup
from pyrogram import Client
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
)

from Emilia import custom_filter
from Emilia.helper.disable import disable
from Emilia.utils.async_http import get
from Emilia.utils.decorators import *


async def fetch_duckduckgo(query: str, num_results: int = 10) -> list:
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"

    response = await get(url)
    if response.status_code != 200:
        raise Exception(
            f"Search engine responded with HTTP error {response.status_code}"
        )

    text = response.text
    soup = BeautifulSoup(text, "html.parser")
    results = []
    for result in soup.find_all("div", class_="result"):
        if len(results) >= num_results:
            break

        title_elem = result.find("h2", class_="result__title")
        if not title_elem:
            continue

        a_tag = title_elem.find("a")
        if not a_tag:
            continue

        title = a_tag.text.strip()
        raw_href = a_tag["href"]

        match = re.search(r"uddg=([^&]+)", raw_href)
        if match:
            real_url = urllib.parse.unquote(match.group(1))
            results.append({"title": title, "url": real_url})
    return results


@usage("/google [query]")
@example("/google python programming")
@description("Fetches the top search results avoiding rate limits.")
@Client.on_message(custom_filter.command(["google", "g"], disable=True))
@disable
@exception
async def google_search_cmd(client: Client, message):
    if len(message.command) < 2:
        return await usage_string(message, google_search_cmd)

    query = message.text.split(None, 1)[1]
    wait_msg = await message.reply_text("Searching...")

    try:
        results = await fetch_duckduckgo(query, num_results=10)

        if not results:
            return await wait_msg.edit_text("No results found. Try a different query.")

        response_text = f"**Search Results for** `{query}`\n\n"

        for idx, res in enumerate(results, start=1):
            title = res["title"]
            url = res["url"]
            response_text += f"{idx}. [{title}]({url})\n"

        encoded_query = urllib.parse.quote_plus(query)
        google_url = f"https://www.google.com/search?q={encoded_query}"

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Google 🔍", url=google_url)]]
        )

        await wait_msg.edit_text(
            response_text,
            reply_markup=keyboard,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    except Exception as e:
        await wait_msg.edit_text(f"An error occurred: `{str(e)}`")
