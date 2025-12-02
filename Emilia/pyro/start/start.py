import os
from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from bson.objectid import ObjectId

from Emilia import custom_filter, BOT_NAME, TOKEN, SUPPORT_CHAT, UPDATE_CHANNEL, START_PIC
from Emilia.anime.bot import get_anime, get_recommendations, auth_link_cmd, logout_cmd, get_additional_info, code_cmd
from Emilia.pyro.connection.connect import connectRedirect
from Emilia.pyro.greetings.captcha.button_captcha import buttonCaptchaRedirect
from Emilia.pyro.greetings.captcha.text_captcha import textCaptchaRedirect
from Emilia.pyro.notes.private_notes import note_redirect
from Emilia.pyro.rules.rules import rulesRedirect
from Emilia.utils.decorators import *
from Emilia.tele.clone import startpic
from Emilia.utils.helper import AUTH_USERS, get_btns
from Emilia.anime.bot import help_

START_TEXT = """
Welcome to [{} :3]({})

This bot give varieties of features such as
➩ Group Management
➩ Spammer Protection
➩ Fun like chatbot
➩ Clone, Ranking, AI System
➩ Anime Loaded Modules
➩ Inline Games

Use the buttons buttons or /help to checkout even more!
"""


@Client.on_message(custom_filter.command(commands="start"))
@leavemute
@rate_limit(RATE_LIMIT_GENERAL)
async def starttt(client, message):
    if len(message.text.split()) == 1:
        if message.chat.type == ChatType.PRIVATE:
            from Emilia.mongo.users_mongo import add_user
            
            current_bot_id = int(client.bot_token.split(":")[0])
            
            if getattr(client, "is_clone", False):
                await add_user(message.from_user.id, message.from_user.username, bot_id=current_bot_id)

            # Look up custom start picture for this specific bot
            custom_start_pic = None
            pic_data = await startpic.find_one({"bot_id": current_bot_id})
            if pic_data:
                custom_start_pic = pic_data.get("file_id") or pic_data.get("url")
            
            start_pic_url = custom_start_pic if custom_start_pic else START_PIC
            
            buttons = [
                [InlineKeyboardButton("Help", callback_data="help_back")],
                [
                    InlineKeyboardButton(
                        "Support", url=f"https://t.me/{SUPPORT_CHAT}"
                    ),
                    InlineKeyboardButton("News", url=f"https://t.me/{UPDATE_CHANNEL}"),
                ],
                [InlineKeyboardButton("How to Clone?", callback_data="clone_help")],
                [InlineKeyboardButton("Source Code", url="https://github.com/ArshCypherZ/Emilia")],
            ]
            
            await message.reply_text(
                START_TEXT.format(BOT_NAME, start_pic_url),
                reply_markup=InlineKeyboardMarkup(buttons),
                disable_web_page_preview=False,
            )

        else:
            from Emilia.mongo.users_mongo import add_chat
            
            if getattr(client, "is_clone", False):
                current_bot_id = int(client.bot_token.split(":")[0])
                await add_chat(message.chat.id, message.chat.title, bot_id=current_bot_id)
            
            await message.reply("Hey there, ping me in my PM to get help!")

    if len(message.text.split()) > 1:
        user = message.from_user.id
        chat = message.chat.id
        deep_cmd_list = (message.text.split()[1]).split("_")

        # Captcha Redirect Implementation
        if startCheckQuery(message, StartQuery="captcha"):
            await buttonCaptchaRedirect(client, message)
            await textCaptchaRedirect(client, message)

        # Private Notes Redirect Implementation
        elif startCheckQuery(message, StartQuery="note"):
            await note_redirect(client, message)

        # Connection Redirect Implementation
        elif startCheckQuery(message, StartQuery="connect"):
            await connectRedirect(client, message)

        # Rules Redirect Implementation
        elif startCheckQuery(message, StartQuery="rules"):
            await rulesRedirect(message, client)

        elif startCheckQuery(message, StartQuery="anihelp"):
            await help_(client, message)

        elif startCheckQuery(message, StartQuery="auth"):
            await auth_link_cmd(client, message)

        elif startCheckQuery(message, StartQuery="logout"):
            await logout_cmd(client, message)

        elif deep_cmd_list[0] == "des":
            try:
                req = deep_cmd_list[3]
            except IndexError:
                req = "desc"
            pic, result = await get_additional_info(
                deep_cmd_list[2], deep_cmd_list[1], req
            )
            await client.send_photo(chat, pic)
            try:
                await client.send_message(
                    chat, result.replace("~!", "").replace("!~", "")
                )
            except (TypeError, AttributeError):
                await client.send_message(chat, "No description available!!!")

        elif deep_cmd_list[0] == "anime":
            auth = False
            if await AUTH_USERS.find_one({"id": user}):
                auth = True
            result = await get_anime(
                {"id": int(deep_cmd_list[1])}, user=user, auth=auth
            )
            pic, msg = result[0], result[1]
            buttons = get_btns("ANIME", result=result, user=user, auth=auth)
            await client.send_photo(chat, pic, caption=msg, reply_markup=buttons)

        elif deep_cmd_list[0] == "anirec":
            result = await get_recommendations(deep_cmd_list[1])
            await client.send_message(user, result, disable_web_page_preview=True)

        elif (message.text.split()[1]).split("_", 1)[0] == "code":
            if not os.environ.get("ANILIST_REDIRECT_URL"):
                return
            qry = (message.text.split()[1]).split("_", 1)[1]
            k = await AUTH_USERS.find_one({"_id": ObjectId(qry)})
            await code_cmd(k["code"], message)


def startCheckQuery(message, StartQuery=None) -> bool:
    if (
        StartQuery in message.text.split()[1].split("_")[0]
        and message.text.split()[1].split("_")[0] == StartQuery
    ):
        return True
    else:
        return False

button = [[InlineKeyboardButton("Clone Commands", callback_data="bot_clone")]]

@Client.on_callback_query()
async def callback_query_handler(client, callback_query):
    if callback_query.data == "clone_help":  
        await callback_query.message.reply_text(clone_help, reply_markup=InlineKeyboardMarkup(button))
        await callback_query.message.delete()
        return
    if callback_query.data == "bot_clone":   
        await callback_query.message.reply_text(help_text, disable_web_page_preview=True)
        await callback_query.message.delete()
        return


clone_help = """
Emilia Clones are exact replicas of @Elf_Robot but with a personalized name and profile picture, ensuring enhanced performance and stability.

Clones inherit all functionalities, updates, and database entries from the original bot. When switching between clones in a group, there's no need to reconfigure settings.

**To create a clone**:
1. Open @BotFather.
2. Initiate a chat with @BotFather and type /newbot.
3. Choose a name for your clone.
4. Select a username for your clone.
5. Copy the API token provided by @BotFather.
6. Send the API token to Emilia via private message using `/clone [apitokenhere]`. Ensure to remove '[ ]'.
7. **Your clone goes live instantly!**

To modify the profile picture of your clone, send /setuserpic to @BotFather, choose the clone, and upload the new image.


**CAUTION**: When adding a clone to a group, remember to assign it administrator privileges!
"""

help_text = """
Nowadays, many people use foreign bots to manage their groups. But this can be risky as the bot owner can misuse your data.
To solve this issue, we have introduced the clone feature. Without the need for any coding knowledge, database, hosting, or anything else, this feature allows you to clone @Elf_Robot to your own bots and manage your group without any privacy concerns.

**Clone Commands:**

• /clone `[bottoken]`: Clones @Elf_Robot to your provided bot. **Goes live instantly!** Make sure to remove the square brackets.
• /deleteclone `[bottoken]`: Deletes the cloned bot from our server.
• /setstartpic `[picurl]`: Sets the start pic for your cloned bot.
• /broadcast `-flag [reply]`: Broadcasts the replied message to all the groups where the cloned bot is present.

Flags available for broadcast:
- `-all`: Broadcast to all groups and users.
- `-chats`: Broadcast to all groups only.
- `-users`: Broadcast to all users only.

Example:
- `/broadcast -all [reply to message]`


**Note:** The clones use the same database as the main bot. Please do not use this feature for illegal purposes. We will not be responsible for any misuse.

PS: If you need any help, feel free to ask in our support group [here.](https://t.me/SpiralTechDivision) I have created this feature with my heart, and it took a lot of time and effort. So, please don't hesitate to /donate to keep this feature alive.
In future, we might close this feature and make it premium. So, use it now and enjoy :3
"""