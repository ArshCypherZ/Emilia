import random
from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.utils.async_http import get

TRUTHS = [
    "What is your biggest fear?",
    "What is the most embarrassing thing you've ever done?",
    "Have you ever lied to your best friend?",
    "What is a secret you've never told anyone?",
    "If you could trade places with anyone for a day, who would it be?",
    "What is the strangest dream you've ever had?",
    "Have you ever had a crush on a teacher or boss?",
    "What is your worst habit?",
    "What is the most childish thing you still do?",
    "Have you ever cheated on a test or exam?"
]

DARES = [
    "Do 10 pushups right now.",
    "Send the last photo in your gallery to this chat.",
    "Send a voice note singing a song of your choice.",
    "Text a friend 'I love you' and send a screenshot of their reaction.",
    "Speak in an accent of the group's choice for the next 10 minutes.",
    "Tell the group a joke that makes them laugh.",
    "Type a message using only your nose.",
    "Show the last 3 search items on your search history.",
    "Send a funny selfie to this group.",
    "Make up a short story about the first person to talk after you."
]


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
async def dare(client, event):
    dare = await get_dare_question()
    if not dare:
        dare = random.choice(DARES)
    await event.reply(f"{dare}")


@register(pattern="truth", disable=True)
@disable
async def truth(client, event):
    truth = await get_truth_question()
    if not truth:
        truth = random.choice(TRUTHS)
    await event.reply(f"{truth}")

