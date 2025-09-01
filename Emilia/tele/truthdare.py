from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.utils.async_http import get


async def fetch_question(url):
    r = await get(url)
    try:
        data = r.json()
    except Exception:
        return None
    return data.get("question")


async def get_dare_question():
    return await fetch_question("https://api.truthordarebot.xyz/v1/dare")


async def get_truth_question():
    return await fetch_question("https://api.truthordarebot.xyz/v1/truth")


@register(pattern="dare", disable=True)
@disable
async def dare(event):
    dare = await get_dare_question()
    if dare:
        await event.reply(f"{dare}")


@register(pattern="truth", disable=True)
@disable
async def truth(event):
    truth = await get_truth_question()
    if truth:
        await event.reply(f"{truth}")
