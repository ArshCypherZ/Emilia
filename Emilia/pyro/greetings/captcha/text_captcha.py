import os
import random

from captcha.image import ImageCaptcha
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from Emilia import BOT_USERNAME
from Emilia.helper.chat_status import isUserAdmin
from Emilia.mongo.welcome_mongo import (
    CaptchaChanceUpdater,
    GetCaptchaSettings,
    GetChance,
    GetUserCaptchaMessageIDs,
    SetCaptchaTextandChances,
    isReCaptcha,
    isRuleCaptcha,
    isUserVerified,
)
from Emilia.pyro.greetings.captcha.captcharules_button import ruleCaptchaButton
from Emilia.pyro.greetings.utils.actions import failedAction, passedAction
from Emilia.pyro.greetings.utils.captcha_text_gen import ButtonGen
from Emilia.pyro.greetings.utils.random_string_gen import (
    RandomStringGen,
    mathCaptchaGen,
)

CAPTCHA_START_STRINGS = [
    (
        "Please complete the above CAPTCHA!\n\n"
        "You will be given `3` tries in order to get yourself verified and gain access to the chat."
    ),
    ("CAPTCHA is not matched -  you've `2` tries left."),
    ("AGAIN incorrect - you now only have `1` try left.\n\n"),
]


async def textCaptcha(chat_id, user_id):
    captcha_mode, captcha_text, captcha_kick_time = await GetCaptchaSettings(chat_id)
    if captcha_mode in ["text", "math"]:
        Captcha_button = [
            [
                InlineKeyboardButton(
                    text=captcha_text,
                    url=f"http://t.me/{BOT_USERNAME}?start=captcha_{captcha_mode}_{user_id}_{chat_id}",
                )
            ]
        ]

        return Captcha_button


async def textCaptchaRedirect(client, message):
    user_id = message.from_user.id
    message.chat.id
    _match = message.text.split()[1].split("_")[1]

    if _match in ["text", "math"]:
        new_user_id = int(message.text.split()[1].split("_")[2])
        new_chat_id = int(message.text.split()[1].split("_")[3])

        if new_user_id == user_id:
            # Already Verified users
            if not (await isReCaptcha(chat_id=new_chat_id)):
                if await isUserVerified(new_chat_id, new_user_id):
                    await message.reply(
                        "You already passed the CAPTCHA, You don't need to verify yourself again.",
                        quote=True,
                    )
                    return

            # Admins captcha message
            if await isUserAdmin(
                message,
                pm_mode=True,
                chat_id=new_chat_id,
                user_id=new_user_id,
                silent=True,
            ):
                await message.reply(
                    "You are admin, You don't have to complete CAPTCHA.", quote=True
                )
                return

            # Captcha generating
            if _match == "text":
                CaptchaStringList = RandomStringGen()
                CaptchaString = random.choice(CaptchaStringList)

            elif _match == "math":
                answer_dict, CaptchaStringList = mathCaptchaGen()
                CaptchaString = (
                    f"{answer_dict.get('num01')} + {answer_dict.get('num02')} = ?"
                )

            CaptchaLoc = f"Emilia/pyro/greetings/captcha/CaptchaDump/EmiliaCaptcha_text_{new_user_id}_{new_chat_id}.png"
            image = ImageCaptcha(
                width=270, height=90, fonts=["path/font_03.ttf"], font_sizes=(50, 50)
            )
            image.generate(CaptchaString)
            image.write(CaptchaString, CaptchaLoc)

            chance = await GetChance(new_chat_id, new_user_id)

            if chance is None:
                chance = 0

            if chance >= 3:
                (
                    message_id,
                    correct_captcha,
                    chances,
                    captcha_list,
                ) = await GetUserCaptchaMessageIDs(
                    chat_id=new_chat_id, user_id=new_user_id
                )
                await failedAction(
                    client,
                    message=message,
                    user_id=new_user_id,
                    chat_id=new_chat_id,
                    message_id=message_id,
                )
                await message.reply("You have lost your'll 3 CAPTCHA's chances")
                return

            if _match == "math":
                CaptchaString = answer_dict.get("answer")

            await SetCaptchaTextandChances(
                new_chat_id, new_user_id, str(CaptchaString), chance, CaptchaStringList
            )
            keyboard = ButtonGen(CaptchaStringList, new_chat_id)

            await client.send_photo(
                chat_id=new_user_id,
                photo=CaptchaLoc,
                caption=CAPTCHA_START_STRINGS[chance],
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            os.remove(CaptchaLoc)

        else:
            # Admins captcha message
            if await isUserAdmin(
                message,
                pm_mode=True,
                chat_id=new_chat_id,
                user_id=new_user_id,
                silent=True,
            ):
                await message.reply(
                    "You are admin, You don't have to complete CAPTCHA.", quote=True
                )
                return

            else:
                await message.reply("This wasn't for you.", quote=True)


@Client.on_callback_query(filters.create(lambda _, __, query: "textc_" in query.data))
async def textCaptchaCallBack(client: Client, callback_query: CallbackQuery):
    RandomString = callback_query.data.split("_")[1]
    chat_id = int(callback_query.data.split("_")[2])
    user_id = callback_query.from_user.id
    callback_query.from_user.mention

    if not (await isReCaptcha(chat_id=chat_id)) and (
        await isUserVerified(chat_id=chat_id, user_id=user_id)
    ):
        await client.edit_message_caption(
            chat_id=user_id,
            message_id=callback_query.message.id,
            caption="You've already completed the CAPTCHA!",
        )

    if (await GetUserCaptchaMessageIDs(chat_id=chat_id, user_id=user_id)) is None:
        await client.edit_message_caption(
            chat_id=user_id,
            message_id=callback_query.message.id,
            caption="Something went wrong, try agian.",
        )
        return

    message_id, correct_captcha, chances, captcha_list = await GetUserCaptchaMessageIDs(
        chat_id, user_id
    )

    # if chances is 3 reached
    if chances >= 2:
        await callback_query.edit_message_caption(caption="You failed this captcha")
        await failedAction(
            client,
            message=callback_query,
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
        )

    # When user clicked on wrong button
    elif RandomString != correct_captcha:
        chances += 1
        await CaptchaChanceUpdater(chat_id, user_id, chances)

        await client.edit_message_caption(
            chat_id=user_id,
            message_id=callback_query.message.id,
            caption=CAPTCHA_START_STRINGS[chances],
            reply_markup=InlineKeyboardMarkup(ButtonGen(captcha_list, chat_id)),
        )

        await callback_query.answer(text=("You have clicked on wrong CAPTCHA button."))

    # When use click on correct CAPTCHA button
    elif RandomString == correct_captcha:
        if await isRuleCaptcha(chat_id=chat_id):
            await client.delete_messages(
                chat_id=user_id, message_ids=callback_query.message.id
            )
            await ruleCaptchaButton(
                client, message=callback_query, chat_id=chat_id, message_id=message_id
            )
        else:
            str_chat_id = str(chat_id).replace("-100", "")
            PassedButton = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="Go Back to the chat",
                            url=f"http://t.me/c/{str_chat_id}/{message_id}",
                        )
                    ]
                ]
            )

            await client.edit_message_caption(
                chat_id=user_id,
                message_id=callback_query.message.id,
                caption="you passed the captcha.",
                reply_markup=PassedButton,
            )

            await callback_query.answer(text=("You have passed the CAPTCHA."))

            await passedAction(client, chat_id=chat_id, user_id=user_id, message_id=message_id)
