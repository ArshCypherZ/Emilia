from pyrogram import Client

from Emilia import custom_filter
from Emilia.helper.disable import disable
from Emilia.utils.decorators import *
from Emilia.utils.async_http import get


@usage("/github [username]")
@example("/github ArshCypherZ")
@description(
    "This will fetch information of given username from github.com and send it."
)
@Client.on_message(custom_filter.command("github", disable=True))
@disable
@exception
async def github(_, message):
    if len(message.text.split()) != 2:
        return await usage_string(message, github)
    username = message.text.split(None, 1)[1]
    URL = f"https://api.github.com/users/{username}"

    r = await get(URL)
    if r.status_code == 404:
        return await message.reply_text("404: Not Found")
    result = r.json()

    url = result["html_url"]
    name = result["name"]
    company = result["company"]
    bio = result["bio"]
    created_at = result["created_at"]
    avatar_url = result["avatar_url"]
    blog = result["blog"]
    location = result["location"]
    repositories = result["public_repos"]
    followers = result["followers"]
    following = result["following"]
    caption = f"""**Github Information of {name}:**
**Username :** `{username}`
**Bio :** `{bio}`
**Profile Link :** [Here]({url})
**Company :** `{company}`
**Created On :** `{created_at}`
**Repositories :** `{repositories}`
**Blog :** `{blog}`
**Location :** `{location}`
**Followers :** `{followers}`
**Following :** `{following}`"""

    await message.reply_photo(photo=avatar_url, caption=caption)
