from Emilia.utils.async_http import get
from telethon import Button, errors

from Emilia.custom_filter import register
from Emilia.helper.disable import disable


async def get_ud_definition(text):
    url = "https://api.urbandictionary.com/v0/define"
    response = await get(url, params={"term": text})
    if response.status_code == 200:
        data = response.json()
        if "list" in data and data["list"]:
            return data["list"][0]
    return None


@register(pattern="ud", disable=True)
@disable
async def ud_command(event):
    words = event.text.split(" ")

    if len(words) != 2:
        await event.reply("Please provide only one word.")
        return

    text = words[1]
    result = await get_ud_definition(text)

    if result:
        definition = result["definition"]
        example = result["example"]

        reply_text = (
            (f"**{text}**\n\n{definition}\n\n__{example}__")
            .replace("[", "")
            .replace("]", "")
        )
    else:
        reply_text = "No results found."

    search_url = f"https://www.google.com/search?q={text}"
    buttons = [Button.url("🔎 Google it!", search_url)]

    try:
        await event.reply(reply_text, buttons=buttons, parse_mode="md")
    except errors.ChatWriteForbiddenError:
        await event.reply(reply_text, parse_mode="md")


@register(pattern="define", disable=True)
@disable
async def define_command(event):
    user_input = event.text.split(None, 1)[1]

    if not user_input:
        return await event.reply("Please provide a word to define!")

    url = "https://api.dictionaryapi.dev/api/v2/entries/en/{}".format(user_input)
    response = await get(url)

    try:
        data = response.json()[0]
        meanings = data.get("meanings")
        if meanings:
            definition = meanings[0].get("definitions")[0].get("definition")
            if definition:
                await event.reply(
                    "**{}**:\n\n{}".format(user_input.capitalize(), definition)
                )
                return

    except (TypeError, IndexError, KeyError):
        pass

    await event.reply("__No results found.__")
