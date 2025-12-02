from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto

from Emilia import LOGGER
from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.utils.decorators import *
from Emilia.catbox import upload
from Emilia.utils.async_http import get

SAUCENAO_API_KEY = '605d2f8a78158eab2602bf53e616f9885e41605d'
SAUCENAO_API_URL = 'https://saucenao.com/search.php'

async def search_image(image_url):
    """Search for an image on SauceNAO."""
    params = {
        'api_key': "605d2f8a78158eab2602bf53e616f9885e41605d",
        'url': image_url,
        'output_type': 2,  # JSON output
    }
    response = await get(SAUCENAO_API_URL, params=params)
    response.raise_for_status()
    return response.json()

def get_top_result(results):
    """Get the top result from SauceNAO search results."""
    if not results:
        return None
    top_result = results[0]
    
    return {
        'index': top_result['index'],
        'header': top_result['header'],
        'similarity': top_result['similarity'],
        'thumbnail': top_result['thumbnail'],
        'url': top_result['data']['ext_urls'][0],
    }

@register(pattern="findanime", disable=True)
@disable
@exception
@rate_limit(RATE_LIMIT_HEAVY)
async def saucenao_search(event):
    """Search for an image on SauceNAO."""
    reply = await event.get_reply_message()
    if not reply:
        return await event.reply("Please reply to a message.")
    if not isinstance(reply.media, (MessageMediaPhoto, MessageMediaDocument)):
        return await event.reply("Please reply to an image or a document.")
    if (
        isinstance(reply.media, MessageMediaDocument)
        and reply.media.document.mime_type.split("/")[0] != "image"
    ):
        return await event.reply("Please reply to an image, not a file.")
    url2 = await upload(reply)
    wait = await event.reply("Searching for the image on SauceNAO...")
    
    results = await search_image(url2)
    top_result = get_top_result(results['results'])
    if top_result:
        await event.reply(f"Top result:\n{top_result['url']}")
    else:
        await event.reply("No results found.")
    await wait.delete()