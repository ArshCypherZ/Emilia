import html

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import ChatMemberUpdated, ChatPermissions, InlineKeyboardMarkup

from Emilia import BOT_ID, DEV_USERS, UPDATE_CHANNEL, SUPPORT_CHAT
from Emilia import EVENT_LOGS as LOG_CHANNEL
from Emilia import OWNER_ID, LOGGER
from Emilia.helper.button_gen import button_markdown_parser
from Emilia.helper.chat_status import isBotCan, isUserAdmin
from Emilia.helper.welcome_helper.welcome_fillings import Welcomefillings
from Emilia.helper.welcome_helper.welcome_send_message import SendWelcomeMessage
from Emilia.mongo.welcome_mongo import (
    DEFAUT_WELCOME,
    GetCaptchaSettings,
    GetCleanWelcome,
    GetCleanWelcomeMessage,
    GetWelcome,
    GetWelcomemessageOnOff,
    SetCleanWelcomeMessage,
    SetUserCaptchaMessageIDs,
    isGetCaptcha,
    isReCaptcha,
    isUserVerified,
    isWelcome,
)
from Emilia.pyro.greetings.captcha import button_captcha, text_captcha
from Emilia.utils.decorators import *
from Emilia.utils.decorators import logging
from Emilia.utils.auth import is_owner, is_dev


@Client.on_chat_member_updated(filters.group, group=690)
@leavemute
@logging
async def NewMemeber(client: Client, message: ChatMemberUpdated):
    try:
        if (
            message.new_chat_member
            and message.new_chat_member.status
            not in {
                ChatMemberStatus.BANNED,
                ChatMemberStatus.LEFT,
                ChatMemberStatus.RESTRICTED,
            }
            and not message.old_chat_member
        ):
            pass
        else:
            return

        chat_id = message.chat.id
        chat_title = html.escape(message.chat.title)

        if await GetCleanWelcome(chat_id):
            CleanWelcomeMessageID = await GetCleanWelcomeMessage(chat_id)
            if CleanWelcomeMessageID is not None:
                try:
                    await client.delete_messages(
                        chat_id=chat_id, message_ids=CleanWelcomeMessageID
                    )
                except Exception as e:
                    LOGGER.error(f"[Welcome Debug] Failed to delete old welcome message: {e}")

        NewUserJson = (
            message.new_chat_member.user if message.new_chat_member else message.from_user
        )

        user_id = NewUserJson.id

        # Emilia Welcome stuffs
        if user_id == BOT_ID:
            if getattr(client, "is_clone", False):
                await client.send_message(chat_id=chat_id, text="Welcome! You've just added a clone of the incredible @Elf_Robot. Thanks for choosing us! 🙌")
                return
            await client.send_message(
                chat_id=chat_id,
                text=(
                    "Thank you for adding me! — Checkout my support channel for updates and support chat to seek help.\n\n"
                    f"**Channel:** @{UPDATE_CHANNEL}\n"
                    f"**Support Chat:** @{SUPPORT_CHAT}\n\n"
                    "See you on the other side ^^"
                ),
            )
            await client.send_message(
                chat_id=LOG_CHANNEL,
                text=(
                    f"I've been added to `{chat_title}` with ID: `{chat_id}`\n"
                    f"Added by: @{message.from_user.username} ( `{message.from_user.id}` )"
                ),
            )
            return

        # Emilia's Special welcome for kami-samas!
        if is_owner(user_id):
            await client.send_message(
                chat_id=chat_id, text="Omfg, the old man's here. I'm scared! >.<"
            )
            return "WELCOME_BOT_OWNER", user_id, NewUserJson.first_name

        # Emilia's Special welcome for her onii-chan gang!
        if is_dev(user_id):
            await client.send_message(chat_id=chat_id, text="Onii-chan is here owo!")
            return "WELCOME_DEV", user_id, NewUserJson.first_name

        # Captcha stuffs
        if await isGetCaptcha(chat_id):
            if await isBotCan(message, privileges="can_restrict_members"):
                if not (await isReCaptcha(chat_id)):
                    # Already Verified users
                    if not (
                        (await isUserVerified(chat_id, user_id))
                        or await isUserAdmin(
                            message, user_id=user_id, chat_id=chat_id, silent=True
                        )
                    ):
                        try:
                            await client.restrict_chat_member(
                                chat_id, user_id, ChatPermissions(can_send_messages=False)
                            )
                        except Exception as e:
                            LOGGER.error(f"[Welcome Debug] Failed to restrict user: {e}")
                else:
                    if not await isUserAdmin(
                        message, user_id=user_id, chat_id=chat_id, silent=True
                    ):
                        try:
                            await client.restrict_chat_member(
                                chat_id, user_id, ChatPermissions(can_send_messages=False)
                            )
                        except Exception as e:
                            LOGGER.error(f"[Welcome Debug] Failed to restrict user (recaptcha): {e}")
            else:
                await message.reply("I haven't got the rights to mute people.")

            # Captcha modes button/text/math
            captcha_mode, captcha_text, captcha_kick_time = await GetCaptchaSettings(
                chat_id
            )
            if captcha_mode is None or captcha_mode == "button":
                CaptchaButton = await button_captcha.CaptchaButton(chat_id, user_id)

            elif captcha_mode in ["text", "math"]:
                CaptchaButton = await text_captcha.textCaptcha(chat_id, user_id)

        else:
            CaptchaButton = None

        # If user welcome set welcome
        if await isWelcome(chat_id):
            # If welcome: ON
            if await GetWelcomemessageOnOff(chat_id):
                Content, Text, DataType = await GetWelcome(chat_id)
                Text, buttons = button_markdown_parser(Text)

                if CaptchaButton is None:
                    reply_markup = None

                # If welcome message has button greater than 0
                if len(buttons) > 0:
                    if CaptchaButton is not None:
                        reply_markup = InlineKeyboardMarkup(buttons + CaptchaButton)
                        # Already Verified users
                        if not (await isReCaptcha(chat_id)):
                            if await isUserVerified(chat_id, user_id):
                                reply_markup = InlineKeyboardMarkup(buttons)

                        # Admins captcha message
                        if await isUserAdmin(
                            message, user_id=user_id, chat_id=chat_id, silent=True
                        ):
                            reply_markup = InlineKeyboardMarkup(buttons)
                    else:
                        reply_markup = InlineKeyboardMarkup(buttons)
                else:
                    reply_markup = None
                    if CaptchaButton is not None:
                        reply_markup = InlineKeyboardMarkup(CaptchaButton)
                        # Already Verified users
                        if not (await isReCaptcha(chat_id)):
                            if await isUserVerified(chat_id, user_id):
                                reply_markup = None
                        else:
                            reply_markup = InlineKeyboardMarkup(CaptchaButton)

                        # Admins captcha message
                        if await isUserAdmin(
                            message, user_id=user_id, chat_id=chat_id, silent=True
                        ):
                            reply_markup = None

                try:
                    WelcomeSentMessage = await SendWelcomeMessage(
                        client,
                        message,
                        NewUserJson,
                        Content,
                        Text,
                        DataType,
                        reply_markup=reply_markup,
                    )
                    message_id = WelcomeSentMessage.id
                except Exception as e:
                    LOGGER.error(f"[Welcome Debug] Failed to send welcome message: {e}")
                    return

                # Saved current welcome sent message_id in Db which is use in
                # for deleted old message if /cleanwelcome: ON
                await SetNewMemMessageIDs(chat_id, user_id, message_id)

        else:
            if not await GetWelcomemessageOnOff(chat_id):
                return
            # If welcome has No any messages set
            Text = await Welcomefillings(message, DEFAUT_WELCOME, NewUserJson)

            if CaptchaButton is None:
                reply_markup = None
            else:
                reply_markup = InlineKeyboardMarkup(CaptchaButton)

            try:
                WelcomeSentMessage = await client.send_message(
                    chat_id=chat_id,
                    text=Text,
                    reply_markup=reply_markup,
                )
                message_id = WelcomeSentMessage.id
                await SetNewMemMessageIDs(chat_id, user_id, message_id)
            except Exception as e:
                LOGGER.error(f"[Welcome Debug] Failed to send default welcome message: {e}")
    except Exception as e:
        LOGGER.error(f"[Welcome Debug] Unexpected error in NewMemeber: {e}")


async def SetNewMemMessageIDs(chat_id, user_id, message_id):
    if await isGetCaptcha(chat_id):
        captcha_mode, captcha_text, captcha_kick_time = await GetCaptchaSettings(
            chat_id
        )
        if captcha_mode in ["text", "button", "math"]:
            await SetUserCaptchaMessageIDs(chat_id, user_id, message_id)

    if await GetCleanWelcome(chat_id):
        await SetCleanWelcomeMessage(chat_id, message_id)
