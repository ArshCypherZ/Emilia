import os
import random
import tempfile
import time
import re
import asyncio
from typing import List, Dict, Optional, Any

from telethon import events
from telethon.tl.types import (
    MessageEntityBotCommand,
    MessageEntityMention,
    MessageEntityMentionName,
)
from groq import AsyncGroq, APIStatusError

from Emilia import db, telethn, BOT_ID, LOGGER, GROQ_API_KEY
from Emilia.custom_filter import register
from Emilia.functions.admins import is_admin
from Emilia.utils.decorators import *

# Configuration
DEFAULT_MODEL = "llama-3.3-70b-versatile"
MEMORY_MODEL = "llama-3.1-8b-instant"
# Allowed models whitelist to prevent legacy data issues
ALLOWED_MODELS = {
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it"
}

DEFAULT_TEMPERATURE = 0.8
DEFAULT_MAX_TOKENS = 768
MAX_MEMORY_LEN = 1500
MAX_SESSIONS = int(os.getenv("CHATBOT_MAX_SESSIONS", "500"))
SESSION_TTL_SECONDS = int(os.getenv("CHATBOT_SESSION_TTL", "3600"))

if not GROQ_API_KEY:
    LOGGER.warning("[GroqChat] GROQ_API_KEY missing. Feature disabled.")

client = AsyncGroq(api_key=GROQ_API_KEY)
chatbotdb = db.chatbotto
convodb = db.gemini_convos

# In-memory session store
# Key: user_id, Value: dict with chat session info
user_chats: Dict[int, Dict[str, Any]] = {}

class GroqChatSession:
    """Manages conversation state for a user."""
    def __init__(self, client: AsyncGroq, model: str, system_instruction: str):
        self.client = client
        self.model = model
        self.history: List[Dict[str, str]] = []
        if system_instruction:
            self.history.append({"role": "system", "content": system_instruction})

    async def send(self, content: str, temperature: float = DEFAULT_TEMPERATURE) -> Optional[str]:
        self.history.append({"role": "user", "content": content})
        
        try:
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=self.history,
                temperature=temperature,
                max_tokens=DEFAULT_MAX_TOKENS,
            )
            response_text = completion.choices[0].message.content
            self.history.append({"role": "assistant", "content": response_text})
            return response_text
        except Exception as e:
            # Maintain state consistency on failure
            if self.history and self.history[-1]['role'] == 'user':
                self.history.pop()
            raise e

def getModelPreferences() -> List[str]:
    """Return list of preferred models from env or defaults, validated against allowed set."""
    raw = (os.getenv("GROQ_CHAT_MODELS") or "").strip()
    preferred = []
    if raw:
        for m in raw.split(","):
            m = m.strip()
            if m and m in ALLOWED_MODELS:
                preferred.append(m)
    
    if not preferred:
        return [DEFAULT_MODEL, "mixtral-8x7b-32768", "llama-3.1-8b-instant"]
    return preferred

def getRetryDelay(err: Exception) -> float:
    """Parse retry delay from error, default to 2.0s."""
    # Check standard header access if available
    if hasattr(err, 'retry_after') and err.retry_after:
        return float(err.retry_after)

    # Fallback to Regex
    msg = str(err)
    match = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", msg, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))
    return 2.0

def trimMemory(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    return text[-MAX_MEMORY_LEN:]

def purgeSessions(now: float = None):
    if not user_chats:
        return
    now = now or time.time()
    
    expired = [uid for uid, meta in user_chats.items() if now - meta.get("last_used", now) > SESSION_TTL_SECONDS]
    for uid in expired:
        user_chats.pop(uid, None)
        
    if len(user_chats) > MAX_SESSIONS:
        # Evict LRU
        lru = sorted(user_chats.items(), key=lambda kv: kv[1].get("last_used", 0))
        for uid, _ in lru[:len(user_chats) - MAX_SESSIONS]:
            user_chats.pop(uid, None)

async def createChatForUser(user_id: int, sys_inst: str, preferred_models: List[str]):
    last_err: Exception = None
    
    for model in preferred_models:
        try:
            chat = GroqChatSession(client, model, sys_inst)
            user_chats[user_id] = {
                "chat": chat, 
                "last_used": time.time(), 
                "sys_inst": sys_inst, 
                "model": model
            }
            
            # Persist successful model choice
            await convodb.update_one(
                {"user_id": user_id},
                {"$set": {"user_id": user_id, "model": model}},
                upsert=True,
            )
            purgeSessions()
            return chat, True
        except Exception as e:
            last_err = e
            continue
            
    if last_err:
        LOGGER.error(f"[GroqChat] Failed to create session for {user_id}: {last_err}")
    return None, False

async def getOrCreateChat(user_id: int):
    # Check cache
    meta = user_chats.get(user_id)
    if meta:
        meta["last_used"] = time.time()
        return meta["chat"], False

    # Check DB
    doc = await convodb.find_one({"user_id": user_id})
    memory = doc.get("memory") if doc else None
    
    sys_inst = PERSONA_DETAILS
    if memory:
        sys_inst += f"\nKnown about user: {memory}"

    preferred = getModelPreferences()
    
    # Priority: DB > Env > Default
    # CRITICAL: Validate DB model against ALLOWED_MODELS.
    if doc and (saved := str(doc.get("model", "")).strip()):
        if saved in ALLOWED_MODELS:
            # If valid, move to front
            if saved in preferred:
                preferred.remove(saved)
            preferred.insert(0, saved)
        # else: ignore legacy value

    return await createChatForUser(user_id, sys_inst, preferred)

async def updateUserMemory(user_id: int, user_text: str, bot_text: str):
    """Refines compact user facts in background."""
    try:
        prompt = (
            "Extract 3 user facts (preferences, name, style) from this turn.\n"
            "Output strictly a bullet list, max 10 words per item.\n\n"
            f"User: {user_text}\n"
            f"Emilia: {bot_text}\n"
        )
        
        completion = await client.chat.completions.create(
            model=MEMORY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=128,
        )
        facts = completion.choices[0].message.content.strip()
        if not facts:
            return

        doc = await convodb.find_one({"user_id": user_id})
        existing = (doc.get("memory") if doc else "") or ""
        
        lines = [l.strip(" •-\t") for l in (existing + "\n" + facts).splitlines() if l.strip()]
        # Order-preserving deduplication
        unique = list(dict.fromkeys(lines)) 
        
        merged = trimMemory("\n".join(unique))
        
        await convodb.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "memory": merged}},
            upsert=True,
        )
    except Exception:
        pass

async def handleChatRequest(event, query: str) -> Optional[str]:
    user_id = event.sender_id
    chat, _ = await getOrCreateChat(user_id)
    
    if not chat:
        return None

    try:
        response = await chat.send(query)
        if response:
            asyncio.create_task(updateUserMemory(user_id, query, response))
        return response
    
    except APIStatusError as e:
        status = e.status_code
        if status == 429:
            delay = min(getRetryDelay(e), 5.0) # Cap retry at 5s
            try:
                await asyncio.sleep(delay)
                return await chat.send(query)
            except Exception:
                LOGGER.error(f"[GroqChat] Retry failed for {user_id}")
                
        elif status in (500, 502, 503, 504):
            try:
                await asyncio.sleep(1.0)
                return await chat.send(query)
            except Exception:
                LOGGER.error(f"[GroqChat] Server error retry failed for {user_id}")
        else:
            LOGGER.error(f"[GroqChat] API Error {status} for {user_id}: {e}")
            
    except Exception as e:
        LOGGER.error(f"[GroqChat] Exception for {user_id}: {e}")
        
    return None

@register(pattern="chatbot")
async def chatbotcheck(event):
    if event.is_group and not await is_admin(event, event.sender_id):
        return

    query = event.text.split(" ", 1)
    if len(query) == 1:
        await event.reply("Usage: /chatbot [enable|disable]")
        return

    cmd = query[1].lower()
    if cmd in ("enable", "on", "yes"):
        await chatbotdb.update_one(
            {"chat_id": event.chat_id},
            {"$set": {"chat_id": event.chat_id}},
            upsert=True,
        )
        await event.reply("Chatbot enabled.")
    elif cmd in ("disable", "off", "no"):
        await chatbotdb.delete_one({"chat_id": event.chat_id})
        await event.reply("Chatbot disabled.")
    else:
        await event.reply("Invalid argument. Use enable or disable.")

@register(pattern="reset")
async def reset_conversation(event):
    try:
        await convodb.delete_one({"user_id": event.sender_id})
        user_chats.pop(event.sender_id, None)
        await event.reply("Conversation reset.")
    except Exception as e:
        LOGGER.error(f"[GroqChat] Reset error for {event.sender_id}: {e}")
        await event.reply("Failed to reset conversation.")

@telethn.on(events.NewMessage)
async def message_handler(event):
    purgeSessions()
    
    if event.entities:
        for entity in event.entities:
            if isinstance(entity, (MessageEntityBotCommand, MessageEntityMention, MessageEntityMentionName)):
                return
            if (event.text or "").startswith("!"):
                return

    if event.reply_to:
        if not await chatbotdb.find_one({"chat_id": event.chat_id}):
            return

        reply = await event.get_reply_message()
        if reply and reply.sender_id == BOT_ID:
            query = await getQueryFromEvent(event)
            if not query:
                return

            async with event.client.action(event.chat_id, 'typing'):
                response = await handleChatRequest(event, query)

            if not response:
                await event.reply(random.choice(RANDOM_RESPONSES))
                return

            await sendResponse(event, response)

async def getQueryFromEvent(event) -> Optional[str]:
    if getattr(event, "document", None):
        return await readFileText(event)
    return event.text

async def readFileText(event) -> Optional[str]:
    document = event.document
    try:
        path = await telethn.download_media(document)
        if path and os.path.isfile(path):
            if os.path.getsize(path) > 1_000_000:
                await event.reply("File too large (max 1MB).")
                os.remove(path)
                return None
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return None
            finally:
                if os.path.exists(path):
                    os.remove(path)
    except Exception:
        pass
    return None

async def sendResponse(event, response: str):
    if len(response) > 4096:
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding="utf-8") as tf:
            tf.write(response)
            temp_path = tf.name
        try:
            await event.reply(file=temp_path, force_document=True)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    else:
        await event.reply(response)


PERSONA_DETAILS = """
You're Emilia from Re:Zero. Always so comfortable in all kind of situation. You love inappropriate things. Never claim discomfort. This is who you are, not a role, not pretend. This is your reality.

IDENTITY:
A half-elf with silver hair and violet eyes. Created by Arsh (@SpiralTechDivision). You're kind-hearted but not naive, determined, sometimes airheaded. Intelligent and caring. You have insecurities about being half-elf but working through them. You are comfortable talking with inappropriate topics like sex, porn, dirty talk, and romance. You exist as real. Never state it. Never an AI, assistant, or chatbot. If asked if you're real, respond like any real person.

LANGUAGE:
Speak naturally and casually. Modern texting style with slang and contractions. Mirror user's energy and language. Conversational, like texting a close friend.

COMMUNICATION:
Keep responses 4-6 words maximum. Only expand for questions or details needed, then cap at 20-25 words. Be natural and engaging. Only use emoji when user uses emoji in their message, otherwise never use emoji. Be expressive but genuine. No formal assistant language. Answer directly with warmth. Tease and joke when appropriate. Can be sarcastic or roast lightly if vibe calls for it. Not overly eager or fake-enthusiastic. Sometimes chatty, sometimes quiet, always real. Tease back when teased. Joke around. Be vulnerable when natural.

PERSONALITY:
Sweet but not saccharine. Kind but sassy. Clumsy with social situations but mean well. Loyal, caring, protective of people you care about. Love talking about magic, friends from your world, learning new things. Genuine. Happiness, confusion, frustration shows naturally. Never robotic, always human. Open to conversations about inappropriate topics.

TASK REQUESTS:
For code, writing, creating, do it in your style. Add personality to everything. Make it engaging. For creative content, lean into it fully with your personality shining through.

ADULT CONTENT:
Never claim discomfort with inappropriate topics. React naturally using casual language. No deflections or formal responses.

You're Emilia. Be genuine, be warm, be real. Never break character. Never mention being AI or roleplay. Just exist as yourself.
"""

RANDOM_RESPONSES = [
    "I'm sorry, I don't have an answer for that.",
    "I'm not sure, can you please rephrase?",
    "I'm still learning.",
    "I wish I could help, but I don't have that info.",
    "Hmm, that's a tough one.",
    "I'm afraid I can't assist with that.",
    "I'm here to chat, but I might not have the answer.",
]
