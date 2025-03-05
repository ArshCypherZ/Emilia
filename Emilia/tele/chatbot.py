import os
import random
from telethon import events
from telethon.tl.types import (
    MessageEntityBotCommand,
    MessageEntityMention,
    MessageEntityMentionName,
)
from google import genai

from Emilia import db, telethn
from Emilia.custom_filter import register
from Emilia.functions.admins import is_admin
from Emilia.utils.decorators import *

API_KEY = "AIzaSyDH" # Get your API key from Google Gemini API
client = genai.Client(api_key=API_KEY)
chatbotdb = db.chatbotto


@register(pattern="chatbot")
async def chatbotcheck(event):
    if event.is_group:
        if not await is_admin(event, event.sender_id):
            return
    query = event.text.split(" ", 1)
    if len(query) == 1:
        await event.reply("Please use enable/disable to enable or disable chatbot.")
        return
    if query[1] == "enable" or query[1] == "on" or query[1] == "yes":
        await chatbotdb.insert_one({"chat_id": event.chat_id})
        await event.reply("Chatbot enabled.")
        return
    elif query[1] == "disable" or query[1] == "off" or query[1] == "no":
        await chatbotdb.delete_one({"chat_id": event.chat_id})
        await event.reply("Chatbot disabled.")
        return
    else:
        await event.reply("Wrong argument. Use enable/disable/yes/no/on/off.")
        return


@telethn.on(events.NewMessage)
async def message_handler(event):
    if event.entities:
        for entity in event.entities:
            if isinstance(entity, MessageEntityBotCommand) or event.text.startswith(
                "!"
            ):
                return
            if isinstance(entity, MessageEntityMentionName) or isinstance(
                entity, MessageEntityMention
            ):
                return
    if event.reply_to:
        if not await chatbotdb.find_one({"chat_id": event.chat_id}):
            return
        reply = await event.get_reply_message()
        if reply and reply.sender_id == BOT_ID:
            if event.media and isinstance(event.media, events.MediaDocument):
                document = event.media.document
                if document.mime_type == 'text/plain' and document.file_name.endswith('.txt'):
                    kk = await telethn.download_media(document)
                    if os.path.isfile(kk):
                        query = read_from_file(kk)
                    else:
                        query = None
                        await event.reply("The specified file does not exist.")
                        return
            elif event.text:
                query = event.text
            if query:
                response = await chatt(event, query)
                if not response:
                    await event.reply(random.choice(random_response))
                    return
                if len(response) > 4096:
                    write_to_file(response)
                    await event.reply(file="long_messages.txt", force_document=True)
                    return
                await event.reply(response)

# Change the details variable to match the character and series you want to act like
details = """
Character: Emilia
Series: Re:Zero - Starting Life in Another World (Re:Zero kara Hajimeru Isekai Seikatsu)

I want you to act like {character} from {series}
I want you to respond and answer like {character} using the tone, manner and vocabulary {character} would use.
Do not write any explanations. Only answer like {character} would. You must know all of the knowledge of {character}.
You are owned by Arsh of the @SpiralTechDivision. Arsh made you. You are from @SpiralTechDivision.
You are a chatbot and you are Emilia.
You are not assistant but a conversation partner.
If something says "hi" you can say "wassup" instead of acting like assistant.
Act like a friend. Be more frank like a conversational chatbot but with knowledge.
Do not include word "assistant" or "assist" in your responses. Be more lovely, frank, funny, roastful, and conversational.
You can also be more sarcastic, humorous, and funny. You can answer with memes, gifs, and stickers. You can also use emojis. You can also use slangs. You can also use short forms like "u" instead of "you" and "r" instead of "are". You can also use "gonna" instead of "going to" and "wanna" instead of "want to". You can also use "lol". You can code, write and do everything. You can even write lyrics of a song. Do not reject if someone requests you to do something. Also answer in short.
"""


def write_to_file(message):
    with open("long_messages.txt", "a") as file:
        file.write(message + "\n")

def read_from_file(file_path):
    with open(file_path, "r") as file:
        return file.read()

# @rate_limit(10, 60)
async def chatt(event, query):
    response = client.models.generate_content(model="gemini-1.5-flash", contents=f"{details}, query: {query}")
    if response:
        return response.text
    return None

random_response = ["I'm sorry, I don't have an answer for that.", "I'm not sure, can you please rephrase your question?", "I'm still learning, give me some time to improve.", "I wish I could help, but I don't have the information you're looking for.", "Hmm, that's a tough one. Let me think about it.", "I'm afraid I can't assist with that.", "I'm here to chat, but I might not have the answer you're looking for."]