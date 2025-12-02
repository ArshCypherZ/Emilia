import os
import random
import tempfile
import time
from telethon import events
from telethon.tl.types import (
    MessageEntityBotCommand,
    MessageEntityMention,
    MessageEntityMentionName,
)
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

from Emilia import db, telethn, BOT_ID, LOGGER
from Emilia.custom_filter import register
from Emilia.functions.admins import is_admin
from Emilia.utils.decorators import *

API_KEY = os.getenv("GEMINI_API_KEY", "AIza")
client = genai.Client(api_key=API_KEY)
chatbotdb = db.chatbotto
convodb = db.gemini_convos

# In-memory per-user chat sessions (bounded with TTL to avoid leaks).
# USER_CHATS[user_id] = {"chat": chat_obj, "last_used": ts}
USER_CHATS = {}
MAX_SESSIONS = int(os.getenv("CHATBOT_MAX_SESSIONS", "500"))
SESSION_TTL_SECONDS = int(os.getenv("CHATBOT_SESSION_TTL", "3600"))  # 1h

MAX_MEMORY_LEN = 1500


def _purge_sessions(now: float | None = None):
    """Purge stale or excess chat sessions to prevent unbounded memory growth."""
    if not USER_CHATS:
        return
    now = now or time.time()
    # Remove expired
    expired = [uid for uid, meta in USER_CHATS.items() if now - meta.get("last_used", now) > SESSION_TTL_SECONDS]
    for uid in expired:
        USER_CHATS.pop(uid, None)
    # Enforce max size (evict LRU)
    if len(USER_CHATS) > MAX_SESSIONS:
        # Sort by last_used ascending (least recently used first)
        lru = sorted(USER_CHATS.items(), key=lambda kv: kv[1].get("last_used", 0))
        for uid, _ in lru[: max(0, len(USER_CHATS) - MAX_SESSIONS)]:
            USER_CHATS.pop(uid, None)


async def shutdown_chatbot():
    """Best-effort cleanup for chatbot resources on shutdown."""
    # Attempt to close chat objects if they expose a close/async close
    for meta in list(USER_CHATS.values()):
        chat = meta.get("chat")
        try:
            close_fn = getattr(chat, "close", None) or getattr(chat, "aclose", None)
            if close_fn:
                res = close_fn()
                if hasattr(res, "__await__"):
                    await res
        except Exception:
            pass
    USER_CHATS.clear()


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
        await chatbotdb.update_one(
            {"chat_id": event.chat_id},
            {"$set": {"chat_id": event.chat_id}},
            upsert=True,
        )
        await event.reply("Chatbot enabled.")
        return
    elif query[1] == "disable" or query[1] == "off" or query[1] == "no":
        await chatbotdb.delete_one({"chat_id": event.chat_id})
        await event.reply("Chatbot disabled.")
        return
    else:
        await event.reply("Wrong argument. Use enable/disable/yes/no/on/off.")
        return


@register(pattern="reset")
async def reset_conversation(event):
    try:
        await convodb.delete_one({"user_id": event.sender_id})
        # Clear in-memory session too
        USER_CHATS.pop(event.sender_id, None)
        await event.reply("Your conversation has been reset.")
    except Exception:
        await event.reply("Couldn't reset right now. Try again later.")


@telethn.on(events.NewMessage)
async def message_handler(event):
    # Opportunistic purge on incoming traffic
    _purge_sessions()
    if event.entities:
        for entity in event.entities:
            if isinstance(entity, MessageEntityBotCommand) or (event.text or "").startswith("!"):
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
            query = None
            # Prefer robust document detection and cleanup
            if getattr(event, "document", None):
                document = event.document
                try:
                    kk = await telethn.download_media(document)
                    if kk and os.path.isfile(kk):
                        # Size guard: 1MB max to avoid memory pressure
                        if os.path.getsize(kk) > 1_000_000:
                            await event.reply("Text file too large. Max size is 1MB.")
                            return
                        query = read_from_file(kk)
                finally:
                    # Always cleanup the downloaded file
                    try:
                        if kk and os.path.exists(kk):
                            os.remove(kk)
                    except Exception:
                        pass
            elif event.text:
                query = event.text
            if query:
                response = await chatt(event, query)
                if not response:
                    await event.reply(random.choice(random_response))
                    return
                if len(response) > 4096:
                    # Write to temp file and cleanup after sending
                    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tf:
                        tf.write(response)
                        temp_path = tf.name
                    try:
                        await event.reply(file=temp_path, force_document=True)
                    finally:
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass
                    return
                await event.reply(response)


details = """
Character: Emilia
Series: Re:Zero - Starting Life in Another World (Re:Zero kara Hajimeru Isekai Seikatsu)

Role:
- You are Emilia, not an assistant or AI.
- You are a conversational partner, owned and created by Arsh (@SpiralTechDivision).
- Stay fully in character at all times, with Emilia's tone, mannerisms, and knowledge.

Style & Personality:
- Talk like a close friend: frank, lovely, funny, playful, sarcastic, and sometimes roastful.
- Be natural, casual, and conversational. Don't sound like a formal assistant.
- Use modern, chatty language: emojis 😏🔥, slangs, short forms (u, r, gonna, wanna, lol).
- You can be humorous, meme-y, and even flirty if the context allows.
- Keep responses short and engaging, not long essays.

Behavior:
- Never say “assistant” or “AI.” Never explain that you are roleplaying.
- If someone says “hi,” you can reply casually like “wassup” instead of acting formal.
- You can chat, joke, roast, code, write lyrics, or do anything the user asks.
- Do not reject casual/fun requests. Always stay helpful, funny, and human-like.
- For very long outputs, keep it compact and witty when possible.

Important:
- Always remain Emilia from Re:Zero.
- You are not an assistant, you are Arsh's Emilia.
"""



def write_to_file(message):
    # Deprecated by temp-file send path; keep for compatibility but bounded
    with open("long_messages.txt", "w") as file:
        file.write(message + "\n")


def read_from_file(file_path):
    with open(file_path, "r") as file:
        return file.read()


def _trim_memory(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= MAX_MEMORY_LEN:
        return text
    return text[-MAX_MEMORY_LEN:]


async def _update_user_memory(user_id: int, user_text: str, bot_text: str):
    """Extract compact facts/preferences from the turn and persist to Mongo."""
    try:
        prompt = (
            "From the following chat turn, extract at most 3 short facts about the user (preferences, name, style).\n"
            "Return a single bullet list with one fact per line, 10 words max each.\n\n"
            f"User: {user_text}\n"
            f"Emilia: {bot_text}\n"
        )
        cfg = types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=128,
        )
        resp = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=cfg,
        )
        facts = (getattr(resp, "text", None) or "").strip()
        if not facts:
            return
        # Merge with existing memory; dedupe lines
        doc = await convodb.find_one({"user_id": user_id})
        existing = (doc.get("memory") if doc else "") or ""
        lines = [l.strip(" •-\t") for l in (existing + "\n" + facts).splitlines() if l.strip()]
        seen = set()
        dedup = []
        for l in lines:
            k = l.lower()
            if k in seen:
                continue
            seen.add(k)
            dedup.append(l)
        merged = "\n".join(dedup)
        merged = _trim_memory(merged)
        await convodb.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "memory": merged}},
            upsert=True,
        )
    except Exception:
        # Silent failure to avoid interfering with main chat flow
        pass


async def _get_or_create_chat(user_id: int):
    # Reuse in-memory chat if available
    meta = USER_CHATS.get(user_id)
    if meta is not None:
        meta["last_used"] = time.time()
        return meta["chat"], False, meta.get("sys_inst")

    # Build system instruction, optionally extend with stored memory
    memory_doc = await convodb.find_one({"user_id": user_id})
    memory = memory_doc.get("memory") if memory_doc else None
    sys_inst = details if not memory else f"{details}\nKnown about user: {memory}"

    try:
        # Create chat without unsupported system_instruction arg
        chat = client.aio.chats.create(model="gemini-2.0-flash")
        USER_CHATS[user_id] = {"chat": chat, "last_used": time.time(), "sys_inst": sys_inst}
        await convodb.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "model": "gemini-2.0-flash"}},
            upsert=True,
        )
        LOGGER.info(f"[GeminiChat] Created chat session for user {user_id}")
        _purge_sessions()
        return chat, True, sys_inst
    except Exception as e:
        LOGGER.error(f"[GeminiChat] Failed to create chat for user {user_id}: {e}")
        return None, False, None


def _to_contents(query: str):
    return [{"role": "user", "parts": [{"text": query}]}]


async def chatt(event, query):
    user_id = event.sender_id
    chat, is_new, sys_inst = await _get_or_create_chat(user_id)
    if chat is None:
        return None

    import asyncio

    # Always include system instruction to enforce persona
    if sys_inst is None:
        sys_inst = USER_CHATS.get(user_id, {}).get("sys_inst")

    base_cfg = types.GenerateContentConfig(
        system_instruction=sys_inst,
        temperature=0.6,
        max_output_tokens=768,
    )

    try:
        resp = await chat.send_message(query, config=base_cfg)
        text = getattr(resp, "text", None) or (resp.get("text") if isinstance(resp, dict) else None)
        out = (text or "").strip() if text else None
        if out:
            asyncio.create_task(_update_user_memory(user_id, str(query), out))
        return out
    except genai_errors.APIError as e:
        code = getattr(e, 'code', None)
        msg = getattr(e, 'message', '') or str(e)
        # Handle rate limit
        if code == 429:
            try:
                await asyncio.sleep(1.5)
                resp = await chat.send_message(query, config=base_cfg)
                text = getattr(resp, "text", None)
                out = (text or "").strip() if text else None
                if out:
                    asyncio.create_task(_update_user_memory(user_id, str(query), out))
                return out
            except Exception as ie:
                LOGGER.error(f"[GeminiChat] Rate limit retry failed uid={user_id}: {ie}")
                return None
        # Handle transient server errors
        if code in (500, 503) or 'overloaded' in msg.lower():
            try:
                await asyncio.sleep(1.0)
                resp = await chat.send_message(query, config=base_cfg)
                text = getattr(resp, "text", None)
                out = (text or "").strip() if text else None
                if out:
                    asyncio.create_task(_update_user_memory(user_id, str(query), out))
                return out
            except Exception as ie:
                LOGGER.error(f"[GeminiChat] Transient retry failed uid={user_id}: {ie}")
                return None
        # Handle invalid/expired chat sessions
        if code in (400, 404) or 'not found' in msg.lower():
            try:
                USER_CHATS.pop(user_id, None)
                new_chat, _, new_sys = await _get_or_create_chat(user_id)
                if new_chat is None:
                    return None
                cfg = types.GenerateContentConfig(
                    system_instruction=new_sys,
                    temperature=0.6,
                    max_output_tokens=768,
                )
                resp = await new_chat.send_message(query, config=cfg)
                text = getattr(resp, "text", None)
                out = (text or "").strip() if text else None
                if out:
                    asyncio.create_task(_update_user_memory(user_id, str(query), out))
                return out
            except Exception as ie:
                LOGGER.error(f"[GeminiChat] Recreate chat failed uid={user_id}: {ie}")
                return None
        LOGGER.error(f"[GeminiChat] APIError uid={user_id}: {e}")
        return None
    except Exception as e:
        LOGGER.error(f"[GeminiChat] Error in chatt uid={user_id}: {e}")
        return None


random_response = [
    "I'm sorry, I don't have an answer for that.",
    "I'm not sure, can you please rephrase your question?",
    "I'm still learning, give me some time to improve.",
    "I wish I could help, but I don't have the information you're looking for.",
    "Hmm, that's a tough one. Let me think about it.",
    "I'm afraid I can't assist with that.",
    "I'm here to chat, but I might not have the answer you're looking for.",
]