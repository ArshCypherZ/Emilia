import aiohttp
from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    ChatJoinRequest,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from Emilia import LOGGER
from Emilia.mongo.autoapprove_mongo import get_autoapprove_mode
from Emilia.mongo.feds_db import get_chat_fed, get_fban_user
from Emilia.mongo.rules_mongo import get_rules
from Emilia.mongo.welcome_mongo import GetCaptchaSettings
from Emilia.modules.plugins.greetings.captcha.text_captcha import dispatch_text_math_captcha
from Emilia.modules.plugins.greetings.utils.actions import passedAction
from Emilia.helper.http import get_aiohttp_session
from Emilia.mongo.autoapprove_mongo import cache
from pyrogram.errors import UserIsBlocked, PeerIdInvalid
from Emilia.utils.decorators import *


async def check_cas(user_id: int) -> bool:
    """Returns True if the user is CAS banned."""
    cache_key = f"cas_{user_id}"
    cached_result = await cache.get(cache_key)
    if cached_result is not None:
        return cached_result

    try:
        session = await get_aiohttp_session()
        async with session.get(
            f"https://api.cas.chat/check?user_id={user_id}", timeout=3
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                is_banned = data.get("ok", False)
                await cache.set(cache_key, is_banned, ttl=3600)
                return is_banned
    except Exception as e:
        LOGGER.error(f"CAS Check Error: {e}")
    return False


@Client.on_chat_join_request(filters.group | filters.channel)
async def autoapprove_handler(client: Client, request: ChatJoinRequest):
    chat_id = request.chat.id
    user_id = request.from_user.id
    mode = await get_autoapprove_mode(chat_id)

    if mode == "off":
        return

    # Anti-spam hook (Runs for antispam, rules, and captcha modes)
    if mode in ["antispam", "rules", "captcha"]:
        # Check FedBans
        fed_id = await get_chat_fed(chat_id)
        if fed_id:
            fban_cache_key = f"fban_{fed_id}_{user_id}"
            is_fed_banned = await cache.get(fban_cache_key)
            if is_fed_banned is None:
                is_fed_banned, _, _ = await get_fban_user(fed_id, str(user_id))
                await cache.set(fban_cache_key, is_fed_banned, ttl=60)
                
            if is_fed_banned:
                try:
                    await client.decline_chat_join_request(chat_id, user_id)
                except Exception:
                    pass
                return

        # Check CAS
        is_cas_banned = await check_cas(user_id)
        if is_cas_banned:
            try:
                await client.decline_chat_join_request(chat_id, user_id)
            except Exception:
                pass
            return

    # Mode: antispam / on -> Approve immediately
    if mode in ["on", "antispam"]:
        try:
            await client.approve_chat_join_request(chat_id, user_id)
        except Exception as e:
            LOGGER.error(f"Failed to approve join request: {e}")
        return

    # Mode: captcha
    if mode == "captcha":
        captcha_mode, captcha_text, _ = await GetCaptchaSettings(chat_id)

        if captcha_mode in ["text", "math"]:
            try:
                caption = f"To join **{request.chat.title}**, please solve the captcha below to prove you are human."
                await dispatch_text_math_captcha(client, user_id, chat_id, captcha_mode, caption=caption)
            except (UserIsBlocked, PeerIdInvalid):
                pass
            except Exception as e:
                LOGGER.error(f"Failed to dispatch math/text captcha: {e}")
            return

        # Default to button captcha
        if not captcha_text:
            captcha_text = "🤖 I am Human"

        text = f"Hello {request.from_user.first_name}!\n\nTo join **{request.chat.title}**, please prove you are human by clicking the button below."
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(captcha_text, callback_data=f"cjr_cap_{chat_id}")]]
        )
        try:
            await client.send_message(user_id, text=text, reply_markup=keyboard)
        except (UserIsBlocked, PeerIdInvalid):
            # Blocked bots pass silently, leaving the request in pending queue (Manual Review Pattern).
            pass
        except Exception:
            pass
        return

    # Mode: rules
    if mode == "rules":
        rules_text = await get_rules(chat_id)
        if not rules_text:
            rules_text = "The administrators haven't set any rules for this chat, but please behave nicely!"
            
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ I Agree", callback_data=f"cjr_rul_{chat_id}")]]
        )
        
        try:
            if len(rules_text) > 3900:
                import io
                rules_file = io.BytesIO(rules_text.encode("utf-8"))
                rules_file.name = "rules.txt"
                text = f"**Welcome to {request.chat.title}!**\n\nPlease read the attached rules and click 'I Agree' to join."
                await client.send_document(user_id, document=rules_file, caption=text, reply_markup=keyboard)
            else:
                text = f"**Welcome to {request.chat.title}!**\n\nPlease read and agree to the following rules before joining:\n\n{rules_text}"
                await client.send_message(user_id, text=text, reply_markup=keyboard)
        except (UserIsBlocked, PeerIdInvalid):
            # Blocked bots pass silently, leaving the request in pending queue (Manual Review Pattern).
            pass
        except Exception:
            pass
        return


def cap_filter(_, __, query: CallbackQuery):
    return query.data and query.data.startswith("cjr_cap_")

@Client.on_callback_query(filters.create(cap_filter))
async def autoapprove_captcha_callback(client: Client, query: CallbackQuery):
    chat_id = int(query.data.split("_")[2])
    user_id = query.from_user.id

    try:
        await passedAction(client, chat_id, user_id, 0)
        await query.message.edit_text("✅ Captcha passed! You have been approved to join the group.")
    except Exception as e:
        await query.answer("Failed to approve. You might have been declined manually or already approved.", show_alert=True)
        LOGGER.error(f"Captcha Approve Error: {e}")


def rul_filter(_, __, query: CallbackQuery):
    return query.data and query.data.startswith("cjr_rul_")

@Client.on_callback_query(filters.create(rul_filter))
async def autoapprove_rules_callback(client: Client, query: CallbackQuery):
    chat_id = int(query.data.split("_")[2])
    user_id = query.from_user.id

    try:
        await passedAction(client, chat_id, user_id, 0)
        await query.message.edit_text("✅ Thank you for agreeing to the rules! You have been approved to join the group.")
    except Exception as e:
        await query.answer("Failed to approve. You might have been declined manually or already approved.", show_alert=True)
        LOGGER.error(f"Rules Approve Error: {e}")
